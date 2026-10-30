"""Statistiche su voti, carico di lavoro e assenze."""

import math
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta

import config

GIORNI = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]


@dataclass
class StatMateria:
    materia: str
    numero: int
    somma: float
    media: float
    minimo: float
    massimo: float
    media_scritto: float | None
    media_orale: float | None
    media_pratico: float | None
    ultimo: float
    andamento: str  # "su", "giu", "stabile" oppure "" se i voti sono troppo pochi
    minimo_sufficienza: float  # voto minimo alla prossima prova per avere la media sufficiente

    @property
    def insufficiente(self):
        return self.media < config.SUFFICIENZA


def _media(valori):
    return sum(valori) / len(valori) if valori else None


def _andamento(valori):
    recenti, precedenti = valori[-config.VOTI_RECENTI :], valori[: -config.VOTI_RECENTI]
    if not precedenti:
        return ""
    differenza = _media(recenti) - _media(precedenti)
    if differenza > config.SOGLIA_ANDAMENTO:
        return "su"
    if differenza < -config.SOGLIA_ANDAMENTO:
        return "giu"
    return "stabile"


def voto_necessario(valori, obiettivo=None):
    """Voto minimo alla prossima prova perché la media arrivi (o resti) all'obiettivo.

    Può uscire dalla scala dei voti: sopra 10 una prova non basta, sotto 1 va bene qualsiasi voto.
    """
    obiettivo = config.SUFFICIENZA if obiettivo is None else obiettivo
    serve = obiettivo * (len(valori) + 1) - sum(valori)
    return math.ceil(serve * 4 - 1e-9) / 4  # arrotondato al quarto di voto superiore


def per_materia(voti):
    """`voti` in ordine cronologico. Restituisce le materie dalla media più bassa."""
    gruppi = {}
    for voto in voti:
        gruppi.setdefault(voto.materia, []).append(voto)
    risultati = []
    for materia, lista in gruppi.items():
        valori = [v.valore for v in lista]
        risultati.append(
            StatMateria(
                materia=materia,
                numero=len(valori),
                somma=sum(valori),
                media=_media(valori),
                minimo=min(valori),
                massimo=max(valori),
                media_scritto=_media([v.valore for v in lista if v.tipo == "Scritto"]),
                media_orale=_media([v.valore for v in lista if v.tipo == "Orale"]),
                media_pratico=_media([v.valore for v in lista if v.tipo == "Pratico"]),
                ultimo=valori[-1],
                andamento=_andamento(valori),
                minimo_sufficienza=voto_necessario(valori),
            )
        )
    return sorted(risultati, key=lambda s: s.media)


def media_generale(statistiche):
    """Media delle medie di materia, come in pagella."""
    return _media([s.media for s in statistiche])


def distribuzione(voti):
    """Quanti voti per fascia: sotto il 4, poi una fascia per ogni voto intero."""
    conteggio = Counter(max(3, min(10, int(v.valore))) for v in voti)
    return [{"fascia": "<4" if n == 3 else str(n), "numero": conteggio[n]} for n in range(3, 11)]


def per_mese(voti):
    mesi = {}
    for voto in voti:
        mesi.setdefault(voto.data.strftime("%Y-%m"), []).append(voto.valore)
    return [{"mese": mese, "media": _media(v), "numero": len(v)} for mese, v in sorted(mesi.items())]


def per_tipo(voti):
    tipi = {}
    for voto in voti:
        tipi.setdefault(voto.tipo or "Altro", []).append(voto.valore)
    return [{"tipo": tipo, "media": _media(v), "numero": len(v)} for tipo, v in sorted(tipi.items())]


def per_periodo(voti, periodi):
    """`periodi`: lista di (descrizione, inizio, fine)."""
    risultati = []
    for descrizione, inizio, fine in periodi:
        valori = [v.valore for v in voti if inizio <= v.data <= fine]
        risultati.append({"periodo": descrizione, "media": _media(valori), "numero": len(valori)})
    return risultati


def _lunedi(giorno):
    return giorno - timedelta(days=giorno.weekday())


