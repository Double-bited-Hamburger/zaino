"""Sincronizzazione tra PC e telefono sulla stessa rete: il telefono cerca il PC e i due si scambiano i dati, cifrati.

Il PC resta in ascolto (solo se la sincronizzazione è attiva), il telefono lo cerca e gli manda la propria copia;
il PC la unisce alla sua e risponde con il risultato. L'unione dà lo stesso esito su entrambi, in qualunque ordine.
"""

import base64
import collections
import gzip
import hashlib
import hmac
import http.client
import ipaddress
import json
import re
import secrets
import socket
import threading
import time
import socketserver
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from cryptography.fernet import Fernet, InvalidToken

import archivio
import config
import profili

FILE = ("stato", "dashboard", "orario")  # i file di ogni profilo, senza .json
LIMITE = 10_000_000  # dimensione massima di uno scambio
CERCA, QUI = b"PCMP1?", b"PCMP1!"  # il telefono chiede «c'è il PC?», il PC risponde dimostrando di conoscere il codice
ATTESA_RICERCA = 1.5
# Un messaggio vale solo se è stato cifrato da poco e una volta sola: chi lo registra in rete non può rimandarlo dopo.
VALIDITA = 15 * 60
NONCE_RICORDATI = 200

revisione = 0  # cresce quando una sincronizzazione cambia i dati: la pagina aperta capisce di doverli rileggere
_ascolto = None  # (server, socket della ricerca, suo thread, segnale di stop) quando il PC è in ascolto
_in_corso = threading.Lock()
# Al massimo due scambi insieme: chi è sulla stessa Wi‑Fi non può riempire la memoria del PC di richieste.
_scambi = threading.BoundedSemaphore(2)
_visti = collections.OrderedDict()  # nonce dei messaggi già accettati
_blocco_visti = threading.Lock()


class ErroreSincronizzazione(Exception):
    pass


class CodiceSbagliato(ErroreSincronizzazione):
    pass


# ---------- impostazioni di questo dispositivo (non si sincronizzano) ----------

def _file():
    return profili.CARTELLA / "sincronizzazione.json"


def impostazioni():
    return archivio.leggi(_file()) or {}


def _ricorda(**valori):
    archivio.scrivi(_file(), {**impostazioni(), **valori})


def _pulisci_codice(codice):
    return re.sub(r"[^A-Z2-7]", "", codice.upper()) if isinstance(codice, str) else ""


def _mostra_codice(codice):
    return "-".join(codice[i:i + 5] for i in range(0, len(codice), 5))


def _indirizzo_locale():
    """L'indirizzo di questo dispositivo nella rete di casa (None se non è collegato)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # non invia nulla: serve solo a sapere da quale scheda di rete si esce
            return s.getsockname()[0]
    except OSError:
        return None


def stato():
    """Ciò che la pagina mostra nel riquadro «Sincronizzazione»."""
    salvate = impostazioni()
    codice = salvate.get("codice") or ""
    comune = {"disponibile": True, "attiva": bool(codice), "ultima": salvate.get("ultima"), "esito": salvate.get("esito"), "revisione": revisione}
    if config.ANDROID:
        return {**comune, "ruolo": "telefono", "pc": salvate.get("pc") or ""}
    return {**comune, "ruolo": "pc", "codice": _mostra_codice(codice), "indirizzo": _indirizzo_locale(), "in_ascolto": _ascolto is not None}


# ---------- cifratura ----------

def _chiave(scopo, codice):
    return hashlib.sha256(f"{scopo}|{codice}".encode()).digest()


def cifra(codice, dati, adesso=None):
    busta = {"inviato": int(adesso or time.time()), "nonce": secrets.token_hex(16), "dati": dati}
    testo = json.dumps(busta, ensure_ascii=False).encode()
    return Fernet(base64.urlsafe_b64encode(_chiave("sincronizza", codice))).encrypt(gzip.compress(testo))


def decifra(codice, cifrato, adesso=None):
    try:
        busta = json.loads(gzip.decompress(Fernet(base64.urlsafe_b64encode(_chiave("sincronizza", codice))).decrypt(cifrato)))
    except (InvalidToken, OSError, ValueError, TypeError):
        raise CodiceSbagliato("Codice di abbinamento sbagliato.") from None
    if not isinstance(busta, dict) or not isinstance(busta.get("dati"), dict) or not isinstance(busta.get("nonce"), str):
        raise ErroreSincronizzazione("Dati ricevuti non validi: aggiorna l'app su entrambi i dispositivi.")
    inviato = busta.get("inviato")
    if not isinstance(inviato, int) or abs((adesso or time.time()) - inviato) > VALIDITA:
        raise ErroreSincronizzazione("Messaggio scaduto: controlla che data e ora del PC e del telefono siano giuste.")
    with _blocco_visti:
        if busta["nonce"] in _visti:
            raise ErroreSincronizzazione("Messaggio già ricevuto: è stato rifiutato.")
        _visti[busta["nonce"]] = True
        while len(_visti) > NONCE_RICORDATI:
            _visti.popitem(last=False)
    return busta["dati"]


def _prova(codice, sfida):
    return hmac.new(_chiave("ricerca", codice), sfida, hashlib.sha256).digest()


# ---------- copia dei dati di questo dispositivo ----------

def _stato(grezzo):
    """Le spunte in forma regolare: «tolti» c'è solo se serve, così due copie uguali risultano uguali."""
    grezzo = grezzo if isinstance(grezzo, dict) else {}
    testi = lambda voce: {k: v for k, v in (grezzo.get(voce) if isinstance(grezzo.get(voce), dict) else {}).items() if isinstance(v, str)}
    pulito = {"fatti": testi("fatti")}
    if testi("tolti"):
        pulito["tolti"] = testi("tolti")
    return pulito


