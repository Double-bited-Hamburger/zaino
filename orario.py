"""Converte l'orario grezzo di WebUntis, o quello scritto a mano nel profilo, in lezioni pronte da mostrare."""

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

import config

DOCENTE, MATERIA, AULA = 2, 3, 4

# Stato della lezione su WebUntis -> etichetta. Gli stati non elencati contano come lezione regolare.
STATI = {
    "SUBSTITUTION": "supplenza",
    "CANCEL": "annullata",
    "FREE": "annullata",
    "ROOMSUBSTITUTION": "cambio aula",
    "SHIFT": "spostata",
    "ADDITIONAL": "aggiuntiva",
    "EXAM": "verifica",
}


@dataclass
class Lezione:
    data: date
    inizio: str
    fine: str
    materia: str
    docenti: list = field(default_factory=list)
    aule: list = field(default_factory=list)
    stato: str = "regolare"
    nota: str = ""
    docenti_previsti: list = field(default_factory=list)  # chi doveva esserci, se c'è una supplenza
    aule_previste: list = field(default_factory=list)

    chiave: str = ""  # identifica la lezione e il suo stato tra un download e l'altro
    # Un'ora che WebUntis scrive come due materie (es. «Italiano-Storia»): il nome com'è scritto e le materie tra cui
    # scegliere. La scelta vale per quel giorno della settimana e quell'ora (vedi chiave_divisione).
    originale: str = ""
    scelte: list = field(default_factory=list)

    @property
    def variazione(self):
        return self.stato != "regolare"


def _ora(valore):
    return f"{valore // 100:02d}:{valore % 100:02d}"


def _solo_lettere(testo):
    return re.sub(r"[^A-Z]", "", (testo or "").upper())


def _sottosequenza(sigla, parola):
    lettere = iter(parola)
    return all(c in lettere for c in sigla)


def docenti_noti(dashboard):
    """Docenti conosciuti da Argo: [(nome da mostrare, cognome, iniziali dei nomi)]."""
    testo = lambda valore: valore if isinstance(valore, str) else ""
    elenco = lambda chiave: [v for v in dashboard.get(chiave) or [] if isinstance(v, dict)] if isinstance(dashboard.get(chiave), list) else []
    noti = {}
    for d in elenco("listaDocentiClasse"):
        cognome = _solo_lettere(testo(d.get("desCognome")))
        nomi = re.sub(r"\(.*?\)", "", testo(d.get("desNome"))).split()
        if cognome and nomi:
            noti[cognome] = (f"{nomi[0][0]}. {d['desCognome'].strip()}", cognome, {n[0].upper() for n in nomi})
    # Chi ha firmato il registro senza essere tra i docenti della classe (es. «F. ROSSI»).
    for lezione in elenco("registro"):
        trovato = re.match(r"\s*(\w)\.\s+(.+)", testo(lezione.get("docente")))
        if trovato and _solo_lettere(trovato.group(2)) and _solo_lettere(trovato.group(2)) not in noti:
            cognome = _solo_lettere(trovato.group(2))
            noti[cognome] = (lezione["docente"].strip(), cognome, {trovato.group(1).upper()})
    return list(noti.values())


def nome_docente(sigla, noti):
    """WebUntis in anonimo mostra solo sigle tipo «MRN_S»: le abbina ai docenti conosciuti da Argo.

    La parte prima del trattino abbrevia il cognome, quella dopo inizia con l'iniziale del nome.
    """
    cognome, _, nome = sigla.partition("_")
    cognome, nome = _solo_lettere(cognome), _solo_lettere(nome)
    trovati = [
        mostrato
        for mostrato, cognome_noto, iniziali in noti
        if cognome and nome and cognome_noto[0] == cognome[0] and _sottosequenza(cognome, cognome_noto) and nome[0] in iniziali
    ]
    return trovati[0] if len(trovati) == 1 else sigla


def _nome_materia(nome):
    nome = nome.strip().capitalize()
    for sigla in config.SIGLE:
        nome = re.sub(rf"\b{re.escape(sigla)}\b", sigla, nome, flags=re.I)
    return nome


def parti(materia):
    """Le materie di un'ora che ne mette insieme due o più («ITALIANO - STORIA», «Italiano/Storia»); [] se è una sola."""
    pezzi = [p.strip() for p in re.split(r"\s*[-/]\s*", materia or "") if p.strip()]
    if len(pezzi) < 2 or any(len(re.sub(r"[^A-Za-zÀ-ÿ]", "", p)) < 3 for p in pezzi):
        return []
    return [_nome_materia(p) for p in pezzi]


def chiave_divisione(materia, giorno, inizio):
    """Dove si ricorda quale materia è davvero un'ora doppia: «italiano-storia|0|12:00» (0 = lunedì)."""
    return f"{materia.strip().lower()}|{giorno}|{inizio}"


def _dividi(materia, giorno, inizio, divisione):
    """(materia da mostrare, nome originale, scelte possibili) per un'ora che può mettere insieme più materie."""
    scelte = parti(materia)
    # Prima la scelta fatta nella pagina, poi quella scritta a mano in config_locale.py (ORARIO_DIVISIONE).
    scelta = ((divisione or {}).get(chiave_divisione(materia, giorno, inizio))
              or config.ORARIO_DIVISIONE.get(materia.strip().lower(), {}).get((giorno, inizio)))
    return scelta or materia, materia.strip() if scelte else "", scelte