def carico(compiti, promemoria, oggi):
    """Quanto lavoro arriva da ogni materia e in ogni periodo. Liste di tutto l'anno."""
    verifiche = [p for p in promemoria if p.verifica]
    materie = Counter(c.materia for c in compiti)
    materie_verifiche = Counter(p.materia for p in verifiche if p.materia)
    docenti = Counter(c.docente for c in compiti if c.docente)
    docenti_verifiche = Counter(p.docente for p in verifiche if p.docente)

    date = [c.consegna for c in compiti] + [p.data for p in verifiche]
    settimane = []
    if date:
        settimana, ultima = _lunedi(min(date)), _lunedi(max(max(date), oggi))
        while settimana <= ultima:
            fine = settimana + timedelta(days=6)
            settimane.append(
                {
                    "inizio": settimana,
                    "compiti": sum(settimana <= c.consegna <= fine for c in compiti),
                    "verifiche": sum(settimana <= p.data <= fine for p in verifiche),
                    "corrente": settimana == _lunedi(oggi),
                }
            )
            settimana += timedelta(days=7)

    giorni_settimana = Counter(c.consegna.weekday() for c in compiti)
    prossimi = []
    for i in range(14):
        giorno = oggi + timedelta(days=i)
        prossimi.append(
            {
                "data": giorno,
                "compiti": sum(c.consegna == giorno for c in compiti),
                "verifiche": sum(p.data == giorno for p in verifiche),
            }
        )
    passate = [s for s in settimane if s["inizio"] <= _lunedi(oggi)]
    return {
        "per_materia": [
            {"materia": m, "compiti": materie[m], "verifiche": materie_verifiche[m]}
            for m in sorted(set(materie) | set(materie_verifiche), key=lambda m: -(materie[m] + materie_verifiche[m]))
        ],
        "per_docente": [
            {"docente": d, "compiti": docenti[d], "verifiche": docenti_verifiche[d]}
            for d in sorted(set(docenti) | set(docenti_verifiche), key=lambda d: -(docenti[d] + docenti_verifiche[d]))
        ],
        "per_settimana": settimane,
        "per_giorno_settimana": [{"giorno": GIORNI[i], "compiti": giorni_settimana[i]} for i in range(6)],
        "prossimi_giorni": prossimi,
        "totale_compiti": len(compiti),
        "totale_verifiche": len(verifiche),
        "media_compiti_settimana": _media([s["compiti"] for s in passate]),
        "media_verifiche_settimana": _media([s["verifiche"] for s in passate]),
    }


def assenze(eventi, lezioni, ore_settimanali=None):
    """Giorni e ore persi. `lezioni`: le ore firmate sul registro, per contare quelle saltate.

    `ore_settimanali`: quante ore ha la settimana di questa classe, dall'orario (orario.ore_settimanali); senza orario
    vale ORE_SETTIMANALI di config.py. Servono per il limite del 25% e per la previsione a fine anno.
    """
    settimanali = ore_settimanali or config.ORE_SETTIMANALI
    ore_giorno = {}
    for lezione in lezioni:
        ore_giorno.setdefault(lezione.data, {})[lezione.ora] = lezione.materia

    dettaglio, materie, mesi = [], Counter(), Counter()
    for evento in eventi:
        ore = ore_giorno.get(evento.data)
        saltate = None  # None = non si riesce a determinare
        if ore:
            if evento.tipo == "assenza":
                saltate = list(ore)
            elif evento.ora:
                # Chi entra alla N-esima ora perde le precedenti; chi esce alla N-esima perde da lì in poi.
                saltate = [o for o in ore if (o < evento.ora if evento.tipo == "ritardo" else o >= evento.ora)]
        if saltate is not None:
            materie.update(ore[o] for o in saltate)
            mesi[evento.data.strftime("%Y-%m")] += len(saltate)
        dettaglio.append({**vars(evento), "ore": None if saltate is None else len(saltate)})

    ore_perse = sum(e["ore"] or 0 for e in dettaglio)
    ore_svolte = sum(len(ore) for ore in ore_giorno.values())
    limite = settimanali * config.SETTIMANE_SCUOLA * config.LIMITE_ASSENZE
    return {
        "eventi": dettaglio,
        "giorni_assenza": sum(e.tipo == "assenza" for e in eventi),
        "ritardi": sum(e.tipo == "ritardo" for e in eventi),
        "uscite": sum(e.tipo == "uscita" for e in eventi),
        "da_giustificare": sum(e.da_giustificare for e in eventi),
        "ore_perse": ore_perse,
        "eventi_senza_ore": sum(e["ore"] is None for e in dettaglio),
        "ore_svolte": ore_svolte,
        "percentuale": ore_perse / ore_svolte * 100 if ore_svolte else None,
        "limite_ore": round(limite),
        "ore_settimanali": settimanali,
        "ore_dall_orario": bool(ore_settimanali),
        "ore_rimaste": round(limite) - ore_perse,
        # Per la scheda: quanti giorni di scuola valgono le ore rimaste, e dove si arriva a fine anno a questo ritmo.
        "ore_al_giorno": ore_svolte / len(ore_giorno) if ore_giorno else None,
        "previsione": round(ore_perse / ore_svolte * settimanali * config.SETTIMANE_SCUOLA) if ore_svolte else None,
        "per_mese": [{"mese": m, "ore": o} for m, o in sorted(mesi.items())],
        "per_materia": [{"materia": m, "ore": o} for m, o in materie.most_common()],
    }


