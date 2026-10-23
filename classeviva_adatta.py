"""Porta i dati grezzi di ClasseViva nella stessa forma di quelli di Argo, così il resto dell'app non cambia.

Su ClasseViva:
- l'agenda contiene sia i compiti (codice AGHW, alla data di consegna) sia le annotazioni (AGNT), tra cui le verifiche;
- i compiti della sezione «Compiti» arrivano a parte, dal sito, con la data in cui sono stati assegnati e quella di consegna;
- i voti blu, o annullati, non fanno media;
- le assenze hanno un codice: ABA0 assenza, ABR0 ritardo, ABR1 ritardo breve, ABU0 uscita anticipata.
"""

import re
from datetime import datetime

from nuvola_adatta import TIPI, _lista, _testo, valore_voto

COMPITO, ANNOTAZIONE, PRENOTAZIONE_AULA = "AGHW", "AGNT", "AGCR"
ASSENZE = {"ABA0": ("A", "Assenza"), "ABR0": ("I", "Ritardo"), "ABR1": ("I", "Ritardo breve"), "ABU0": ("U", "Uscita anticipata")}
LEZIONE_NORMALE = "LSF0"  # le altre sono compresenze e sostegno, sulla stessa ora


def _numero(valore):
    return valore if isinstance(valore, (int, float)) and not isinstance(valore, bool) else None


def _data(valore):
    """La data «AAAA-MM-GG» così come è scritta (senza cambiare fuso: è l'ora della scuola)."""
    testo = _testo(valore).strip()
    return testo[:10] if re.match(r"\d{4}-\d{2}-\d{2}", testo) else None


def _ora(valore):
    """«HH:MM» da un momento tipo «2026-10-12T09:00:00+02:00»; stringa vuota se manca."""
    try:
        return datetime.fromisoformat(_testo(valore).strip().replace("Z", "+00:00")).strftime("%H:%M")
    except ValueError:
        return ""


def _nome(testo):
    """«COGNOME NOME» diviso in (cognome, nome): ClasseViva li scrive insieme, il primo pezzo fa da cognome."""
    parti = _testo(testo).split()
    return (parti[0], " ".join(parti[1:])) if parti else ("", "")


def _materie(grezzo):
    materie, docenti = [], {}
    for materia in _lista(grezzo.get("materie")):
        sigla, nome = str(materia.get("id")), _testo(materia.get("description"))
        if not nome:
            continue
        materie.append({"abbreviazione": sigla, "materia": nome, "faMedia": True})
        for docente in _lista(materia.get("teachers")):
            chiave = _testo(docente.get("teacherId")) or _testo(docente.get("teacherName"))
            cognome, nomi = _nome(docente.get("teacherName"))
            if chiave and cognome:
                voce = docenti.setdefault(chiave, {"pk": chiave, "desCognome": cognome, "desNome": nomi, "nominativo": _testo(docente.get("teacherName")).upper(), "materie": []})
                voce["materie"].append(sigla)
    return materie, list(docenti.values())


def _voti(grezzo):
    voti = []
    for voto in _lista(grezzo.get("voti")):
        decimale = _numero(voto.get("decimalValue"))
        valore = float(decimale) if decimale is not None else valore_voto({"valutazione": voto.get("displayValue")})
        componente = _testo(voto.get("componentDesc")).lower()
        fuori_media = voto.get("canceled") is True or _testo(voto.get("color")).lower() == "blue"
        voti.append({
            "datGiorno": _data(voto.get("evtDate")),
            "desMateria": _testo(voto.get("subjectDesc")),
            "pkMateria": str(voto.get("subjectId")),
            "valore": valore,
            "codCodice": _testo(voto.get("displayValue")),
            "codVotoPratico": next((sigla for parte, sigla in TIPI.items() if parte in componente), ""),
            "faMenoMedia": "S" if fuori_media else "",
            "docente": "",
            "descrizioneProva": _testo(voto.get("notesForFamily")),
        })
    return voti


def _lezioni(grezzo):
    """Le ore di lezione firmate, nella forma del registro di classe di Argo (servono alle ore perse)."""
    registro = []
    # Prima le lezioni normali: a parità di ora vince quella, non la compresenza.
    for lezione in sorted(_lista(grezzo.get("lezioni")), key=lambda l: _testo(l.get("evtCode")) != LEZIONE_NORMALE):
        giorno, ora, durata = _data(lezione.get("evtDate")), _numero(lezione.get("evtHPos")), _numero(lezione.get("evtDuration")) or 1
        if not giorno or not isinstance(ora, int):
            continue
        for scarto in range(max(1, min(int(round(durata)), 6))):  # una lezione di due ore occupa due righe
            registro.append({"datGiorno": giorno, "ora": ora + scarto, "materia": _testo(lezione.get("subjectDesc")),
                             "docente": _testo(lezione.get("authorName")), "compiti": []})
    return registro


