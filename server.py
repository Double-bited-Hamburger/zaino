"""Server locale dell'app: serve la pagina e i dati, solo a questo computer."""

import hmac
import http.cookies
import json
import mimetypes
import os
import threading
import traceback
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import requests

import aggiornamenti
import archivio
import config
import dati
import pdf_compiti
import pdf_settimana
import profili
import sincronizza
import untis_client
from archivio import ErroreRegistro
from untis_client import UntisError

WEB = Path(config.WEB_DIR) if config.WEB_DIR else Path(__file__).parent / "web"
REGISTRO_ERRORI = (Path(config.DATI_DIR) if config.DATI_DIR else Path(__file__).parent) / "cache" / "errori.log"
# Il tema scelto nella pagina: sul telefono serve ai widget, che si vestono allo stesso modo (notifiche.widget).
PREFERENZE = (Path(config.DATI_DIR) if config.DATI_DIR else Path(__file__).parent) / "cache" / "preferenze.json"
TEMI = {"auto", "chiaro", "scuro", "quaderno", "terminale", "nothing", "ultra"}
INDIRIZZO = config.INDIRIZZO

# Il profilo in uso è uno solo per volta (vedi dati.attiva): le richieste si mettono in fila,
# ognuna con il profilo scelto nel proprio cookie.
BLOCCO = threading.RLock()
UN_ANNO = 365 * 86400
SENZA_GETTONE = """<!doctype html><meta charset="utf-8"><title>Zaino</title>
<p style="font:16px system-ui;margin:2em">Apri il registro con <b>zaino.exe</b> (o <b>avvia.bat</b>) su Windows o <b>avvia.sh</b> su Linux e macOS:
per proteggere i tuoi dati la pagina risponde solo al collegamento che apre l'app.</p>""".encode()
SICUREZZA = (
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "no-referrer"),
    ("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'"),
)


def annota_errore():
    """Salva l'errore in corso in cache/errori.log, così si può capire cosa è successo."""
    try:
        REGISTRO_ERRORI.parent.mkdir(exist_ok=True)
        if REGISTRO_ERRORI.exists() and REGISTRO_ERRORI.stat().st_size > 500_000:
            REGISTRO_ERRORI.unlink()  # non deve crescere all'infinito
        with REGISTRO_ERRORI.open("a", encoding="utf-8") as f:
            print(f"--- {datetime.now().isoformat(timespec='seconds')}", traceback.format_exc(), sep="\n", file=f)
    except OSError:
        pass


def _uguali(dato, segreto):
    """Confronto a tempo costante (non si può indovinare il segreto un carattere alla volta)."""
    return isinstance(dato, str) and hmac.compare_digest(dato.encode(), segreto.encode())


def protetto(gestore):
    """Un errore imprevisto diventa una risposta leggibile invece di una connessione interrotta."""
    def avvolto(self):
        try:
            gestore(self)
        except (BrokenPipeError, ConnectionError):
            pass  # il browser ha chiuso la connessione
        except Exception as errore:
            annota_errore()
            try:
                self._rispondi(500, {"errore": f"Errore interno ({type(errore).__name__}). I dettagli sono in cache/errori.log."})
            except OSError:
                pass
    return avvolto


