"""Client per l'API usata dall'app Argo didUP Famiglia (sola lettura)."""

import base64
import hashlib
import json
import re
import secrets
import string
from datetime import datetime, timedelta
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

import requests

from archivio import CredenzialiRifiutate, ErroreRegistro

CLIENT_ID = "72fd6dea-d0ab-4bb9-8eaa-3ac24c84886c"
CLIENT_VERSION = "1.30.2"
STORE_URL = "https://itunes.apple.com/lookup?bundleId=it.argosoft.didup.famiglia.new&country=it"
REDIRECT_URI = "it.argosoft.didup.famiglia.new://login-callback"
SCOPES = "openid offline profile user.roles argo"
AUTH_URL = "https://auth.portaleargo.it/oauth2/auth"
TOKEN_URL = "https://auth.portaleargo.it/oauth2/token"
LOGIN_URL = "https://www.portaleargo.it/auth/sso/login"
API_URL = "https://www.portaleargo.it/appfamiglia/api/rest/"
TIMEOUT = 30


class ArgoError(ErroreRegistro):
    pass


def _random_string(length):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _format_date(date):
    return date.strftime("%Y-%m-%d %H:%M:%S.") + f"{date.microsecond // 1000:03d}"


def _versione_store():
    """Versione corrente dell'app: Argo rifiuta i client con una versione vecchia."""
    try:
        return requests.get(STORE_URL, timeout=TIMEOUT).json()["results"][0]["version"]
    except (requests.RequestException, ValueError, LookupError):
        return None


def _query_param(url, name):
    return parse_qs(urlsplit(url).query).get(name, [None])[0]


_SENZA_CHIUSURA = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class _PaginaAccesso(HTMLParser):
    """Dalle pagine dell'accesso di Argo: il link «Continua» e i riquadri d'avviso visibili («Username e/o password non validi»)."""

    def __init__(self):
        super().__init__()
        self.href = None
        self.avvisi = []
        self._aperti = []  # per ogni tag aperto: True se è (o sta dentro) un avviso visibile
        self._testo = []

    def handle_starttag(self, tag, attrs):
        attributi = dict(attrs)
        if tag == "a" and "data-auth-app-redirect" in attributi:
            self.href = attributi.get("href")
        if tag in _SENZA_CHIUSURA:
            return
        classi = (attributi.get("class") or "").split()
        nascosto = "display:none" in (attributi.get("style") or "").replace(" ", "")
        dentro = bool(self._aperti) and self._aperti[-1]
        if not dentro and "alert" in classi and not nascosto:
            self._testo = []
            dentro = True
        self._aperti.append(dentro)

    def handle_endtag(self, tag):
        if tag in _SENZA_CHIUSURA or not self._aperti:
            return
        era_dentro = self._aperti.pop()
        if era_dentro and not (self._aperti and self._aperti[-1]):
            testo = " ".join(" ".join(self._testo).split())
            if testo:
                self.avvisi.append(testo)

    def handle_data(self, data):
        if self._aperti and self._aperti[-1]:
            self._testo.append(data)


def _leggi_pagina(html):
    pagina = _PaginaAccesso()
    try:
        pagina.feed(html or "")
    except Exception:  # una pagina malformata non deve diventare un errore incomprensibile
        pass
    return pagina


def _link_continua(html):
    """Il link del pulsante «Continua» della pagina «Accesso completato», che Argo mostra al posto di un redirect."""
    return _leggi_pagina(html).href


def _errore_pagina(risposta):
    """L'errore giusto per una pagina dell'accesso che non porta avanti: credenziali sbagliate solo se lo dice Argo."""
    stato = getattr(risposta, "status_code", 200)
    if stato == 429:
        return ArgoError("Argo ha ricevuto troppi tentativi di accesso: aspetta qualche minuto e riprova.", temporaneo=True)
    if stato >= 500:
        return ArgoError(f"Argo non risponde in questo momento (HTTP {stato}): riprova tra qualche minuto.", temporaneo=True)
    avvisi = _leggi_pagina(risposta.text).avvisi
    for avviso in avvisi:
        if re.search(r"non valid|errat|sbagliat|credenziali", avviso, re.IGNORECASE):
            return CredenzialiRifiutate(
                f"Argo dice: «{avviso[:120]}». Controlla codice scuola, nome utente e password: "
                "devono essere gli stessi che usi per entrare in didUP Famiglia."
            )
    if avvisi:
        return ArgoError(f"Argo non ha completato l'accesso: «{avvisi[0][:200]}»")
    return ArgoError(
        f"Argo ha mostrato una pagina inattesa durante l'accesso (HTTP {stato}): riprova tra poco. "
        "Se succede sempre, segnalalo nelle issue del progetto.",
        temporaneo=True,
    )