def istantanea():
    """Tutto ciò che si sincronizza: profili (con password), spunte e dati scaricati."""
    tutti, dati = {}, {}
    for profilo in profili.elenco():
        try:
            cartella = profili.cartella(profilo["id"])
        except profili.ProfiloNonValido:
            continue
        tutti[profilo["id"]] = {**profilo, "password": profili.password(profilo["id"])}
        dati[profilo["id"]] = {nome: archivio.leggi(cartella / f"{nome}.json") for nome in FILE}
        dati[profilo["id"]]["stato"] = _stato(dati[profilo["id"]]["stato"])
    return {"profili": tutti, "eliminati": dict(profili.eliminati()), "dati": dati}


def _controlla(copia):
    """Tiene di una copia ricevuta solo ciò che ha la forma giusta."""
    oggetto = lambda valore: valore if isinstance(valore, dict) else {}
    valido = lambda i: isinstance(i, str) and re.fullmatch(r"[0-9a-f]{8}", i)
    tutti = {
        i: p for i, p in oggetto(copia.get("profili")).items()
        if valido(i) and isinstance(p, dict) and p.get("id") == i and p.get("registro") in profili.REGISTRI
        and all(isinstance(p.get(campo), str) for campo in ("nome", "utente", "scuola", "password"))
        and (p.get("untis") is None or re.fullmatch(r"[a-z0-9-]+\.webuntis\.com", str(oggetto(p["untis"]).get("server"))))
    }
    dati = {}
    for i in tutti:
        suoi = oggetto(oggetto(copia.get("dati")).get(i))
        dati[i] = {nome: suoi.get(nome) if isinstance(suoi.get(nome), dict) else None for nome in FILE}
        dati[i]["stato"] = _stato(dati[i]["stato"])
    eliminati = {i: quando for i, quando in oggetto(copia.get("eliminati")).items() if valido(i) and isinstance(quando, str)}
    return {"profili": tutti, "eliminati": eliminati, "dati": dati}


# ---------- unione di due copie ----------

def _recente(a, b, campo):
    """Tra due versioni tiene quella con la data più recente; a parità sceglie sempre la stessa, in qualunque ordine arrivino."""
    if a is None or b is None or a == b:
        return a if b is None else b
    data = lambda x: x.get(campo) if isinstance(x.get(campo), str) else ""
    if data(a) != data(b):
        return a if data(a) > data(b) else b
    return max(a, b, key=lambda x: json.dumps(x, sort_keys=True, ensure_ascii=False))


def _unisci_stato(a, b):
    fatti, tolti = {}, {}
    for i in {*a["fatti"], *b["fatti"], *a.get("tolti", {}), *b.get("tolti", {})}:
        fatto = max(a["fatti"].get(i, ""), b["fatti"].get(i, ""))
        tolto = max(a.get("tolti", {}).get(i, ""), b.get("tolti", {}).get(i, ""))
        if fatto and fatto >= tolto:
            fatti[i] = fatto
        else:
            tolti[i] = tolto
    return _stato({"fatti": fatti, "tolti": tolti})


def _giorni(dashboard):
    nuvola = dashboard.get("nuvola") if dashboard else None
    return nuvola["giorni"] if isinstance(nuvola, dict) and isinstance(nuvola.get("giorni"), dict) else None


