"""Profili dell'app: ognuno ha il suo registro (didUP o Nuvola), le sue credenziali e i suoi dati."""

import base64
import hashlib
import importlib
import os
import re
import shutil
import sys
import threading
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import dotenv_values

import archivio
import config

BASE = Path(__file__).parent
CARTELLA = Path(config.DATI_DIR) / "profili" if config.DATI_DIR else BASE / "profili"
SERVIZIO = "ParserCompiti"  # nome con cui le password compaiono nel Gestione credenziali di Windows
REGISTRI = {"argo": "Argo didUP", "nuvola": "Nuvola", "classeviva": "ClasseViva"}
_IDENT = re.compile(r"[A-Za-z0-9]{1,20}")  # codice di uno studente ClasseViva, tipo S1234567X

_blocco = threading.Lock()


class ProfiloNonValido(Exception):
    pass


def _elenco_file():
    return CARTELLA / "profili.json"


def _leggi():
    dati = archivio.leggi(_elenco_file())
    if not dati or not isinstance(dati.get("profili"), list):
        return {"profili": [], "ultimo": None, "eliminati": {}}
    dati["profili"] = [p for p in dati["profili"] if isinstance(p, dict) and isinstance(p.get("id"), str)]
    # Quando è stato eliminato ogni profilo: serve alla sincronizzazione, perché non torni dall'altro dispositivo.
    if not isinstance(dati.get("eliminati"), dict):
        dati["eliminati"] = {}
    return dati


def cartella(id_profilo):
    """La cartella con i dati scaricati e le spunte del profilo."""
    if not re.fullmatch(r"[0-9a-f]{8}", id_profilo or ""):
        raise ProfiloNonValido("Profilo non valido.")
    return CARTELLA / id_profilo


def elenco():
    return _leggi()["profili"]


def eliminati():
    return _leggi()["eliminati"]


def adesso():
    return datetime.now().isoformat(timespec="seconds")


def ultimo():
    dati = _leggi()
    return dati["ultimo"] if any(p["id"] == dati["ultimo"] for p in dati["profili"]) else None


def trova(id_profilo):
    return next((p for p in elenco() if p["id"] == id_profilo), None)


def segna_ultimo(id_profilo):
    with _blocco:
        dati = _leggi()
        dati["ultimo"] = id_profilo
        archivio.scrivi(_elenco_file(), dati)


def studenti(id_profilo):
    """Gli studenti tra cui scegliere per un account ClasseViva con più studenti (li annota l'ultimo download); [] se uno solo."""
    elenco = (archivio.leggi(cartella(id_profilo) / "studenti.json") or {}).get("studenti")
    return [{"ident": s["ident"], "name": _testo(s.get("name"))} for s in elenco or []
            if isinstance(s, dict) and isinstance(s.get("ident"), str) and _IDENT.fullmatch(s["ident"])]


def annota_studenti(id_profilo, scelte):
    percorso = cartella(id_profilo) / "studenti.json"
    if scelte:
        archivio.scrivi(percorso, {"studenti": scelte})
    else:
        percorso.unlink(missing_ok=True)


# ---------- password ----------

# Il portachiavi giusto per il sistema, se keyring da solo non ne trova nessuno (può succedere in zaino.exe,
# dove PyInstaller rischia di perdere l'elenco dei portachiavi installati).
_PORTACHIAVI_DEL_SISTEMA = {"win32": ("keyring.backends.Windows", "WinVaultKeyring"), "darwin": ("keyring.backends.macOS", "Keyring")}
_portachiavi_scelto = False


def _portachiavi():
    """Il Gestione credenziali di Windows (o il portachiavi di macOS e Linux), se disponibile."""
    global _portachiavi_scelto
    try:
        import keyring
    except Exception:
        return None
    if not _portachiavi_scelto:
        _portachiavi_scelto = True
        try:
            if keyring.get_keyring().priority <= 0 and sys.platform in _PORTACHIAVI_DEL_SISTEMA:
                modulo, classe = _PORTACHIAVI_DEL_SISTEMA[sys.platform]
                keyring.set_keyring(getattr(importlib.import_module(modulo), classe)())
        except Exception:
            pass
    return keyring


def portachiavi_disponibile():
    """True se le password si possono custodire al sicuro: portachiavi del sistema, o cifrate (sul telefono)."""
    if config.CHIAVE_CREDENZIALI:
        return True
    portachiavi = _portachiavi()
    try:
        return bool(portachiavi) and portachiavi.get_keyring().priority > 0  # il ripiego «fail» di keyring vale 0
    except Exception:
        return False