class ArgoClient:
    def __init__(self, school_code, username, password):
        self.school_code = school_code
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.token = None
        self.token_expire = None
        self.login_data = None
        self.version = CLIENT_VERSION

    def _get_code(self, code_verifier):
        digest = hashlib.sha256(code_verifier.encode()).digest()
        challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
        params = {
            "redirect_uri": REDIRECT_URI,
            "client_id": CLIENT_ID,
            "response_type": "code",
            "prompt": "login",
            "state": _random_string(22),
            "nonce": _random_string(22),
            "scope": SCOPES,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        res = self.session.get(
            f"{AUTH_URL}?{urlencode(params)}", allow_redirects=False, timeout=TIMEOUT
        )
        login_challenge = _query_param(res.headers.get("location", ""), "login_challenge")
        if not login_challenge:
            if getattr(res, "status_code", 200) >= 500:
                raise _errore_pagina(res)
            raise ArgoError("Argo non ha restituito la pagina di login: riprova tra poco (se succede sempre, l'API potrebbe essere cambiata).", temporaneo=True)

        res = self.session.post(
            LOGIN_URL,
            data={
                "challenge": login_challenge,
                "client_id": CLIENT_ID,
                "famiglia_customer_code": self.school_code,
                "login": "true",
                "password": self.password,
                "username": self.username,
            },
            allow_redirects=False,
            timeout=TIMEOUT,
        )
        # I redirect vanno seguiti a mano: l'ultimo punta allo schema dell'app.
        for _ in range(8):
            location = res.headers.get("location") or _link_continua(res.text)
            if not location:
                raise _errore_pagina(res)
            location = urljoin(res.url, location)
            if location.startswith(REDIRECT_URI):
                code = _query_param(location, "code")
                if not code:
                    raise ArgoError(f"Login non completato: {_query_param(location, 'error_description')}")
                return code
            res = self.session.get(location, allow_redirects=False, timeout=TIMEOUT)
        raise ArgoError("Troppi redirect durante il login.")

    def _get_token(self):
        code_verifier = _random_string(43)
        code = self._get_code(code_verifier)
        res = self.session.post(
            TOKEN_URL,
            data={
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": REDIRECT_URI,
                "code_verifier": code_verifier,
                "client_id": CLIENT_ID,
            },
            timeout=TIMEOUT,
        )
        try:
            data = res.json()
            if "error" in data:
                raise ArgoError(f"{data['error']} {data.get('error_description', '')}")
            self.token_expire = datetime.now() + timedelta(seconds=data["expires_in"])
            data["access_token"]
        except (ValueError, KeyError, TypeError):
            raise ArgoError(f"Argo non ha completato l'accesso (HTTP {res.status_code}): riprova tra poco.", temporaneo=True)
        self.token = data

    def _api(self, path, body=None):
        headers = {
            "accept": "application/json",
            "argo-client-version": self.version,
            "authorization": f"Bearer {self.token['access_token']}",
            "x-date-exp-auth": _format_date(self.token_expire),
        }
        if self.login_data:
            headers["x-auth-token"] = self.login_data["token"]
            headers["x-cod-min"] = self.login_data["codMin"]
        res = self.session.request(
            "GET" if body is None else "POST",
            API_URL + path,
            headers=headers,
            json=body,
            timeout=TIMEOUT,
        )
        try:
            data = res.json()
        except ValueError:
            data = None
        if not isinstance(data, dict):
            raise ArgoError(f"Argo ha dato una risposta illeggibile (/{path}, HTTP {res.status_code}): riprova tra poco.", temporaneo=True)
        if not data.get("success") or "data" not in data:
            if "ultima versione" in (data.get("msg") or "") and self.version == CLIENT_VERSION:
                self.version = _versione_store() or CLIENT_VERSION
                if self.version != CLIENT_VERSION:
                    return self._api(path, body)
            raise ArgoError(f"Argo ha risposto con un errore (/{path}): {data.get('msg') or res.status_code}", temporaneo=res.status_code >= 500)
        return data["data"]

    def login(self):
        self._get_token()
        profili = self._api(
            "login",
            {
                "lista-opzioni-notifiche": "{}",
                "lista-x-auth-token": "[]",
                "clientID": _random_string(163),
            },
        )
        try:
            self.login_data = {"token": profili[0]["token"], "codMin": profili[0]["codMin"], "opzioni": profili[0].get("opzioni") or []}
        except (KeyError, IndexError, TypeError, AttributeError):
            raise ArgoError("Nessun profilo associato a questo account.")

    def dashboard(self):
        """Restituisce (profilo, dashboard) con i dati di tutto l'anno scolastico."""
        profilo = self._api("profilo")
        try:
            inizio = datetime.fromisoformat(profilo["anno"]["dataInizio"][:10])
            opzioni = {o["chiave"]: o["valore"] for o in self.login_data["opzioni"]}
        except (KeyError, TypeError, ValueError):
            raise ArgoError("Argo ha cambiato il formato del profilo: lo script va aggiornato.")
        data = self._api(
            "dashboard/dashboard",
            {
                "dataultimoaggiornamento": _format_date(inizio),
                "opzioni": json.dumps(opzioni),
            },
        )
        try:
            dashboard = data["dati"][0]
        except (KeyError, IndexError, TypeError):
            dashboard = None
        if not isinstance(dashboard, dict):
            raise ArgoError("Argo ha risposto senza i dati del registro: riprova tra poco.", temporaneo=True)
        return profilo, dashboard