def _unisci_dashboard(a, b):
    scelto = _recente(a, b, "scaricato")
    altro = b if scelto is a else a
    # Nuvola si legge un giorno alla volta: i giorni letti da un dispositivo servono anche all'altro.
    if _giorni(scelto) is not None and _giorni(altro):
        scelto = {**scelto, "nuvola": {**scelto["nuvola"], "giorni": {**_giorni(altro), **_giorni(scelto)}}}
    return scelto


def _unisci_orario(a, b):
    scelto = _recente(a, b, "scaricato")
    altro = b if scelto is a else a
    viste = lambda orario: orario["viste"] if orario and isinstance(orario.get("viste"), dict) else {}
    if not viste(scelto) or not viste(altro):
        return scelto
    # Una variazione è «nuova» da quando l'ha vista il primo dei due dispositivi.
    prime = {k: min((v for v in (quando, viste(altro).get(k)) if isinstance(v, str) and v), default="") for k, quando in viste(scelto).items()}
    return {**scelto, "viste": prime}


def unisci(a, b):
    """L'unione di due copie. Dà lo stesso risultato scambiandole e non cambia ripetendola."""
    eliminati = {i: max(a["eliminati"].get(i, ""), b["eliminati"].get(i, "")) for i in {*a["eliminati"], *b["eliminati"]}}
    tutti, dati = {}, {}
    for i in dict.fromkeys([*a["profili"], *b["profili"]]):
        profilo = _recente(a["profili"].get(i), b["profili"].get(i), "modificato")
        if i in eliminati and eliminati[i] >= (profilo.get("modificato") or ""):
            continue
        altro = b["profili"].get(i) if profilo is a["profili"].get(i) else a["profili"].get(i)
        if not profilo["password"] and altro and altro["password"]:
            profilo = {**profilo, "password": altro["password"]}
        vuoti = {nome: None for nome in FILE} | {"stato": _stato(None)}
        suoi_a, suoi_b = a["dati"].get(i, vuoti), b["dati"].get(i, vuoti)
        suoi = {"stato": _unisci_stato(suoi_a["stato"], suoi_b["stato"]), "dashboard": _unisci_dashboard(suoi_a["dashboard"], suoi_b["dashboard"]),
                "orario": _unisci_orario(suoi_a["orario"], suoi_b["orario"])}
        # Dati scaricati prima che il profilo cambiasse account (o scuola dell'orario) non sono più i suoi.
        for nome, dal in (("dashboard", "dati_dal"), ("orario", "orario_dal")):
            if suoi[nome] and str(suoi[nome].get("scaricato") or "") < str(profilo.get(dal) or ""):
                suoi[nome] = None
        tutti[i], dati[i] = profilo, suoi
    return {"profili": tutti, "eliminati": eliminati, "dati": dati}


def _applica(locale, unione):
    """Scrive su questo dispositivo ciò che nell'unione è diverso da prima. True se è cambiato qualcosa."""
    cambiato = False
    for i in locale["profili"]:
        if i not in unione["profili"]:
            profili.elimina(i)
            cambiato = True
    for i, profilo in unione["profili"].items():
        vecchio = locale["profili"].get(i) or {}
        if profilo["password"] and profilo["password"] != vecchio.get("password"):
            profili.imposta_password(i, profilo["password"])
        for nome in FILE:
            nuovo, file = unione["dati"][i][nome], profili.cartella(i) / f"{nome}.json"
            if nuovo == locale["dati"].get(i, {}).get(nome):
                continue
            if nuovo is None:
                file.unlink(missing_ok=True)
            elif nome != "stato" or nuovo != _stato(None) or file.exists():
                archivio.scrivi(file, nuovo)
            cambiato = True
    senza_password = lambda tutti: [{k: v for k, v in p.items() if k != "password"} for p in tutti]
    # L'ordine dei profili di questo dispositivo resta com'è; quelli arrivati dall'altro si aggiungono in fondo.
    ordine = [i for i in locale["profili"] if i in unione["profili"]] + [i for i in unione["profili"] if i not in locale["profili"]]
    elenco = senza_password(unione["profili"][i] for i in ordine)
    if elenco != senza_password(locale["profili"].values()) or unione["eliminati"] != locale["eliminati"] or cambiato:
        profili.sostituisci(elenco, unione["eliminati"])
        cambiato = cambiato or elenco != senza_password(locale["profili"].values())
    return cambiato


def ricevi(remota, blocco):
    """Unisce una copia ricevuta a quella di questo dispositivo e salva il risultato. Restituisce (unione, cambiato)."""
    global revisione
    with blocco:
        locale = istantanea()
        unione = unisci(locale, _controlla(remota))
        cambiato = _applica(locale, unione)
        if cambiato:
            revisione += 1
    return unione, cambiato