def _cifrario():
    """Cifra le password su disco se è impostata CHIAVE_CREDENZIALI (sul telefono, dove non c'è il portachiavi)."""
    if not config.CHIAVE_CREDENZIALI:
        return None
    from cryptography.fernet import Fernet

    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(("credenziali|" + config.CHIAVE_CREDENZIALI).encode()).digest()))


def imposta_password(id_profilo, password):
    file = cartella(id_profilo) / "credenziali.json"
    cifrario = _cifrario()
    if cifrario:
        archivio.scrivi(file, {"cifrata": cifrario.encrypt(password.encode()).decode()})
        return
    portachiavi = _portachiavi()
    if portachiavi:
        try:
            portachiavi.set_password(SERVIZIO, id_profilo, password)
            # Si rilegge subito: certi portachiavi (bloccati, o di un'altra sessione su Linux) accettano e poi non restituiscono nulla.
            if portachiavi.get_password(SERVIZIO, id_profilo) == password:
                archivio.scrivi(file, {"dove": "portachiavi"})  # nel file solo dove sta, per spiegare il problema se un giorno manca
                return
        except Exception:
            pass
    # Senza portachiavi la password resta in un file della cartella del profilo, leggibile solo dal tuo utente.
    archivio.scrivi(file, {"password": password})
    try:
        os.chmod(file, 0o600)
    except OSError:
        pass


MANCANTE = "Password del registro mancante: reinseriscila modificando il profilo."


def _leggi_password(id_profilo):
    """(password, perché manca): il motivo spiega cosa fare, invece di un generico «dati non validi»."""
    file = archivio.leggi(cartella(id_profilo) / "credenziali.json") or {}
    cifrario = _cifrario()
    if cifrario and isinstance(file.get("cifrata"), str):
        try:
            return cifrario.decrypt(file["cifrata"].encode()).decode(), ""
        except Exception:
            return "", ("La password salvata non si può più leggere: la chiave del telefono è cambiata (per esempio dopo un ripristino). "
                        "Reinseriscila modificando il profilo, oppure sincronizza col PC.")
    portachiavi = None if cifrario else _portachiavi()
    guasto = False
    if portachiavi:
        try:
            salvata = portachiavi.get_password(SERVIZIO, id_profilo)
            if salvata:
                return salvata, ""
        except Exception:
            guasto = True
    if isinstance(file.get("password"), str) and file["password"]:
        return file["password"], ""
    if file.get("dove") == "portachiavi" or guasto:
        return "", ("La password era nel portachiavi del sistema, che ora non la restituisce (bloccato, non disponibile o di un "
                    "altro utente del computer). Sbloccalo e riprova, oppure reinserisci la password modificando il profilo.")
    return "", MANCANTE


def password(id_profilo):
    return _leggi_password(id_profilo)[0]


def perche_manca_password(id_profilo):
    """Il messaggio da mostrare quando password() è vuota."""
    return _leggi_password(id_profilo)[1] or MANCANTE


def _dimentica_password(id_profilo):
    portachiavi = _portachiavi()
    if portachiavi:
        try:
            portachiavi.delete_password(SERVIZIO, id_profilo)
        except Exception:
            pass


# ---------- creazione, modifica, eliminazione ----------

# Caratteri che non si vedono ma arrivano copiando e incollando (da un messaggio, una mail, un PDF).
_INVISIBILI = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u00ad"), None)


def _testo(valore, massimo=120, spazi=True):
    """Il testo di un campo del modulo, pulito: niente caratteri invisibili né spazi ai lati (spazi=False: nessuno spazio)."""
    if not isinstance(valore, str):
        return ""
    testo = unicodedata.normalize("NFC", valore).translate(_INVISIBILI).replace("\u00a0", " ")
    if not spazi:
        testo = "".join(testo.split())
    return testo.strip()[:massimo]


def codice_scuola(valore):
    """Il codice scuola di Argo come lo vuole Argo: maiuscole e cifre, senza spazi («sc 12345» → «SC12345»)."""
    return _testo(valore, spazi=False).upper()


def nome_utente(registro, valore):
    """Il nome utente pulito. Argo e ClasseViva non hanno spazi nei nomi utente: se ci sono, li ha messi la tastiera."""
    return _testo(valore, spazi=registro == "nuvola")


