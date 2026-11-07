"""Le circolari della scuola, dall'elenco pubblico su trasparenza-pa.net (il portale «Amministrazione trasparente» di Argo).

Non serve nessuna password: il sito è pubblico, e il suo codice cliente è lo stesso codice scuola del profilo Argo.
La cartella dell'anno («Circolari_2026-27») di solito sta in «Atti generali» (node 3); se la scuola le pubblica
altrove, nel profilo si incolla l'indirizzo della pagina. Stessa lettura del bot Telegram Circolari_TG.
"""

import html
import re
import unicodedata
from urllib.parse import parse_qs, urlsplit

import requests

from archivio import ErroreRegistro

BASE = "https://trasparenza-pa.net"
TIMEOUT = 25
INTESTAZIONI = {"User-Agent": "Zaino (app per il registro elettronico, sola lettura)"}
CARTELLA_PADRE = "3"  # «Atti generali», dove quasi tutte le scuole Argo mettono le cartelle «Circolari_AAAA-AA»
PAGINE = 2  # una pagina ha una ventina di circolari: le ultime due bastano a non perdersene nessuna tra un «Aggiorna» e l'altro

# Etichette ricavate dal titolo (come gli hashtag del bot). L'asterisco finale vale per qualsiasi desinenza.
ETICHETTE = [
    ("docenti", ["docent*", "dipartiment*", "collegio", "tutor", "referent*", "staff"]),
    ("personale", ["personale scolastico", "personale della scuola", "personale ata", "ata"]),
    ("studenti", ["student*", "alunn*"]),
    ("genitori", ["genitor*", "famigli*"]),
    ("convocazioni", ["convocazion*", "riunion*"]),
    ("cdc", ["cdc", "consiglio di classe", "consigli di classe", "coordinatori"]),
    ("rettifica", ["rettific*", "variazione circ*"]),
    ("uscite", ["uscita didattica", "uscite didattiche", "uscita presso", "visit*", "viaggi*"]),
    ("orario", ["orario", "orari"]),
    ("calendario", ["calendario"]),
    ("sciopero", ["scioper*"]),
    ("assemblea", ["assemble*"]),
    ("elezioni", ["elezion*"]),
    ("corsi", ["corso", "corsi", "formazion*"]),
    ("esami", ["esam*", "maturita"]),
    ("certificazioni", ["certificazion*"]),
    ("progetti", ["progetto", "progetti", "scambi*", "selezione", "candidatura", "bando", "borse di studio"]),
    ("orientamento", ["orientament*", "orientativ*", "open day"]),
    ("pcto", ["pcto", "stage", "alternanza"]),
    ("sport", ["sport", "sportiv*", "atleta"]),
    ("sicurezza", ["sicurezza", "evacuazion*"]),
]
MASSIMO_ETICHETTE = 8


class ErroreCircolari(ErroreRegistro):
    pass


def _senza_accenti(testo):
    return "".join(c for c in unicodedata.normalize("NFD", testo) if not unicodedata.combining(c)).lower()


def _regola(parola):
    jolly = parola.endswith("*")
    base = re.escape(_senza_accenti(parola.rstrip("*")))
    return re.compile(rf"(?<![a-z0-9]){base}{'[a-z]*' if jolly else ''}(?![a-z0-9])")


_REGOLE = [(nome, [_regola(p) for p in parole]) for nome, parole in ETICHETTE]
_CLASSE = re.compile(r"(?<![A-Za-z0-9])([1-5])([A-Z])([A-Za-z])?(?![A-Za-z0-9])")


def classi_citate(titolo):
    """Le classi nominate nel titolo, scritte come sul registro: «5AA» e «5Aa» → «5Aa»."""
    return list(dict.fromkeys(m[1] + m[2] + (m[3] or "").lower() for m in _CLASSE.finditer(titolo)))


def etichette(titolo):
    testo = _senza_accenti(titolo)
    return [nome for nome, regole in _REGOLE if any(r.search(testo) for r in regole)][:MASSIMO_ETICHETTE]


def _testo(frammento):
    # Due passate: nei titoli il sito codifica due volte alcuni caratteri («4&amp;#43;2»).
    return " ".join(html.unescape(html.unescape(re.sub(r"<[^>]*>", " ", frammento))).split())


def _numero_e_titolo(titolo):
    """«Circ_101 Convocazione…» → (101, «Convocazione…»)."""
    trovato = re.match(r"^Circ(?:olare)?[\s_.]*(?:n[.°]?\s*)?(\d+)[\s_.:–-]*(.*)$", titolo, re.IGNORECASE)
    if not trovato or not trovato[2]:
        return None, titolo
    return int(trovato[1]), trovato[2]


def _data_iso(giorno, ora=""):
    g, m, a = giorno.split("/")
    return f"{a}-{m}-{g}" + (f"T{ora}" if ora else "")