class Gestore(BaseHTTPRequestHandler):
    def _rispondi(self, codice, corpo, tipo="application/json; charset=utf-8", intestazioni=()):
        if not isinstance(corpo, bytes):
            corpo = json.dumps(corpo, ensure_ascii=False).encode()
        self.send_response(codice)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        for nome, valore in (*SICUREZZA, *intestazioni):
            self.send_header(nome, valore)
        self.end_headers()
        self.wfile.write(corpo)

    def _host_locale(self):
        """Contro il «DNS rebinding»: un sito esterno non può presentarsi con un altro nome al posto di 127.0.0.1."""
        host = self.headers.get("Host", "")
        return host in (f"{INDIRIZZO}:{config.PORTA}", f"localhost:{config.PORTA}")

    def _locale(self):
        """Rifiuta le richieste che non arrivano dalla pagina dell'app. Anche altri programmi possono chiamare
        127.0.0.1: la pagina si fa riconoscere con il gettone segreto, che riceve aprendo il collegamento di main.py."""
        if not self._host_locale():
            return False
        return not config.GETTONE or _uguali(self._cookie("gettone"), config.GETTONE)

    def _accesso(self):
        """Il collegamento aperto da main.py porta il gettone nell'indirizzo («/?accesso=…»): giusto o no."""
        if not config.GETTONE or not self._host_locale():
            return False
        valore = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("accesso", [""])[0]
        return _uguali(valore, config.GETTONE)

    def _cookie(self, nome):
        try:
            return http.cookies.SimpleCookie(self.headers.get("Cookie", "")).get(nome).value
        except (http.cookies.CookieError, AttributeError):
            return None

    def _imposta_cookie(self, nome, valore, durata):
        return ("Set-Cookie", f"{nome}={valore}; Path=/; Max-Age={durata}; HttpOnly; SameSite=Strict")

    def _scegli_profilo(self):
        """Attiva il profilo indicato nel cookie di questa richiesta (da usare con BLOCCO preso)."""
        id_profilo = self._cookie("profilo")
        dati.attiva(profili.trova(id_profilo) if id_profilo else None, ricorda=False)

    def _panoramica(self):
        """Colpo d'occhio di tutti i profili, dai dati già scaricati. Serve BLOCCO."""
        corrente = dati.PROFILO
        carte = []
        try:
            for profilo in profili.elenco():
                dati.attiva(profilo, ricorda=False)
                grezzi = dati.carica()
                carta = {"id": profilo["id"], "nome": profilo["nome"], "registro": profilo["registro"]}
                if grezzi:
                    carta.update(dati.riassunto(dati.elabora(grezzi), dati.leggi_stato()))
                else:
                    carta["vuoto"] = True
                carte.append(carta)
        finally:
            dati.attiva(corrente, ricorda=False)
        return {"profili": carte}

    def _pagina(self):
        if not dati.PROFILO:
            return {"senza_profilo": True, "vuoto": True, "stato": {"fatti": {}}}
        comuni = {"stato": dati.leggi_stato(), "profilo": dati.PROFILO}
        dati_grezzi = dati.carica()
        if not dati_grezzi:
            return {"vuoto": True, **comuni}
        return {**dati.elabora(dati_grezzi), **comuni}

    def _profili(self):
        elenco = profili.elenco()
        studenti = {p["id"]: profili.studenti(p["id"]) for p in elenco if p.get("registro") == "classeviva"}
        return {"profili": elenco, "attivo": (dati.PROFILO or {}).get("id"), "ultimo": profili.ultimo(), "registri": profili.REGISTRI,
                "studenti": {i: s for i, s in studenti.items() if s}, "android": config.ANDROID, "versione": config.VERSIONE}

    @protetto
    def do_GET(self):
        percorso = self.path.split("?")[0]
        if percorso == "/" and self._accesso():
            # Il gettone passa nel cookie e sparisce dall'indirizzo.
            return self._rispondi(302, b"", "text/plain", (("Location", "/"), self._imposta_cookie("gettone", config.GETTONE, UN_ANNO)))
        if not self._locale():
            if percorso.startswith("/api/") or not self._host_locale():
                return self._rispondi(403, {"errore": "Accesso non consentito."})
            return self._rispondi(403, SENZA_GETTONE, "text/html; charset=utf-8")
        if percorso == "/api/aggiornamenti":
            # Fuori da BLOCCO: la risposta di GitHub può tardare, e la pagina deve continuare a rispondere.
            return self._rispondi(200, aggiornamenti.stato())
        with BLOCCO:
            self._scegli_profilo()
            self._get(percorso)

    def _get(self, percorso):
        if percorso == "/api/panoramica":
            return self._rispondi(200, self._panoramica())
        if percorso == "/api/dati":
            return self._rispondi(200, self._pagina())
        if percorso == "/api/profili":
            return self._rispondi(200, self._profili())
        if percorso == "/api/sincronizzazione":
            return self._rispondi(200, sincronizza.stato())
        if percorso == "/api/untis/scuole":
            testo = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("q", [""])[0].strip()[:60]
            try:
                return self._rispondi(200, {"scuole": untis_client.cerca_scuole(testo) if len(testo) >= 3 else []})
            except requests.RequestException:
                return self._rispondi(502, {"errore": "WebUntis non è raggiungibile."})
        if percorso == "/api/esporta-compiti":
            if not dati.PROFILO or not dati.carica():
                return self._rispondi(404, {"errore": "Nessun dato scaricato: premi «Aggiorna»."})
            try:
                pdf = pdf_compiti.genera(self._pagina())
            except ValueError as errore:
                return self._rispondi(404, {"errore": str(errore)})
            return self._rispondi(200, pdf, "application/pdf", (("Content-Disposition", f'inline; filename="compiti-{datetime.now():%Y-%m-%d}.pdf"'),))
        if percorso == "/api/pdf":
            indice = self.path.partition("settimana=")[2]
            try:
                pdf = pdf_settimana.genera(self._pagina(), int(indice) if indice.isdigit() else 0)
            except (ValueError, KeyError) as errore:
                return self._rispondi(404, {"errore": str(errore)})
            return self._rispondi(200, pdf, "application/pdf")
        file = (WEB / (percorso.lstrip("/") or "index.html")).resolve()
        if WEB.resolve() not in file.parents or not file.is_file():
            return self._rispondi(404, {"errore": "Non trovato."})
        tipo = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
        self._rispondi(200, file.read_bytes(), f"{tipo}; charset=utf-8")

    @protetto
    def do_POST(self):
        # L'intestazione personalizzata impedisce a un altro sito di chiamare l'app dal browser.
        if not self._locale() or self.headers.get("X-Parser-Compiti") != "1":
            return self._rispondi(403, {"errore": "Accesso non consentito."})
        try:
            lunghezza = int(self.headers.get("Content-Length") or 0)
            # 20 kB: ci sta l'orario scritto a mano più lungo (profili.MASSIMO_ORE).
            corpo = json.loads(self.rfile.read(min(lunghezza, 20_000)) or b"{}") if 0 <= lunghezza <= 20_000 else None
        except ValueError:
            corpo = None
        if not isinstance(corpo, dict):
            return self._rispondi(400, {"errore": "Richiesta non valida."})

        if self.path == "/api/tema":
            if corpo.get("tema") not in TEMI:
                return self._rispondi(400, {"errore": "Tema sconosciuto."})
            archivio.scrivi(PREFERENZE, {"tema": corpo["tema"]})
            return self._rispondi(200, {"ok": True})
        if self.path == "/api/sincronizzazione":
            # Fuori da BLOCCO: mentre il telefono cerca il PC in rete, la pagina deve continuare a rispondere.
            try:
                return self._rispondi(200, sincronizza.comando(corpo, BLOCCO))
            except sincronizza.ErroreSincronizzazione as errore:
                return self._rispondi(400, {"errore": str(errore)})
        if self.path == "/api/aggiornamenti":
            return self._aggiornamenti(corpo)
        with BLOCCO:
            self._scegli_profilo()
            self._post(corpo)

    def _aggiornamenti(self, corpo):
        azione = corpo.get("azione")
        if azione == "controlla":
            return self._rispondi(200, aggiornamenti.stato(forza=True))
        if azione == "automatico":
            return self._rispondi(200, aggiornamenti.imposta(bool(corpo.get("attivo"))))
        if azione != "installa":
            return self._rispondi(400, {"errore": "Richiesta non valida."})
        try:
            with BLOCCO:  # niente scaricamenti dal registro a metà mentre l'app si sostituisce
                versione = aggiornamenti.installa()
        except aggiornamenti.ErroreAggiornamento as errore:
            return self._rispondi(400, {"errore": str(errore)})
        self._rispondi(200, {"ok": True, "versione": versione})
        # La versione nuova è partita e aspetta la porta: questa si chiude appena la risposta è arrivata alla pagina.
        threading.Timer(1.0, os._exit, (0,)).start()

    def _post(self, corpo):
        if self.path == "/api/aggiorna":
            # L'orario è indipendente dal registro: se WebUntis non risponde si prosegue lo stesso.
            avviso = None
            try:
                dati.scarica_orario()
            except UntisError as errore:
                avviso = f"Orario non aggiornato: {errore}"
            except requests.RequestException:
                avviso = "Orario non aggiornato: WebUntis non è raggiungibile."
            except Exception:
                annota_errore()
                avviso = "Orario non aggiornato per un errore imprevisto (dettagli in cache/errori.log)."
            try:
                scaricati = dati.scarica()
                grezzi = scaricati.get("classeviva") if isinstance(scaricati, dict) else None
                extra = grezzi.get("avviso") if isinstance(grezzi, dict) and isinstance(grezzi.get("avviso"), str) else None
                avviso = " ".join(filter(None, (avviso, extra))) or None  # per esempio: account con più studenti
            except ErroreRegistro as errore:
                return self._rispondi(502, {"errore": str(errore)})
            except requests.RequestException:
                return self._rispondi(502, {"errore": "Impossibile raggiungere il registro: controlla la connessione."})
            return self._rispondi(200, {**self._pagina(), "avviso": avviso})
        if self.path == "/api/profili/attiva":
            profilo = profili.trova(corpo.get("id")) if corpo.get("id") else None
            if corpo.get("id") and not profilo:
                return self._rispondi(404, {"errore": "Profilo non trovato."})
            dati.attiva(profilo)  # lo ricorda anche come ultimo usato
            cookie = self._imposta_cookie("profilo", profilo["id"] if profilo else "", 365 * 86400 if profilo else 0)
            return self._rispondi(200, self._profili(), intestazioni=(cookie,))
        if self.path == "/api/profili":
            try:
                profilo = profili.salva(corpo.get("profilo"), corpo.get("id") if isinstance(corpo.get("id"), str) else None)
            except profili.ProfiloNonValido as errore:
                return self._rispondi(400, {"errore": str(errore)})
            if dati.PROFILO and dati.PROFILO["id"] == profilo["id"]:
                dati.attiva(profilo, ricorda=False)
            return self._rispondi(200, {**self._profili(), "salvato": profilo["id"]})
        if self.path == "/api/profili/elimina":
            try:
                profili.cartella(corpo.get("id"))
            except profili.ProfiloNonValido as errore:
                return self._rispondi(400, {"errore": str(errore)})
            if dati.PROFILO and dati.PROFILO["id"] == corpo["id"]:
                dati.attiva(None)
            profili.elimina(corpo["id"])
            return self._rispondi(200, self._profili())
        if self.path == "/api/orario":
            # L'orario scritto a mano ({"ore": [...]}) o la scelta per un'ora doppia ({"chiave", "materia"}; "" = togli).
            if not dati.PROFILO:
                return self._rispondi(409, {"errore": "Scegli prima un profilo."})
            try:
                if "ore" in corpo:
                    profilo = profili.imposta_orario(dati.PROFILO["id"], ore=corpo["ore"])
                else:
                    profilo = profili.imposta_orario(dati.PROFILO["id"], divisione=(corpo.get("chiave"), corpo.get("materia") or ""))
            except profili.ProfiloNonValido as errore:
                return self._rispondi(400, {"errore": str(errore)})
            dati.attiva(profilo, ricorda=False)
            return self._rispondi(200, self._pagina())
        if self.path == "/api/stato":
            if not dati.PROFILO:
                return self._rispondi(409, {"errore": "Scegli prima un profilo."})
            if not isinstance(corpo.get("id"), str) or not 0 < len(corpo["id"]) <= 64:
                return self._rispondi(400, {"errore": "Richiesta non valida."})
            return self._rispondi(200, dati.segna_compito(corpo["id"], bool(corpo.get("fatto"))))
        self._rispondi(404, {"errore": "Non trovato."})

    def log_message(self, *args):
        pass


def avvia(porta=None):
    """Avvia il server; solleva OSError se la porta è già occupata (app già aperta)."""
    return sincronizza.ServerHTTP((INDIRIZZO, config.PORTA if porta is None else porta), Gestore)