def password_pulita(valore):
    """La password senza spazi ai lati né caratteri invisibili: si prova se quella scritta viene rifiutata (vedi dati.accedi)."""
    return _testo(valore, massimo=500)


def _untis(valore):
    """Impostazioni WebUntis del profilo: tutte e tre o nessuna."""
    if not isinstance(valore, dict):
        return None
    server, scuola, classe = (_testo(valore.get(k)) for k in ("server", "scuola", "classe"))
    if not (server or scuola or classe):
        return None
    if not (server and scuola and classe):
        raise ProfiloNonValido("Per l'orario WebUntis servono scuola e classe (oppure lascia tutto vuoto).")
    server = server.lower().removeprefix("https://").strip("/")
    # Solo server WebUntis veri: l'app non deve poter essere usata per contattare indirizzi qualsiasi.
    if not re.fullmatch(r"[a-z0-9-]+\.webuntis\.com", server):
        raise ProfiloNonValido("Il server WebUntis deve essere del tipo nome.webuntis.com.")
    return {"server": server, "scuola": scuola, "classe": classe}


def _indirizzo_circolari(valore):
    """L'indirizzo della pagina delle circolari su trasparenza-pa.net (facoltativo: per Argo di solito si trova da solo)."""
    import circolari

    indirizzo = _testo(valore, 300)
    if indirizzo and not circolari.da_indirizzo(indirizzo):
        raise ProfiloNonValido("L'indirizzo delle circolari deve essere una pagina di trasparenza-pa.net, con codcli= nell'indirizzo.")
    return indirizzo


def fonte_circolari(profilo):
    """(codice cliente, node) delle circolari del profilo, o None. Argo: il codice scuola è lo stesso di trasparenza-pa.net."""
    import circolari

    if (profilo or {}).get("circolari"):
        return circolari.da_indirizzo(profilo["circolari"])
    if (profilo or {}).get("registro") == "argo" and profilo.get("scuola"):
        return codice_scuola(profilo["scuola"]), ""
    return None


def stesso_accesso(a, b):
    """True se i due profili entrano nello stesso account (i vecchi profili possono avere il codice scuola in minuscolo)."""
    chiave = lambda p: (p.get("registro"), codice_scuola(p.get("scuola")), nome_utente(p.get("registro"), p.get("utente")))
    return chiave(a) == chiave(b)


def controlla(dati, id_profilo=None):
    """Controlla e pulisce i dati del modulo, senza salvare: (profilo come verrebbe salvato, nuova password o "")."""
    if not isinstance(dati, dict):
        raise ProfiloNonValido("Dati del profilo non validi.")
    registro = dati.get("registro")
    if registro not in REGISTRI:
        raise ProfiloNonValido("Scegli il registro: Argo didUP, Nuvola oppure ClasseViva.")
    nuovo = {
        "nome": _testo(dati.get("nome"), 40),
        "registro": registro,
        "scuola": codice_scuola(dati.get("scuola")) if registro == "argo" else "",
        "utente": nome_utente(registro, dati.get("utente")),
        # Solo ClasseViva: quale studente mostrare se l'account ne ha più d'uno ("" = il primo).
        "studente": _testo(dati.get("studente"), 20) if registro == "classeviva" else "",
        "untis": _untis(dati.get("untis")),
        "circolari": _indirizzo_circolari(dati.get("circolari")),
        "modificato": adesso(),  # tra due copie dello stesso profilo la sincronizzazione tiene la più recente
    }
    if not nuovo["nome"]:
        raise ProfiloNonValido("Dai un nome al profilo.")
    if not nuovo["utente"]:
        raise ProfiloNonValido("Inserisci il nome utente del registro.")
    if registro == "argo" and not nuovo["scuola"]:
        raise ProfiloNonValido("Per Argo didUP serve il codice scuola.")
    if nuovo["studente"] and not _IDENT.fullmatch(nuovo["studente"]):
        raise ProfiloNonValido("Studente non valido.")
    nuova_password = dati.get("password") if isinstance(dati.get("password"), str) else ""
    if not password_pulita(nuova_password):
        nuova_password = ""  # solo spazi: come lasciarla vuota
    if id_profilo is None and not nuova_password:
        raise ProfiloNonValido("Inserisci la password del registro.")
    if id_profilo is not None and not trova(id_profilo):
        raise ProfiloNonValido("Profilo non trovato.")
    return nuovo, nuova_password