# ---------- lato PC: in ascolto ----------

class _Gestore(BaseHTTPRequestHandler):
    timeout = 30
    blocco = None

    def _rispondi(self, codice, corpo=b""):
        self.send_response(codice)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_POST(self):
        try:
            lunghezza = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            lunghezza = 0
        codice = impostazioni().get("codice")
        if self.path != "/sync" or not codice or not 0 < lunghezza <= LIMITE:
            return self._rispondi(404)
        if not _scambi.acquire(blocking=False):
            return self._rispondi(503)
        try:
            try:
                remota = decifra(codice, self.rfile.read(lunghezza))
            except CodiceSbagliato:
                time.sleep(1)  # rallenta chi prova a indovinare
                return self._rispondi(403)
            except ErroreSincronizzazione as errore:
                # Il codice è giusto (il messaggio si è decifrato): si può dire al telefono cosa non va.
                return self._rispondi(400, str(errore).encode())
            unione, _ = ricevi(remota, self.blocco)
            _ricorda(ultima=profili.adesso(), esito="Sincronizzato con il telefono.")
            self._rispondi(200, cifra(codice, unione))
        finally:
            _scambi.release()

    def log_message(self, *args):
        pass


def _rispondi_alla_ricerca(presa, fermo):
    # Si controlla ogni mezzo secondo se l'ascolto è stato fermato: su Linux e macOS chiudere la presa non sveglia
    # chi è fermo in recvfrom, e la porta resterebbe occupata fino al prossimo messaggio.
    presa.settimeout(0.5)
    while not fermo.is_set():
        try:
            messaggio, mittente = presa.recvfrom(256)
        except TimeoutError:
            continue
        except ConnectionError:
            continue  # Windows segnala così una risposta arrivata a un telefono che aveva già chiuso: non è un problema
        except OSError:
            return  # ascolto fermato
        codice = impostazioni().get("codice")
        if codice and messaggio.startswith(CERCA) and len(messaggio) == len(CERCA) + 16:
            try:
                presa.sendto(QUI + _prova(codice, messaggio[len(CERCA):]), mittente)
            except OSError:
                pass


class ServerHTTP(ThreadingHTTPServer):
    """ThreadingHTTPServer senza la ricerca del nome del computer in rete (getfqdn), che non serve:
    su macOS può durare più di un minuto, e intanto l'app sembra bloccata."""

    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


def avvia_ascolto(blocco):
    """Il PC si mette in ascolto del telefono sulla rete locale. False se non serve o la porta è occupata."""
    global _ascolto
    if _ascolto or config.ANDROID or not impostazioni().get("codice"):
        return bool(_ascolto)
    presa = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        gestore = type("Gestore", (_Gestore,), {"blocco": blocco})
        app = ServerHTTP(("0.0.0.0", config.PORTA_SYNC), gestore)
    except OSError:
        presa.close()
        return False
    try:
        presa.bind(("0.0.0.0", config.PORTA_SYNC))
    except OSError:
        presa.close()
        app.server_close()
        return False
    app.daemon_threads = True
    threading.Thread(target=app.serve_forever, daemon=True).start()
    fermo = threading.Event()
    ricerca = threading.Thread(target=_rispondi_alla_ricerca, args=(presa, fermo), daemon=True)
    ricerca.start()
    _ascolto = (app, presa, ricerca, fermo)
    return True


def ferma_ascolto():
    global _ascolto
    if _ascolto:
        app, presa, ricerca, fermo = _ascolto
        _ascolto = None
        fermo.set()
        ricerca.join(timeout=2)
        presa.close()
        app.shutdown()
        app.server_close()


# ---------- lato telefono: cerca il PC e scambia ----------

def _trova_pc(codice, conosciuto):
    """L'indirizzo del PC in ascolto con lo stesso codice, oppure None. Chiede a quello già noto e a tutta la rete."""
    sfida = secrets.token_bytes(16)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as presa:
        presa.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        # A tutta la rete in due modi: non tutti i telefoni e i router lasciano passare il primo.
        mio = _indirizzo_locale()
        rete = mio.rsplit(".", 1)[0] + ".255" if mio else None
        for destinazione in dict.fromkeys(filter(None, (conosciuto, "255.255.255.255", rete))):
            try:
                presa.sendto(CERCA + sfida, (destinazione, config.PORTA_SYNC))
            except OSError:
                pass  # nessuna rete, o indirizzo non raggiungibile da qui
        scadenza = time.monotonic() + ATTESA_RICERCA
        while (resta := scadenza - time.monotonic()) > 0:
            presa.settimeout(resta)
            try:
                risposta, mittente = presa.recvfrom(256)
            except TimeoutError:
                return None
            except OSError:
                continue  # su Windows un indirizzo che rifiuta il messaggio si presenta così: si aspettano gli altri
            if hmac.compare_digest(risposta, QUI + _prova(codice, sfida)):
                return mittente[0]
    return None


