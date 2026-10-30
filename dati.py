"""Scarica i dati del registro e li prepara per l'interfaccia."""

import threading
from collections import Counter
from dataclasses import asdict
from datetime import date, datetime, timedelta

import archivio
import classeviva_adatta
import config
import nuvola_adatta
import orario
import parser as estrai
import profili
import stats
import untis_client
from archivio import ErroreRegistro
from argo_client import ArgoClient
from classeviva_client import ClassevivaClient
from nuvola_client import NuvolaClient

# Il profilo in uso e i suoi file: li imposta attiva() quando si sceglie un profilo.
PROFILO = None
CACHE = CACHE_ORARIO = STATO = None

# Il server risponde a più richieste insieme: le modifiche alle spunte vanno fatte una alla volta.
_blocco_stato = threading.Lock()

_scrivi, _leggi = archivio.scrivi, archivio.leggi


def attiva(profilo, ricorda=True):
    """Da qui in poi l'app lavora sui dati di questo profilo (None = nessun profilo)."""
    global PROFILO, CACHE, CACHE_ORARIO, STATO
    PROFILO = profilo
    if profilo is None:
        CACHE = CACHE_ORARIO = STATO = None
        return
    cartella = profili.cartella(profilo["id"])
    CACHE, CACHE_ORARIO, STATO = cartella / "dashboard.json", cartella / "orario.json", cartella / "stato.json"
    if ricorda:
        profili.segna_ultimo(profilo["id"])


def _scarica_argo(profilo, password):
    client = ArgoClient(profilo["scuola"], profilo["utente"], password)
    client.login()
    alunno, dashboard = client.dashboard()
    return {"profilo": alunno, "dashboard": dashboard}


def _scarica_nuvola(profilo, password, cache, oggi=None):
    client = NuvolaClient(profilo["utente"], password)
    client.login()
    # Compiti e lezioni si leggono un giorno alla volta: i giorni già letti restano in cache e si accumulano.
    precedente = (_leggi(cache) or {}).get("nuvola")
    giorni = precedente.get("giorni") if isinstance(precedente, dict) and isinstance(precedente.get("giorni"), dict) else {}
    grezzo = client.scarica(oggi, giorni_gia_letti=giorni)
    grezzo["giorni"] = {**giorni, **grezzo["giorni"]}
    alunno, dashboard = nuvola_adatta.converti(grezzo)
    return {"profilo": alunno, "dashboard": dashboard, "nuvola": grezzo}


def _scarica_classeviva(profilo, password, cache, oggi=None):
    client = ClassevivaClient(profilo["utente"], password, profilo.get("studente", ""))
    client.login()
    profili.annota_studenti(profilo["id"], client.scelte)  # per la scelta dello studente nel modulo del profilo
    grezzo = client.scarica(oggi)
    if grezzo.get("compiti") is None:
        # Il sito non ha risposto: restano i compiti letti l'ultima volta, invece di sparire fino al prossimo «Aggiorna».
        precedente = (_leggi(cache) or {}).get("classeviva")
        compiti = precedente.get("compiti") if isinstance(precedente, dict) else None
        grezzo["compiti"] = compiti if isinstance(compiti, list) else []
    alunno, dashboard = classeviva_adatta.converti(grezzo, oggi)
    return {"profilo": alunno, "dashboard": dashboard, "classeviva": grezzo}


def scarica():
    """Scarica i dati dal registro del profilo attivo e li salva in cache."""
    # Profilo e file si fissano subito: se nel frattempo si cambia profilo, i dati non finiscono in quello sbagliato.
    profilo, cache = PROFILO, CACHE
    if not profilo:
        raise ErroreRegistro("Scegli prima un profilo.")
    password = profili.password(profilo["id"])
    if not password:
        raise ErroreRegistro("Password del registro mancante: modificala nel profilo.")
    if profilo.get("registro") == "nuvola":
        dati = _scarica_nuvola(profilo, password, cache)
    elif profilo.get("registro") == "classeviva":
        dati = _scarica_classeviva(profilo, password, cache)
    else:
        dati = _scarica_argo(profilo, password)
    dati["scaricato"] = datetime.now().isoformat(timespec="seconds")
    _scrivi(cache, dati)
    return dati