def converti(settimane, noti=(), divisione=None):
    """`settimane`: l'output di untis_client.scarica. Restituisce le lezioni in ordine di tempo.

    `divisione`: le ore doppie già divise dall'utente, {chiave_divisione: materia}.
    """
    lezioni = {}
    for settimana in settimane:
        try:
            elementi = {(e["type"], e["id"]): e for e in settimana["elementi"]}
            periodi = list(settimana["lezioni"])
        except (TypeError, KeyError):
            continue  # settimana in un formato inatteso: si mostra il resto

        def nome(tipo, id_elemento):
            elemento = elementi.get((tipo, id_elemento)) or {}
            if tipo == DOCENTE:
                return nome_docente(str(elemento.get("name") or "?"), noti)
            return str(elemento.get("longName") or elemento.get("name") or "?").strip()

        for periodo in periodi:
            try:
                lezione = _lezione(periodo, nome, divisione)
            except (TypeError, KeyError, ValueError, AttributeError):
                continue  # una lezione illeggibile non deve nascondere tutte le altre
            if lezione:
                lezioni[(lezione.data, lezione.inizio, lezione.materia, tuple(lezione.docenti))] = lezione
    return sorted(lezioni.values(), key=lambda l: (l.data, l.inizio, l.materia))


def _lezione(periodo, nome, divisione=None):
    """La lezione di un periodo WebUntis, oppure None se è tra quelle da nascondere."""
    parti = {DOCENTE: [], MATERIA: [], AULA: []}
    previsti = {DOCENTE: [], AULA: []}
    for e in periodo.get("elements") or []:
        if e["type"] not in parti:
            continue
        parti[e["type"]].append(nome(e["type"], e["id"]))
        if e.get("orgId") and e["type"] in previsti:
            previsti[e["type"]].append(nome(e["type"], e["orgId"]))
    materia = " / ".join(parti[MATERIA]) or str(periodo.get("lessonText") or "Lezione")
    if any(n.lower() in materia.lower() for n in config.ORARIO_NASCONDI):
        return None
    giorno = str(periodo["date"])
    data = date(int(giorno[:4]), int(giorno[4:6]), int(giorno[6:8]))
    inizio = _ora(periodo["startTime"])
    materia, originale, scelte = _dividi(materia, data.weekday(), inizio, divisione)
    testi = [t.strip() for t in (periodo.get("substText"), periodo.get("periodText")) if isinstance(t, str) and t.strip()]
    return Lezione(
        data=data,
        inizio=inizio,
        fine=_ora(periodo["endTime"]),
        materia=_nome_materia(materia),
        docenti=parti[DOCENTE],
        aule=parti[AULA],
        stato=STATI.get(periodo.get("cellState"), "regolare"),
        nota=" · ".join(dict.fromkeys(testi)),
        docenti_previsti=previsti[DOCENTE],
        aule_previste=previsti[AULA],
        originale=originale,
        scelte=scelte,
        chiave="|".join(
            [str(periodo.get("id")), str(periodo.get("cellState"))]
            + sorted(f"{e['type']}:{e['id']}" for e in periodo.get("elements") or [])
        ),
    )


def manuali(ore, oggi, divisione=None):
    """Le lezioni di questa settimana e della prossima dall'orario scritto a mano nel profilo (profili.imposta_orario).

    `ore`: [{giorno (0 = lunedì), inizio, fine, materia, aula, docente}], ogni settimana uguale.
    """
    lunedi = oggi - timedelta(days=oggi.weekday())
    if oggi.weekday() == 6:  # di domenica interessa già la settimana che inizia
        lunedi += timedelta(days=7)
    lezioni = []
    for settimana in range(2):
        for ora in ore:
            data = lunedi + timedelta(days=7 * settimana + ora["giorno"])
            materia, originale, scelte = _dividi(ora["materia"], ora["giorno"], ora["inizio"], divisione)
            lezioni.append(Lezione(
                data=data, inizio=ora["inizio"], fine=ora["fine"], materia=_nome_materia(materia),
                docenti=[ora["docente"]] if ora.get("docente") else [], aule=[ora["aula"]] if ora.get("aula") else [],
                originale=originale, scelte=scelte, chiave=f"manuale|{data.isoformat()}|{ora['inizio']}|{ora['materia']}",
            ))
    return sorted(lezioni, key=lambda l: (l.data, l.inizio, l.materia))


def ore_settimanali(lezioni):
    """Quante ore di lezione ha una settimana piena: la settimana con più ore tra quelle in orario (None se non si sa)."""
    per_settimana = {}
    for l in lezioni:
        if l.stato != "aggiuntiva":
            per_settimana.setdefault(l.data - timedelta(days=l.data.weekday()), set()).add((l.data, l.inizio))
    piu_piena = max((len(ore) for ore in per_settimana.values()), default=0)
    return piu_piena if piu_piena >= 10 else None  # meno di così è una settimana di vacanza o un orario a metà


def per_settimana(lezioni):
    """Raggruppa per settimana: [{inizio, fine, fasce: [(inizio, fine)], giorni: [date]}]."""
    settimane = {}
    for lezione in lezioni:
        lunedi = lezione.data - timedelta(days=lezione.data.weekday())
        settimana = settimane.setdefault(lunedi, {"inizio": lunedi, "fasce": set(), "giorni": set()})
        settimana["fasce"].add((lezione.inizio, lezione.fine))
        settimana["giorni"].add(lezione.data)
    risultati = []
    for lunedi, settimana in sorted(settimane.items()):
        giorni = sorted(settimana["giorni"])
        risultati.append({"inizio": lunedi, "fine": giorni[-1], "fasce": sorted(settimana["fasce"]), "giorni": giorni})
    return risultati