def salva(dati, id_profilo=None):
    """Crea un profilo (id_profilo None) o lo modifica. Restituisce il profilo salvato, senza password."""
    nuovo, nuova_password = controlla(dati, id_profilo)
    # Da quando valgono i dati scaricati: la sincronizzazione scarta quelli più vecchi, che sono di un altro account.
    nuovo["dati_dal"] = nuovo["orario_dal"] = nuovo["modificato"]
    with _blocco:
        tutti = _leggi()
        if id_profilo is None:
            nuovo["id"] = uuid.uuid4().hex[:8]
            tutti["profili"].append(nuovo)
        else:
            posizione = next((i for i, p in enumerate(tutti["profili"]) if p["id"] == id_profilo), None)
            if posizione is None:
                raise ProfiloNonValido("Profilo non trovato.")
            vecchio = tutti["profili"][posizione]
            nuovo["id"] = id_profilo
            # Cambiando registro, account o studente i dati scaricati non valgono più.
            stesso_account = stesso_accesso(vecchio, nuovo)
            if not stesso_account:
                (cartella(id_profilo) / "studenti.json").unlink(missing_ok=True)
            # "" vuol dire il primo studente: sceglierlo esplicitamente non cambia i dati.
            primo = (studenti(id_profilo) or [{"ident": ""}])[0]["ident"]
            if not stesso_account or (vecchio.get("studente") or primo) != (nuovo["studente"] or primo):
                (cartella(id_profilo) / "dashboard.json").unlink(missing_ok=True)
            else:
                nuovo["dati_dal"] = vecchio.get("dati_dal", "")
            if vecchio.get("orario_personale"):
                nuovo["orario_personale"] = vecchio["orario_personale"]  # si cambia da imposta_orario, non dal modulo del profilo
            if vecchio.get("circolari", "") != nuovo["circolari"] or not stesso_account:
                (cartella(id_profilo) / "circolari.json").unlink(missing_ok=True)
            if vecchio.get("untis") != nuovo["untis"]:
                (cartella(id_profilo) / "orario.json").unlink(missing_ok=True)
            else:
                nuovo["orario_dal"] = vecchio.get("orario_dal", "")
            tutti["profili"][posizione] = nuovo
        archivio.scrivi(_elenco_file(), tutti)
    if nuova_password:
        imposta_password(nuovo["id"], nuova_password)
    return nuovo


_ORA = re.compile(r"([01]\d|2[0-3]):[0-5]\d")
MASSIMO_ORE = 80  # sei giorni da tredici ore abbondano
MASSIMO_DIVISIONI = 200


def _ore(valore):
    """Le ore dell'orario scritto a mano, controllate: [{giorno, inizio, fine, materia, aula, docente}] in ordine."""
    if not isinstance(valore, list) or len(valore) > MASSIMO_ORE:
        raise ProfiloNonValido(f"L'orario può avere al massimo {MASSIMO_ORE} ore.")
    ore = []
    for ora in valore:
        if not isinstance(ora, dict):
            raise ProfiloNonValido("Ora non valida.")
        giorno, inizio, fine = ora.get("giorno"), _testo(ora.get("inizio"), 5), _testo(ora.get("fine"), 5)
        materia = _testo(ora.get("materia"), 60)
        if not materia:
            continue  # una riga lasciata vuota nel modulo
        if not isinstance(giorno, int) or isinstance(giorno, bool) or not 0 <= giorno <= 5:
            raise ProfiloNonValido("Il giorno va da lunedì a sabato.")
        if not (_ORA.fullmatch(inizio) and _ORA.fullmatch(fine)) or inizio >= fine:
            raise ProfiloNonValido(f"{materia}: inizio e fine vanno scritti come 08:00 e 09:00, con la fine dopo l'inizio.")
        ore.append({"giorno": giorno, "inizio": inizio, "fine": fine, "materia": materia,
                    "aula": _testo(ora.get("aula"), 40), "docente": _testo(ora.get("docente"), 40)})
    ore.sort(key=lambda o: (o["giorno"], o["inizio"]))
    if any((a["giorno"], a["inizio"]) == (b["giorno"], b["inizio"]) for a, b in zip(ore, ore[1:])):
        raise ProfiloNonValido("Due ore iniziano nello stesso giorno alla stessa ora.")
    return ore