def carica():
    """Ultimi dati scaricati, oppure None se non c'è ancora nulla (o il file è rovinato)."""
    dati = _leggi(CACHE) if CACHE else None
    if not dati or not isinstance(dati.get("dashboard"), dict):
        return None
    dati.setdefault("scaricato", datetime.fromtimestamp(CACHE.stat().st_mtime).isoformat(timespec="seconds"))
    return dati


def carica_orario():
    dati = _leggi(CACHE_ORARIO) if CACHE_ORARIO else None
    if not dati or not isinstance(dati.get("settimane"), list) or not isinstance(dati.get("viste"), dict):
        return None
    return dati


def scarica_orario(oggi=None):
    """Scarica l'orario da WebUntis e annota quando è comparsa ogni variazione."""
    untis, cache = (PROFILO or {}).get("untis"), CACHE_ORARIO
    if not untis:
        if cache:
            cache.unlink(missing_ok=True)
        return None
    oggi = oggi or date.today()
    if oggi.weekday() == 6:  # di domenica interessa già la settimana che inizia
        oggi += timedelta(days=1)
    settimane = untis_client.scarica(untis["server"], untis["scuola"], untis["classe"], oggi)
    precedente = _leggi(cache)
    if not precedente or not isinstance(precedente.get("viste"), dict):
        precedente = None
    adesso = datetime.now().isoformat(timespec="seconds")
    viste = (precedente or {}).get("viste", {})
    # Al primo download nessuna variazione è "nuova": non c'è nulla con cui confrontarla.
    variazioni = {
        l.chiave: viste.get(l.chiave, adesso if precedente else "")
        for l in orario.converti(settimane)
        if l.variazione
    }
    dati = {"scaricato": adesso, "settimane": settimane, "viste": variazioni}
    _scrivi(cache, dati)
    return dati


def _personale():
    personale = (PROFILO or {}).get("orario_personale")
    return personale if isinstance(personale, dict) else {}


def lezioni_orario(dashboard, oggi=None):
    """(lezioni, dati grezzi) dell'orario: l'ultimo scaricato da WebUntis o, senza WebUntis, quello scritto a mano
    nel profilo (grezzo con fonte «manuale»). ([], None) se non c'è nessuno dei due."""
    divisione = _personale().get("divisione") or {}
    grezzo = carica_orario() if (PROFILO or {}).get("untis") else None
    if grezzo:
        return orario.converti(grezzo["settimane"], orario.docenti_noti(dashboard), divisione), {**grezzo, "fonte": "untis"}
    if _personale().get("ore"):
        return orario.manuali(_personale()["ore"], oggi or date.today(), divisione), {"fonte": "manuale", "scaricato": None, "viste": {}}
    return [], None


def _orario(dashboard, lezioni, grezzo):
    if not grezzo:
        return None
    return {
        "fonte": grezzo["fonte"],
        "scaricato": grezzo.get("scaricato"),
        "settimane": orario.per_settimana(lezioni),
        "lezioni": [
            {**asdict(l), "variazione": l.variazione, "nuova": bool(grezzo.get("scaricato")) and grezzo["viste"].get(l.chiave) == grezzo["scaricato"]}
            for l in lezioni
        ],
    }


def _stato_salvato():
    stato = _leggi(STATO) if STATO else None
    if not stato or not isinstance(stato.get("fatti"), dict):
        return {"fatti": {}}
    return stato


def leggi_stato():
    """Le spunte, come servono alla pagina."""
    return {"fatti": _stato_salvato()["fatti"]}


