"""Strumenti comuni alle prove: profili finti, una cartella pulita per ogni prova, il server su una porta libera."""

import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import prove  # noqa: F401  (rende sicuro l'ambiente: va importato per primo)
import config
import dati
import profili
import server

# Profili finti, uno per registro: le password non sono mai vere.
ARGO = {"nome": "Mario", "registro": "argo", "scuola": "SC12345", "utente": "mario.r", "password": "segreta-argo"}
NUVOLA = {"nome": "Amico", "registro": "nuvola", "utente": "amico", "password": "segreta-nuvola",
          "untis": {"server": "https://Scuola.WebUntis.com/", "scuola": "scuola", "classe": "3A"}}
CLASSEVIVA = {"nome": "Rossi", "registro": "classeviva", "utente": "genitore@example.com", "password": "segreta-cv"}
FIGLI = [{"ident": "S1234567X", "name": "MARIO ROSSI"}, {"ident": "S1111111X", "name": "LUCIA ROSSI"}]

# La funzione vera, prima che Base la sostituisca con una finta.
PROVA_ACCESSO_VERA = dati.prova_accesso


class Risposta:
    """Al posto di una risposta di requests: stato, intestazioni, testo e JSON a piacere."""

    def __init__(self, url="", stato=200, dati=None, testo="", intestazioni=None):
        self.url, self.status_code, self._dati, self.text = url, stato, dati, testo
        self.headers = intestazioni or {}
        self.is_redirect = stato in (301, 302, 303, 307, 308)

    def json(self):
        if self._dati is None:
            raise ValueError("non è JSON")
        return self._dati


class Base(unittest.TestCase):
    """Ogni prova lavora in una cartella temporanea tutta sua, senza portachiavi, senza Internet e senza pause.

    self.portachiavi: None = nessun portachiavi (le password vanno su file); una prova può metterne uno finto.
    self.prova_accesso: la prova dei dati di accesso fatta al salvataggio del profilo (finta: va sempre bene,
    a meno che la prova non le dia un side_effect).
    """

    def setUp(self):
        self.cartella = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(mock.patch.object(profili, "CARTELLA", self.cartella / "profili"))
        self.enterContext(mock.patch.object(profili, "BASE", self.cartella))
        self.enterContext(mock.patch.object(server, "REGISTRO_ERRORI", self.cartella / "errori.log"))
        self.enterContext(mock.patch.object(server, "PREFERENZE", self.cartella / "preferenze.json"))
        self.portachiavi = None
        self.enterContext(mock.patch.object(profili, "_portachiavi", lambda: self.portachiavi))
        self.enterContext(mock.patch.object(dati, "PAUSA_RIPROVA", 0))
        self.prova_accesso = self.enterContext(mock.patch.object(dati, "prova_accesso"))
        # Le circolari stanno su un sito pubblico: le prove ne ricevono un elenco vuoto, a meno che non ne mettano uno.
        self.circolari = self.enterContext(mock.patch.object(dati.circolari, "scarica", return_value=("1", [])))
        self.addCleanup(dati.attiva, None)
        dati.attiva(None)
        prove.TENTATIVI_RETE.clear()
        self.addCleanup(self._niente_internet)

    def _niente_internet(self):
        self.assertEqual(prove.TENTATIVI_RETE, [], "la prova ha cercato di collegarsi a Internet")


class PortachiaviFinto:
    """Un portachiavi in memoria. guasto=True: accetta le password ma poi non le restituisce (come uno bloccato)."""

    def __init__(self, guasto=False):
        self.deposito, self.guasto = {}, guasto

    def set_password(self, servizio, utente, password):
        self.deposito[(servizio, utente)] = password

    def get_password(self, servizio, utente):
        if self.guasto:
            raise RuntimeError("portachiavi bloccato")
        return self.deposito.get((servizio, utente))

    def delete_password(self, servizio, utente):
        self.deposito.pop((servizio, utente), None)


class ServerProfili(Base):
    """Il server vero dell'app, su una porta libera qualsiasi: così non si scontra con l'app aperta o con altri programmi."""

    GETTONE = ""  # vuoto: il server non chiede il gettone (le prove del gettone sono in test_sicurezza)

    def setUp(self):
        super().setUp()
        self.enterContext(mock.patch.object(config, "GETTONE", self.GETTONE))
        self.app = server.avvia(porta=0)
        self.PORTA = self.app.server_address[1]
        self.enterContext(mock.patch.object(config, "PORTA", self.PORTA))  # il server controlla l'intestazione Host
        threading.Thread(target=self.app.serve_forever, daemon=True).start()
        self.addCleanup(self.app.server_close)
        self.addCleanup(self.app.shutdown)
        self.cookie = ""  # come il browser: ricorda il cookie del profilo scelto

    def chiama(self, metodo, percorso, corpo=None):
        """Una richiesta come la fa la pagina: restituisce (stato, JSON della risposta)."""
        connessione = http.client.HTTPConnection("127.0.0.1", self.PORTA, timeout=20)
        connessione.request(metodo, percorso, body=json.dumps(corpo) if corpo is not None else None,
                            headers={"Host": f"127.0.0.1:{self.PORTA}", "X-Parser-Compiti": "1", "Content-Type": "application/json", "Cookie": self.cookie})
        risposta = connessione.getresponse()
        contenuto = risposta.read()
        for impostato in risposta.msg.get_all("Set-Cookie") or []:
            nome, _, resto = impostato.partition("=")
            valore = resto.split(";")[0]
            if nome == "profilo":
                self.cookie = f"profilo={valore}" if valore else ""
        connessione.close()
        return risposta.status, json.loads(contenuto)
