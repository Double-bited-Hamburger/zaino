"""Client per l'API usata dall'app Argo didUP Famiglia (sola lettura)."""

import base64
import hashlib
import json
import secrets
import string
from datetime import datetime, timedelta
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

import requests

from archivio import ErroreRegistro

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


class _PaginaCompletato(HTMLParser):
    href = None

    def handle_starttag(self, tag, attrs):
        attributi = dict(attrs)
        if tag == "a" and "data-auth-app-redirect" in attributi:
            self.href = attributi.get("href")


def _link_continua(html):
    """Il link del pulsante «Continua» della pagina «Accesso completato», che Argo mostra al posto di un redirect."""
    pagina = _PaginaCompletato()
    pagina.feed(html)
    return pagina.href


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
            raise ArgoError("Argo non ha restituito la pagina di login (API cambiata?).")

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
                raise ArgoError(
                    "Login rifiutato: controlla codice scuola, utente e password del profilo."
                )
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
            raise ArgoError(f"Argo non ha completato l'accesso (HTTP {res.status_code}): riprova tra poco.")
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
            raise ArgoError(f"Risposta non valida da /{path} (HTTP {res.status_code}).")
        if not data.get("success") or "data" not in data:
            if "ultima versione" in (data.get("msg") or "") and self.version == CLIENT_VERSION:
                self.version = _versione_store() or CLIENT_VERSION
                if self.version != CLIENT_VERSION:
                    return self._api(path, body)
            raise ArgoError(f"Errore da /{path}: {data.get('msg') or res.status_code}")
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
            raise ArgoError("Argo ha risposto senza i dati del registro: riprova tra poco.")
        return profilo, dashboard