def _scambia(indirizzo, codice, copia):
    connessione = http.client.HTTPConnection(indirizzo, config.PORTA_SYNC, timeout=30)
    try:
        connessione.request("POST", "/sync", body=cifra(codice, copia), headers={"Content-Type": "application/octet-stream"})
        risposta = connessione.getresponse()
        corpo = risposta.read(LIMITE + 1)
    finally:
        connessione.close()
    if risposta.status == 403:
        raise ErroreSincronizzazione("Codice di abbinamento sbagliato.")
    if risposta.status == 503:
        raise ErroreSincronizzazione("Il PC è occupato in un'altra sincronizzazione: riprova tra poco.")
    if risposta.status == 400:
        raise ErroreSincronizzazione("Il PC ha rifiutato i dati: " + corpo[:300].decode("utf-8", "replace"))
    if risposta.status != 200 or len(corpo) > LIMITE:
        raise ErroreSincronizzazione("Il PC ha risposto in modo inatteso.")
    return decifra(codice, corpo)


def sincronizza_ora(blocco):
    """Il telefono cerca il PC e scambia i dati. Restituisce {trovato, cambiato, esito}; se il PC non c'è non è un errore."""
    salvate = impostazioni()
    codice = salvate.get("codice")
    if not codice or not _in_corso.acquire(blocking=False):
        return {"trovato": False, "cambiato": False, "esito": salvate.get("esito")}
    try:
        indirizzo = _trova_pc(codice, salvate.get("pc"))
        if not indirizzo:
            return {"trovato": False, "cambiato": False, "esito": "PC non trovato: apri l'app sul PC e collega il telefono allo stesso Wi‑Fi."}
        with blocco:
            copia = istantanea()
        try:
            _, cambiato = ricevi(_scambia(indirizzo, codice, copia), blocco)
        except (ErroreSincronizzazione, OSError, http.client.HTTPException) as errore:
            esito = str(errore) if isinstance(errore, ErroreSincronizzazione) else "Collegamento con il PC interrotto."
            _ricorda(esito=esito)
            return {"trovato": True, "cambiato": False, "esito": esito, "errore": True}
        _ricorda(pc=indirizzo, ultima=profili.adesso(), esito="Sincronizzato con il PC.")
        return {"trovato": True, "cambiato": cambiato, "esito": "Sincronizzato con il PC."}
    finally:
        _in_corso.release()


# ---------- comandi della pagina ----------

def comando(corpo, blocco):
    """Esegue un'azione chiesta dal riquadro «Sincronizzazione» e restituisce il nuovo stato."""
    azione = corpo.get("azione")
    esito = {}
    if azione == "disattiva":
        ferma_ascolto()
        _file().unlink(missing_ok=True)
    elif azione == "attiva" and not config.ANDROID:
        if not impostazioni().get("codice"):
            _ricorda(codice=base64.b32encode(secrets.token_bytes(13)).decode()[:20])
        if not avvia_ascolto(blocco):
            raise ErroreSincronizzazione(f"Non riesco ad ascoltare sulla porta {config.PORTA_SYNC}: forse è usata da un altro programma.")
    elif azione == "abbina" and config.ANDROID:
        codice = _pulisci_codice(corpo.get("codice"))
        if len(codice) != 20:
            raise ErroreSincronizzazione("Il codice ha 20 caratteri: copialo dal riquadro «Sincronizzazione» dell'app sul PC.")
        indirizzo = corpo.get("indirizzo").strip() if isinstance(corpo.get("indirizzo"), str) else ""
        if indirizzo:
            try:
                # Solo indirizzi della rete di casa: l'app non deve poter essere puntata verso Internet.
                if not ipaddress.IPv4Address(indirizzo).is_private:
                    raise ValueError
            except ValueError:
                raise ErroreSincronizzazione("L'indirizzo del PC deve essere del tipo 192.168.1.20.") from None
        _ricorda(codice=codice, pc=indirizzo or impostazioni().get("pc") or "")
        esito = sincronizza_ora(blocco)
    elif azione == "ora" and config.ANDROID:
        esito = sincronizza_ora(blocco)
    else:
        raise ErroreSincronizzazione("Richiesta non valida.")
    return {**stato(), **esito}