def _num(valore):
    return f"{valore:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def _quando(giorni):
    return "oggi" if giorni == 0 else "domani" if giorni == 1 else f"tra {giorni} giorni"


def consigli(statistiche, verifiche, materie_registro, carico_dati, oggi):
    """Elenco di punti su cui lavorare, dal più urgente. Ogni voce: {livello, titolo, testo}."""
    per_nome = {s.materia: s for s in statistiche}
    voci = []

    for s in statistiche:
        if s.insufficiente:
            serve = s.minimo_sufficienza
            come = (
                f"alla prossima prova serve almeno {_num(serve)}"
                if serve <= 10
                else "una sola prova non basta a recuperare: servono più voti alti"
            )
            voci.append(("critico", f"{s.materia}: media {_num(s.media)}", f"È insufficiente, {come}."))
    for verifica in verifiche:
        giorni = (verifica.data - oggi).days
        s = per_nome.get(verifica.materia)
        if not 0 <= giorni <= 7 or not verifica.materia:
            continue
        if s and (s.insufficiente or s.andamento == "giu" or s.media < config.SUFFICIENZA + 0.5):
            motivo = "è insufficiente" if s.insufficiente else "è in calo" if s.andamento == "giu" else "è appena sopra il 6"
            voci.append(("attenzione", f"Verifica di {verifica.materia} {_quando(giorni)}", f"La media ({_num(s.media)}) {motivo}: è la prova a cui dare la precedenza."))
    for s in statistiche:
        if s.andamento == "giu" and not s.insufficiente:
            voci.append(("attenzione", f"{s.materia}: in calo", f"Gli ultimi {config.VOTI_RECENTI} voti sono più bassi dei precedenti (media {_num(s.media)})."))
        if s.media_scritto is not None and s.media_orale is not None and abs(s.media_scritto - s.media_orale) >= 1:
            debole = "lo scritto" if s.media_scritto < s.media_orale else "l'orale"
            voci.append(("info", f"{s.materia}: divario tra scritto e orale", f"Scritto {_num(s.media_scritto)}, orale {_num(s.media_orale)}: il punto debole è {debole}."))
    for giorno in carico_dati["prossimi_giorni"]:
        if giorno["verifiche"] >= 2:
            giorni = (giorno["data"] - oggi).days
            voci.append(("attenzione", f"{GIORNI[giorno['data'].weekday()]} {giorno['data'].day}: {giorno['verifiche']} verifiche lo stesso giorno", f"Cade {_quando(giorni)}: conviene iniziare a ripassare in anticipo."))
    senza_voti = sorted(set(materie_registro) - set(per_nome))
    if statistiche and senza_voti:
        voci.append(("info", "Materie ancora senza voti", ", ".join(senza_voti) + "."))

    ordine = {"critico": 0, "attenzione": 1, "info": 2}
    voci.sort(key=lambda v: ordine[v[0]])
    return [{"livello": livello, "titolo": titolo, "testo": testo} for livello, titolo, testo in voci]