def segna_compito(id_compito, fatto):
    if not STATO:
        raise ErroreRegistro("Scegli prima un profilo.")
    with _blocco_stato:
        stato = _stato_salvato()
        # Si ricorda anche quando una spunta viene tolta: senza, la sincronizzazione la farebbe tornare dall'altro dispositivo.
        tolti = stato["tolti"] if isinstance(stato.get("tolti"), dict) else {}
        adesso = datetime.now().isoformat(timespec="seconds")
        if fatto:
            stato["fatti"][id_compito] = adesso
            tolti.pop(id_compito, None)
        elif stato["fatti"].pop(id_compito, None):
            tolti[id_compito] = adesso
        if tolti or "tolti" in stato:
            stato["tolti"] = tolti
        _scrivi(STATO, stato)
        return {"fatti": stato["fatti"]}


def _periodi(dashboard):
    periodi = []
    for periodo in estrai.voci(dashboard, "listaPeriodi"):
        inizio, fine = estrai._data(periodo.get("dataInizio")), estrai._data(periodo.get("dataFine"))
        if inizio and fine and 0 <= (fine - inizio).days < 300:  # esclude "Intero anno"
            nome = estrai._pulisci(periodo.get("descrizione")).capitalize()
            # Argo chiama «Scrutinio finale» la seconda parte dell'anno.
            periodi.append(("Secondo periodo" if nome.lower() == "scrutinio finale" else nome, inizio, fine))
    return periodi


def _medie_registro(dashboard):
    """{materia: media calcolata da Argo}, per accorgersi se il nostro calcolo se ne discosta."""
    medie = dashboard.get("mediaMaterie")
    risultato = {}
    if not isinstance(medie, dict):
        return risultato
    for voto in estrai.voci(dashboard, "voti"):
        dettagli = medie.get(voto.get("pkMateria")) if isinstance(voto.get("pkMateria"), str) else None
        media = dettagli.get("mediaMateria") if isinstance(dettagli, dict) else None
        if isinstance(media, (int, float)) and not isinstance(media, bool) and media > 0:
            risultato[estrai._nome_materia(voto.get("desMateria"))] = float(media)
    return risultato


def _oggetto(valore):
    return valore if isinstance(valore, dict) else {}


def _json(valore):
    """Rende serializzabili date e dataclass."""
    if isinstance(valore, (date, datetime)):
        return valore.isoformat()
    if isinstance(valore, dict):
        return {k: _json(v) for k, v in valore.items()}
    if isinstance(valore, (list, tuple)):
        return [_json(v) for v in valore]
    return valore