def imposta_orario(id_profilo, ore=None, divisione=None):
    """Cambia l'orario scritto a mano (ore) o la scelta per un'ora doppia (divisione: (chiave, materia), "" = togli).

    Sta nel profilo: così passa anche al telefono con la sincronizzazione.
    """
    with _blocco:
        tutti = _leggi()
        profilo = next((p for p in tutti["profili"] if p["id"] == id_profilo), None)
        if profilo is None:
            raise ProfiloNonValido("Profilo non trovato.")
        personale = dict(profilo.get("orario_personale") or {})
        if ore is not None:
            personale["ore"] = _ore(ore)
        if divisione is not None:
            chiave, scelta = divisione
            if not isinstance(chiave, str) or not 0 < len(chiave) <= 140 or not isinstance(scelta, str):
                raise ProfiloNonValido("Scelta non valida.")
            scelte = dict(personale.get("divisione") or {})
            if scelta.strip():
                scelte[chiave] = _testo(scelta, 60)
            else:
                scelte.pop(chiave, None)
            if len(scelte) > MASSIMO_DIVISIONI:
                raise ProfiloNonValido("Troppe ore divise.")
            personale["divisione"] = scelte
        profilo["orario_personale"] = {k: v for k, v in personale.items() if v}
        profilo["modificato"] = adesso()
        archivio.scrivi(_elenco_file(), tutti)
        return profilo


def elimina(id_profilo):
    """Cancella il profilo con tutti i suoi dati (credenziali, dati scaricati, spunte)."""
    percorso = cartella(id_profilo)
    with _blocco:
        tutti = _leggi()
        tutti["profili"] = [p for p in tutti["profili"] if p["id"] != id_profilo]
        if tutti["ultimo"] == id_profilo:
            tutti["ultimo"] = None
        tutti["eliminati"][id_profilo] = adesso()
        archivio.scrivi(_elenco_file(), tutti)
    _dimentica_password(id_profilo)
    shutil.rmtree(percorso, ignore_errors=True)


def sostituisci(nuovi, nuovi_eliminati):
    """Riscrive l'elenco dei profili così com'è (lo usa la sincronizzazione, che li ha già controllati)."""
    with _blocco:
        tutti = _leggi()
        tutti["profili"], tutti["eliminati"] = nuovi, nuovi_eliminati
        archivio.scrivi(_elenco_file(), tutti)


def importa_cartella_del_programma():
    """zaino.exe tiene i dati in %APPDATA%/Zaino: se è stato messo nella cartella di una versione da Python
    (avvia.bat), al primo avvio porta lì profili e dati, che così non si perdono. Le password restano nel
    portachiavi, che le ritrova con lo stesso profilo."""
    if not config.EXE or _elenco_file().exists():
        return False
    accanto = Path(sys.executable).parent
    if not (accanto / "profili" / "profili.json").exists():
        return False
    for nome in ("profili", "cache"):
        if (accanto / nome).is_dir():
            shutil.copytree(accanto / nome, CARTELLA.parent / nome, dirs_exist_ok=True)
    return True


def migra_vecchia_installazione():
    """Prima dei profili c'era un solo account in .env: lo trasforma nel primo profilo, con i suoi dati."""
    if _elenco_file().exists():
        return None
    valori = dotenv_values(BASE / ".env") if (BASE / ".env").exists() else {}
    scuola, utente, vecchia_password = (_testo(valori.get(k)) for k in ("ARGO_SCUOLA", "ARGO_UTENTE", "ARGO_PASSWORD"))
    if not (scuola and utente and vecchia_password):
        return None
    cache = archivio.leggi(BASE / "cache" / "dashboard.json") or {}
    alunno = cache.get("profilo", {}).get("alunno", {}) if isinstance(cache.get("profilo"), dict) else {}
    nome = _testo(alunno.get("nominativo") if isinstance(alunno, dict) else "", 40).title() or "Il mio registro"
    profilo = salva({"nome": nome, "registro": "argo", "scuola": scuola, "utente": utente, "password": vecchia_password})
    destinazione = cartella(profilo["id"])
    destinazione.mkdir(parents=True, exist_ok=True)
    for origine in (BASE / "cache" / "dashboard.json", BASE / "cache" / "orario.json", BASE / "stato.json"):
        if origine.exists():
            shutil.move(str(origine), str(destinazione / origine.name))
    segna_ultimo(profilo["id"])
    return profilo
