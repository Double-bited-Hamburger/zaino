"""Profili dell'app: ognuno ha il suo registro (didUP o Nuvola), le sue credenziali e i suoi dati."""

import base64
import hashlib
import re
import shutil
import sys
import threading
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

def _portachiavi():
    """Il Gestione credenziali di Windows (o equivalente), se disponibile."""
    try:
        import keyring

        return keyring
    except Exception:
        return None


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
            file.unlink(missing_ok=True)
            return
        except Exception:
            pass
    # Senza portachiavi la password resta in un file locale della cartella del profilo.
    archivio.scrivi(file, {"password": password})


def password(id_profilo):
    file = archivio.leggi(cartella(id_profilo) / "credenziali.json") or {}
    cifrario = _cifrario()
    if cifrario and isinstance(file.get("cifrata"), str):
        try:
            return cifrario.decrypt(file["cifrata"].encode()).decode()
        except Exception:
            return ""  # chiave cambiata: la password va reinserita dal profilo
    portachiavi = None if cifrario else _portachiavi()
    if portachiavi:
        try:
            salvata = portachiavi.get_password(SERVIZIO, id_profilo)
            if salvata:
                return salvata
        except Exception:
            pass
    return file.get("password") or ""


def _dimentica_password(id_profilo):
    portachiavi = _portachiavi()
    if portachiavi:
        try:
            portachiavi.delete_password(SERVIZIO, id_profilo)
        except Exception:
            pass


# ---------- creazione, modifica, eliminazione ----------

def _testo(valore, massimo=120):
    return valore.strip()[:massimo] if isinstance(valore, str) else ""


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


def salva(dati, id_profilo=None):
    """Crea un profilo (id_profilo None) o lo modifica. Restituisce il profilo salvato, senza password."""
    if not isinstance(dati, dict):
        raise ProfiloNonValido("Dati del profilo non validi.")
    registro = dati.get("registro")
    if registro not in REGISTRI:
        raise ProfiloNonValido("Scegli il registro: Argo didUP, Nuvola oppure ClasseViva.")
    nuovo = {
        "nome": _testo(dati.get("nome"), 40),
        "registro": registro,
        "scuola": _testo(dati.get("scuola")) if registro == "argo" else "",
        "utente": _testo(dati.get("utente")),
        # Solo ClasseViva: quale studente mostrare se l'account ne ha più d'uno ("" = il primo).
        "studente": _testo(dati.get("studente"), 20) if registro == "classeviva" else "",
        "untis": _untis(dati.get("untis")),
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

    # Da quando valgono i dati scaricati: la sincronizzazione scarta quelli più vecchi, che sono di un altro account.
    nuovo["dati_dal"] = nuovo["orario_dal"] = nuovo["modificato"]
    with _blocco:
        tutti = _leggi()
        if id_profilo is None:
            if not nuova_password:
                raise ProfiloNonValido("Inserisci la password del registro.")
            nuovo["id"] = uuid.uuid4().hex[:8]
            tutti["profili"].append(nuovo)
        else:
            posizione = next((i for i, p in enumerate(tutti["profili"]) if p["id"] == id_profilo), None)
            if posizione is None:
                raise ProfiloNonValido("Profilo non trovato.")
            vecchio = tutti["profili"][posizione]
            nuovo["id"] = id_profilo
            # Cambiando registro, account o studente i dati scaricati non valgono più.
            stesso_account = (vecchio.get("registro"), vecchio.get("scuola"), vecchio.get("utente")) == (nuovo["registro"], nuovo["scuola"], nuovo["utente"])
            if not stesso_account:
                (cartella(id_profilo) / "studenti.json").unlink(missing_ok=True)
            # "" vuol dire il primo studente: sceglierlo esplicitamente non cambia i dati.
            primo = (studenti(id_profilo) or [{"ident": ""}])[0]["ident"]
            if not stesso_account or (vecchio.get("studente") or primo) != (nuovo["studente"] or primo):
                (cartella(id_profilo) / "dashboard.json").unlink(missing_ok=True)
            else:
                nuovo["dati_dal"] = vecchio.get("dati_dal", "")
            if vecchio.get("untis") != nuovo["untis"]:
                (cartella(id_profilo) / "orario.json").unlink(missing_ok=True)
            else:
                nuovo["orario_dal"] = vecchio.get("orario_dal", "")
            tutti["profili"][posizione] = nuovo
        archivio.scrivi(_elenco_file(), tutti)
    if nuova_password:
        imposta_password(nuovo["id"], nuova_password)
    return nuovo


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
