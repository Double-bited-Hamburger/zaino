"""Client per il registro Nuvola (Madisoft), tramite l'API usata dall'area studente/tutore (sola lettura)."""

import html
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import requests

from archivio import CredenzialiRifiutate, ErroreRegistro

BASE = "https://nuvola.madisoft.it"
ACCESSO = f"{BASE}/connect/authentication-service"
API = f"{BASE}/api-studente/v1"
TIMEOUT = 30
BROWSER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"

# Compiti e lezioni si leggono un giorno alla volta: quanti giorni indietro e avanti chiedere.
GIORNI_INDIETRO = 30
GIORNI_AVANTI = 21
RICHIESTE_INSIEME = 4


class NuvolaError(ErroreRegistro):
    pass


def _valori(risposta):
    """Le API di Nuvola avvolgono gli elenchi in {"valori": [...]}; alcune restituiscono direttamente la lista."""
    if isinstance(risposta, dict):
        risposta = risposta.get("valori", risposta.get("data", [risposta]))
    return [v for v in risposta if isinstance(v, dict)] if isinstance(risposta, list) else []


class NuvolaClient:
    def __init__(self, utente, password):
        self.utente = utente
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": BROWSER, "Accept-Language": "it-IT,it;q=0.9"})
        self.alunno = None

    def login(self):
        # 1. Nuvola rimanda alla pagina di accesso (Keycloak), che contiene l'indirizzo a cui inviare le credenziali.
        pagina = self.session.get(ACCESSO, timeout=TIMEOUT)
        if getattr(pagina, "status_code", 200) >= 500:
            raise NuvolaError(f"Nuvola non risponde in questo momento (HTTP {pagina.status_code}): riprova tra qualche minuto.", temporaneo=True)
        trovato = re.search(r'"loginAction"\s*:\s*"([^"]+)"', pagina.text) or re.search(r'<form[^>]+action="([^"]+)"', pagina.text)
        if not trovato:
            raise NuvolaError("Pagina di accesso di Nuvola non riconosciuta: riprova tra poco (se succede sempre, il sito potrebbe essere cambiato).", temporaneo=True)
        azione = html.unescape(trovato.group(1).replace("\\/", "/").replace("\\u0026", "&"))

        # 2. Invio delle credenziali: se sono giuste si torna su Nuvola, altrimenti si resta sulla pagina di accesso.
        esito = self.session.post(azione, data={"username": self.utente, "password": self.password, "credentialId": ""}, timeout=TIMEOUT)
        if not esito.url.startswith(BASE):
            if getattr(esito, "status_code", 200) >= 500:
                raise NuvolaError(f"Nuvola non risponde in questo momento (HTTP {esito.status_code}): riprova tra qualche minuto.", temporaneo=True)
            raise CredenzialiRifiutate("Login rifiutato: Nuvola non ha accettato nome utente e password. Controlla che siano quelli con cui entri in Nuvola.")

        # 3. L'area riservata rilascia il token per le API (vale sia per gli studenti sia per i tutori).
        risposta = self.session.get(f"{API}/login-from-web", timeout=TIMEOUT, allow_redirects=False)
        try:
            dati = risposta.json()
            token = dati.get("token") if isinstance(dati, dict) else dati
        except ValueError:
            token = None
        if risposta.status_code != 200 or not isinstance(token, str) or not token:
            raise NuvolaError("Accesso riuscito ma Nuvola non ha rilasciato il token: l'account è di uno studente o di un tutore?")
        self.session.headers["Authorization"] = f"Bearer {token}"

        alunni = _valori(self._api("alunni"))
        if not alunni or "id" not in alunni[0]:
            raise NuvolaError("Nessuno studente associato a questo account.")
        self.alunno = alunni[0]
        if self.alunno.get("apiAttive") is False:
            raise NuvolaError("La scuola non ha attivato la consultazione dei dati per questo account.")

    def _api(self, percorso):
        """Una chiamata all'API; None se la voce non esiste o la scuola l'ha disattivata."""
        parametri = {"contextAlunno": self.alunno["id"]} if self.alunno else None
        risposta = self.session.get(f"{API}/{percorso}", params=parametri, timeout=TIMEOUT, allow_redirects=False)
        if risposta.status_code == 401 or risposta.is_redirect:
            raise NuvolaError("Sessione di Nuvola scaduta: riprova.")
        if risposta.status_code != 200:
            return None  # 403 = sezione disattivata dalla scuola, 404 = sezione inesistente
        try:
            return risposta.json()
        except ValueError:
            return None

    def _alunno(self, percorso):
        return self._api(f"alunno/{self.alunno['id']}/{percorso}")

    def _giorno(self, giorno):
        """Compiti da consegnare quel giorno e ore di lezione (svolte o programmate) di quel giorno."""
        chiave = giorno.strftime("%d-%m-%Y")
        return giorno.isoformat(), {
            "compiti": _valori(self._alunno(f"compito/elenco/{chiave}")),
            "lezioni": _valori(self._alunno(f"argomento-lezione/elenco/{chiave}")),
        }

    def scarica(self, oggi=None, giorni_gia_letti=()):
        """Tutti i dati grezzi. `giorni_gia_letti`: date passate già in cache, da non richiedere di nuovo."""
        oggi = oggi or date.today()
        frazioni = _valori(self._alunno("frazioni-temporali"))
        # L'elenco delle materie serve anche per quelle ancora senza voti.
        frazione = next((f for f in frazioni if f.get("corrente")), frazioni[0] if frazioni else None)
        materie = _valori(self._alunno(f"frazione-temporale/{frazione.get('id')}/voti/materie")) if frazione else []

        da_leggere = [
            oggi + timedelta(days=scarto)
            for scarto in range(-GIORNI_INDIETRO, GIORNI_AVANTI + 1)
            # I giorni passati non cambiano più: si rileggono solo gli ultimi tre.
            if scarto >= -3 or (oggi + timedelta(days=scarto)).isoformat() not in giorni_gia_letti
        ]
        with ThreadPoolExecutor(max_workers=RICHIESTE_INSIEME) as gruppo:
            giorni = dict(gruppo.map(self._giorno, da_leggere))
        return {
            "alunno": self.alunno,
            "frazioni": frazioni,
            "materie": [{"id": m.get("id"), "materia": m.get("materia")} for m in materie],
            "voti": _valori(self._alunno("voti")),
            "giorni": giorni,
            "assenze": _valori(self._alunno("assenze")),
            "note": _valori(self._alunno("note")),
            "eventi_classe": _valori(self._alunno("eventi-classe")),
            "eventi_alunno": _valori(self._alunno("eventi-alunno")),
        }