def _agenda(grezzo, docenti):
    compiti, promemoria = [], []
    per_nome = {d["nominativo"]: d["pk"] for d in docenti}
    for voce in _lista(grezzo.get("agenda")):
        codice, giorno, testo = _testo(voce.get("evtCode")), _data(voce.get("evtDatetimeBegin")), _testo(voce.get("notes")).strip()
        if not giorno or not testo or codice == PRENOTAZIONE_AULA:
            continue
        materia, docente = _testo(voce.get("subjectDesc")), _testo(voce.get("authorName"))
        if codice == COMPITO:
            # ClasseViva mette il compito nel giorno in cui va consegnato; quando è stato assegnato non si sa.
            compiti.append({"datGiorno": None, "materia": materia, "docente": docente, "compiti": [{"compito": testo, "dataConsegna": giorno}]})
            continue
        intera = voce.get("isFullDay") is True
        promemoria.append({
            "datGiorno": giorno, "desAnnotazioni": testo, "materia": materia, "docente": docente,
            # Senza materia, il parser la deduce dalle materie del docente.
            "pkDocente": per_nome.get(docente.upper(), ""),
            "oraInizio": "00:00" if intera else _ora(voce.get("evtDatetimeBegin")),
            "oraFine": "00:00" if intera else _ora(voce.get("evtDatetimeEnd")),
        })
    return compiti, promemoria


def _compiti_sito(grezzo):
    compiti = []
    for voce in _lista(grezzo.get("compiti")):
        testo, consegna = _testo(voce.get("homeworkDesc")).strip(), _data(voce.get("expiryDate"))
        if not testo or not consegna:
            continue
        compiti.append({"datGiorno": _data(voce.get("assignmentDate")), "materia": _testo(voce.get("subjectDesc")), "docente": _testo(voce.get("teacherName")),
                        "compiti": [{"compito": testo, "dataConsegna": consegna}]})
    return compiti


def _consegna_e_testo(voce):
    compito = voce["compiti"][0]
    return compito["dataConsegna"], " ".join(compito["compito"].split())


def _appello(grezzo):
    appello = []
    for evento in _lista(grezzo.get("assenze")):
        codice, descrizione = ASSENZE.get(_testo(evento.get("evtCode")), ("A", "Assenza"))
        ora, giustificata = _numero(evento.get("evtHPos")), evento.get("isJustified") is True
        appello.append({
            "data": _data(evento.get("evtDate")),
            "codEvento": codice,
            "descrizione": descrizione,
            # Stessa dicitura delle note di Argo, così le ore perse si calcolano allo stesso modo.
            "nota": f"{'Ingresso' if codice == 'I' else 'Uscita'} in {int(ora)}^ ora" if ora and codice != "A" else _testo(evento.get("justifReasonDesc")),
            "giustificata": "S" if giustificata else "N",
            "daGiustificare": not giustificata,
        })
    return appello


def _periodi(grezzo):
    return [
        {"descrizione": _testo(p.get("periodDesc")), "dataInizio": _data(p.get("dateStart")), "dataFine": _data(p.get("dateEnd"))}
        for p in _lista(grezzo.get("periodi"))
    ]


def converti(grezzo, oggi=None):
    """(profilo, dashboard) nella forma prodotta dal client Argo."""
    materie, docenti = _materie(grezzo)
    compiti, promemoria = _agenda(grezzo, docenti)
    dal_sito = _compiti_sito(grezzo)
    # Un compito che c'è sia in agenda sia nella sezione «Compiti» si tiene una volta, nella versione del sito
    # (che sa anche quando è stato assegnato).
    doppi = {_consegna_e_testo(c) for c in dal_sito}
    compiti = [c for c in compiti if _consegna_e_testo(c) not in doppi] + dal_sito
    lezioni, voti = _lezioni(grezzo), _voti(grezzo)
    noti = {m["materia"] for m in materie}
    # Materie che compaiono nei voti o nelle lezioni ma non nell'elenco: si aggiungono, così nessuna resta fuori
    # (delle lezioni contano solo quelle normali: compresenza e sostegno non sono materie).
    normali = {_testo(l.get("subjectDesc")) for l in _lista(grezzo.get("lezioni")) if _testo(l.get("evtCode")) in (LEZIONE_NORMALE, "")}
    for nome in sorted(({v["desMateria"] for v in voti} | normali) - noti):
        if nome:
            materie.append({"abbreviazione": nome, "materia": nome, "faMedia": True})
    scheda = grezzo.get("card") if isinstance(grezzo.get("card"), dict) else {}
    classe = next((_testo(v.get("classDesc")).split()[0] for v in _lista(grezzo.get("lezioni")) + _lista(grezzo.get("agenda")) if _testo(v.get("classDesc")).split()), "")
    profilo = {
        "alunno": {"nominativo": " ".join(p for p in (_testo(scheda.get("lastName")), _testo(scheda.get("firstName"))) if p)},
        "scheda": {"classe": {"desDenominazione": classe, "desSezione": ""}},
    }
    dashboard = {
        "listaMaterie": materie,
        "listaDocentiClasse": [{k: v for k, v in d.items() if k != "nominativo"} for d in docenti],
        "listaPeriodi": _periodi(grezzo),
        "voti": voti,
        "registro": compiti + lezioni,
        "promemoria": promemoria,
        "appello": _appello(grezzo),
    }
    return profilo, dashboard