def leggi_circolari(pagina, codcli):
    """Le circolari di una pagina dell'elenco, dalla più recente: [{id, numero, titolo, descrizione, data, allegati, link, classi, etichette}]."""
    date_elenco = {int(i): d for d, i in re.findall(r"<small>(\d{2}/\d{2}/\d{4})</small>[\s\S]{0,600}?#modalDetail-(\d+)\"", pagina)}
    pezzi = re.split(r'id="modalDetail-(\d+)"', pagina)
    circolari = []
    for i in range(1, len(pezzi), 2):
        id_ = int(pezzi[i])
        blocco = pezzi[i + 1].split('class="modal-footer"')[0]
        titolo_html = re.search(r'<h4[^>]*class="modal-title"[^>]*>([\s\S]*?)</h4>', blocco)
        if not titolo_html:
            continue
        intero = _testo(titolo_html[1])
        numero, titolo = _numero_e_titolo(intero)
        pubblicato = re.search(r"Pubblicato il (\d{2}/\d{2}/\d{4})(?: (\d{2}:\d{2}))?", blocco)
        descrizione_html = re.search(r'class="ql-editor"[^>]*>([\s\S]*?)</div>', blocco)
        descrizione = _testo(descrizione_html[1]) if descrizione_html else ""
        allegati, visti = [], set()
        for file_id, nome in re.findall(r'<td scope="row"[^>]*>\s*<a[^>]*href="/action/download\.php\?file_id=(\d+)"[^>]*>([\s\S]*?)</a>', blocco):
            if file_id not in visti:
                visti.add(file_id)
                allegati.append({"nome": _testo(nome) or f"allegato-{file_id}.pdf", "url": f"{BASE}/action/download.php?file_id={file_id}"})
        allegati.sort(key=lambda a: 0 if a["nome"].lower().startswith("circ") else 1)  # il testo della circolare prima degli altri
        giorno = pubblicato[1] if pubblicato else date_elenco.get(id_, "")
        circolari.append({
            "id": id_,
            "numero": numero,
            "titolo": titolo,
            "descrizione": "" if descrizione.lower() == intero.lower() else descrizione,
            "data": _data_iso(giorno, pubblicato[2] or "" if pubblicato else "") if giorno else "",
            "allegati": allegati,
            "link": f"{BASE}/?codcli={codcli}&opc={id_}",
            "classi": classi_citate(titolo),
            "etichette": etichette(titolo),
        })
    return circolari


def controlla_lettura(pagina, circolari):
    """Se il sito cambia struttura è meglio un errore chiaro che un elenco vuoto o senza allegati."""
    if 'class="breadcrumb"' not in pagina:
        raise ErroreCircolari("il sito delle circolari ha risposto con una pagina inattesa (manutenzione?)", temporaneo=True)
    blocchi = len(re.findall(r'id="modalDetail-\d+"', pagina))
    if blocchi != len(circolari):
        raise ErroreCircolari(f"lette {len(circolari)} circolari su {blocchi}: il sito è cambiato")
    if circolari and not any(c["allegati"] for c in circolari) and "download.php" in pagina:
        raise ErroreCircolari("nessun allegato riconosciuto: il sito è cambiato")


def cartella_piu_recente(pagina):
    """Tra le cartelle «Circolari_2026-27» della pagina, il node di quella dell'anno più recente (o None)."""
    trovate = re.findall(r'href="[^"]*[?&](?:amp;)?node=(\d+)"[^>]*>\s*Circolari[\s_-]*(\d{4})\s*[-_/]\s*\d{2,4}\s*</a>', pagina, re.IGNORECASE)
    return max(trovate, key=lambda t: int(t[1]))[0] if trovate else None


def da_indirizzo(indirizzo):
    """(codcli, node) da un indirizzo di trasparenza-pa.net incollato nel profilo; None se non lo è."""
    parti = urlsplit(indirizzo.strip())
    if parti.scheme not in ("http", "https") or parti.hostname not in ("trasparenza-pa.net", "www.trasparenza-pa.net"):
        return None
    valori = parse_qs(parti.query)
    codcli, node = (valori.get(k, [""])[0] for k in ("codcli", "node"))
    if not re.fullmatch(r"[A-Za-z0-9]{2,20}", codcli) or not re.fullmatch(r"\d{0,12}", node):
        return None
    return codcli.upper(), node


def _pagina(codcli, node, numero=1):
    parametri = {"codcli": codcli, "node": node, **({"contentsPage": numero} if numero > 1 else {})}
    risposta = requests.get(BASE + "/", params=parametri, headers=INTESTAZIONI, timeout=TIMEOUT)
    if risposta.status_code != 200:
        raise ErroreCircolari(f"il sito delle circolari ha risposto HTTP {risposta.status_code}", temporaneo=risposta.status_code >= 500)
    return risposta.text


def scarica(codcli, node=""):
    """Le ultime circolari della scuola, dalla più recente. Senza node cerca la cartella dell'anno in «Atti generali»."""
    if not node:
        node = cartella_piu_recente(_pagina(codcli, CARTELLA_PADRE))
        if not node:
            raise ErroreCircolari("non trovo la cartella delle circolari della scuola: incolla nel profilo l'indirizzo della pagina "
                                  "delle circolari su trasparenza-pa.net")
    circolari = []
    for numero in range(1, PAGINE + 1):
        pagina = _pagina(codcli, node, numero)
        lette = leggi_circolari(pagina, codcli)
        controlla_lettura(pagina, lette)
        circolari += [c for c in lette if c["id"] not in {v["id"] for v in circolari}]
        if not lette:
            break
    circolari.sort(key=lambda c: (c["data"], c["id"]), reverse=True)
    return node, circolari