def elabora(dati, oggi=None):
    """Tutto ciò che serve alla pagina, a partire dai dati grezzi."""
    oggi = oggi or date.today()
    dashboard, profilo = _oggetto(dati.get("dashboard")), _oggetto(dati.get("profilo"))
    if isinstance(dati.get("nuvola"), dict):
        # Su Nuvola cosa è «lezione svolta» e cosa «verifica in arrivo» dipende dal giorno in cui si guarda.
        profilo, dashboard = nuvola_adatta.converti(dati["nuvola"], oggi)
    elif isinstance(dati.get("classeviva"), dict):
        # Dai grezzi: una correzione dell'adattatore vale subito, senza riscaricare.
        profilo, dashboard = classeviva_adatta.converti(dati["classeviva"], oggi)

    scartate = []  # voci del registro con un formato inatteso, saltate
    promemoria = estrai.promemoria(dashboard, scartate=scartate)
    compiti = estrai.compiti(dashboard, scartate=scartate)
    voti = estrai.voti(dashboard, scartate=scartate)
    eventi = estrai.assenze(dashboard, scartate=scartate)
    lezioni = estrai.lezioni(dashboard)
    lezioni_settimana, grezzo_orario = lezioni_orario(dashboard, oggi)
    statistiche = stats.per_materia(voti)
    carico = stats.carico(compiti, promemoria, oggi)
    futuri = [p for p in promemoria if p.data >= oggi]
    materie = sorted(
        {
            estrai._nome_materia(m.get("materia"))
            for m in estrai.voci(dashboard, "listaMaterie")
            if m.get("faMedia", True) and estrai._pulisci(m.get("materia"))
        }
    )
    medie_registro = _medie_registro(dashboard)

    classe = _oggetto(_oggetto(profilo.get("scheda")).get("classe"))
    return _json(
        {
            "studente": estrai._pulisci(_oggetto(profilo.get("alunno")).get("nominativo")).title(),
            "classe": estrai._pulisci(classe.get("desDenominazione")) + estrai._pulisci(classe.get("desSezione")),
            "scaricato": dati.get("scaricato"),
            "oggi": oggi,
            "sufficienza": config.SUFFICIENZA,
            # Dal lunedì di questa settimana, così il PDF settimanale è completo; l'agenda mostra solo i futuri.
            "promemoria": [asdict(p) for p in promemoria if p.data >= oggi - timedelta(days=oggi.weekday())],
            "compiti": [
                {**asdict(c), "id": c.id}
                for c in compiti
                if c.consegna >= oggi - timedelta(days=config.GIORNI_SCADUTI)
            ],
            # Tutti i compiti dell'anno: servono alla mappa a colori e all'esportazione.
            "compiti_anno": [{**asdict(c), "id": c.id} for c in compiti],
            "voti": [asdict(v) for v in voti],
            # Giudizi senza numero e voti che non fanno media: si mostrano nell'elenco ma non entrano nei calcoli.
            "voti_fuori_media": [asdict(v) for v in estrai.voti(dashboard, in_media=False)],
            "materie": materie,
            "statistiche": [
                {**asdict(s), "insufficiente": s.insufficiente, "media_registro": medie_registro.get(s.materia)}
                for s in statistiche
            ],
            "media_generale": stats.media_generale(statistiche),
            "distribuzione": stats.distribuzione(voti),
            "voti_per_mese": stats.per_mese(voti),
            "voti_per_tipo": stats.per_tipo(voti),
            "voti_per_periodo": stats.per_periodo(voti, _periodi(dashboard)),
            "consigli": stats.consigli(statistiche, [p for p in futuri if p.verifica], materie, carico, oggi),
            "carico": carico,
            "assenze": stats.assenze(eventi, lezioni, orario.ore_settimanali(lezioni_settimana)),
            "orario": _orario(dashboard, lezioni_settimana, grezzo_orario),
            "scartate": dict(Counter(scartate)),
        }
    )


def riassunto(elaborati, stato, oggi=None):
    """Il colpo d'occhio di un profilo per la panoramica: medie, verifiche, compiti da fare, ultimi voti."""
    oggi = oggi or date.today()
    fatti = stato.get("fatti", {})
    entro = (oggi + timedelta(days=14)).isoformat()
    return {
        "studente": elaborati["studente"],
        "classe": elaborati["classe"],
        "scaricato": elaborati["scaricato"],
        "media_generale": elaborati["media_generale"],
        "insufficienti": [{"materia": s["materia"], "media": s["media"]} for s in elaborati["statistiche"] if s["insufficiente"]],
        "verifiche": [
            {"data": p["data"], "materia": p["materia"], "testo": p["testo"]}
            for p in elaborati["promemoria"]
            if p["verifica"] and oggi.isoformat() <= p["data"] <= entro
        ][:5],
        "compiti": [
            {"id": c["id"], "consegna": c["consegna"], "materia": c["materia"], "testo": c["testo"]}
            for c in elaborati["compiti"]
            if c["id"] not in fatti and oggi.isoformat() <= c["consegna"] <= entro
        ][:8],
        "ultimi_voti": [
            {"data": v["data"], "materia": v["materia"], "valore": v["valore"]}
            for v in sorted(elaborati["voti"], key=lambda v: v["data"], reverse=True)[:3]
        ],
    }
