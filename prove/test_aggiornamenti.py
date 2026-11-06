"""Prove degli aggiornamenti: il controllo su GitHub e zaino.exe che si sostituisce (con GitHub e file finti)."""

import hashlib
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import requests

import aggiornamenti
import archivio
from aggiornamenti import ErroreAggiornamento

NUOVO = b"MZ zaino 0.9.0"


class Risposta:
    def __init__(self, corpo=None, testo="", contenuto=b"", stato=200):
        self._corpo, self.text, self._contenuto, self.status_code = corpo, testo, contenuto, stato

    def json(self):
        return self._corpo

    def raise_for_status(self):
        if self.status_code != 200:
            raise requests.HTTPError(str(self.status_code))

    def iter_content(self, _dimensione):
        yield self._contenuto

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def release(versione="0.9.0", con_exe=True):
    file = [{"name": "zaino.exe", "browser_download_url": "https://x/zaino.exe"},
            {"name": "zaino.exe.sha256", "browser_download_url": "https://x/zaino.exe.sha256"}] if con_exe else []
    return {"tag_name": versione, "html_url": f"https://github.com/x/releases/tag/{versione}",
            "assets": [{"name": f"zaino-{versione}.apk", "browser_download_url": "https://x/a.apk"}, *file]}


class Base(unittest.TestCase):
    def setUp(self):
        self.cartella = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(mock.patch.object(aggiornamenti, "FILE", self.cartella / "cache" / "aggiornamenti.json"))
        self.enterContext(mock.patch.object(aggiornamenti.config, "VERSIONE", "0.5.1"))
        self.enterContext(mock.patch.object(aggiornamenti.config, "ANDROID", False))
        self.chiamate = []

    def github(self, dati=None, impronta=None, contenuto=NUOVO, errore=False):
        def get(url, **_):
            self.chiamate.append(url)
            if errore:
                raise requests.ConnectionError("rete giù")
            if url == aggiornamenti.ULTIMA:
                return Risposta(dati or release())
            if url.endswith(".sha256"):
                return Risposta(testo=f"{impronta or hashlib.sha256(contenuto).hexdigest()}  zaino.exe\n")
            return Risposta(contenuto=contenuto)
        self.enterContext(mock.patch.object(aggiornamenti.requests, "get", get))


class Controllo(Base):
    def test_numeri(self):
        self.assertEqual(aggiornamenti.numeri("v0.2.1-beta"), (0, 2, 1))
        self.assertGreater(aggiornamenti.numeri("0.10.0"), aggiornamenti.numeri("0.9.9"))

    def test_versione_nuova(self):
        self.github()
        stato = aggiornamenti.stato()
        self.assertEqual(stato["nuova"], {"versione": "0.9.0", "pagina": "https://github.com/x/releases/tag/0.9.0"})
        self.assertFalse(stato["installabile"])  # da Python non si sostituisce da solo

    def test_installabile_solo_da_exe(self):
        self.github()
        with mock.patch.object(aggiornamenti.config, "EXE", True):
            self.assertTrue(aggiornamenti.stato()["installabile"])
        self.github(release(con_exe=False))
        with mock.patch.object(aggiornamenti.config, "EXE", True):
            self.assertFalse(aggiornamenti.stato(forza=True)["installabile"])  # una Release senza exe

    def test_stessa_versione_o_piu_vecchia(self):
        for versione in ("0.5.1", "0.5.0"):
            self.github(release(versione))
            self.assertIsNone(aggiornamenti.stato(forza=True)["nuova"])

    def test_una_volta_al_giorno(self):
        self.github()
        aggiornamenti.stato()
        aggiornamenti.stato()
        self.assertEqual(self.chiamate.count(aggiornamenti.ULTIMA), 1)
        aggiornamenti.stato(forza=True)  # «Controlla ora»
        self.assertEqual(self.chiamate.count(aggiornamenti.ULTIMA), 2)
        salvato = archivio.leggi(aggiornamenti.FILE)
        archivio.scrivi(aggiornamenti.FILE, {**salvato, "controllato": time.time() - 2 * 86400, "tentato": 0})
        aggiornamenti.stato()
        self.assertEqual(self.chiamate.count(aggiornamenti.ULTIMA), 3)

    def test_controllo_automatico_spento(self):
        self.github()
        aggiornamenti.imposta(False)
        self.assertFalse(aggiornamenti.stato()["automatico"])
        self.assertNotIn(aggiornamenti.ULTIMA, self.chiamate)

    def test_github_irraggiungibile(self):
        self.github(errore=True)
        stato = aggiornamenti.stato()
        self.assertIn("non è raggiungibile", stato["errore"])
        self.assertIsNone(stato["nuova"])
        self.chiamate.clear()
        self.github()
        self.assertIsNone(aggiornamenti.stato()["errore"])  # non riprova subito a ogni apertura
        self.assertNotIn(aggiornamenti.ULTIMA, self.chiamate)

    def test_telefono(self):
        with mock.patch.object(aggiornamenti.config, "ANDROID", True):
            self.assertEqual(aggiornamenti.stato(), {"disponibile": False})


class Installa(Base):
    def setUp(self):
        super().setUp()
        self.exe = self.cartella / "app" / "zaino.exe"
        self.exe.parent.mkdir()
        self.exe.write_bytes(b"MZ zaino 0.5.1")
        self.enterContext(mock.patch.object(aggiornamenti.config, "EXE", True))
        self.enterContext(mock.patch.object(aggiornamenti.sys, "executable", str(self.exe)))
        self.avviati = []
        self.enterContext(mock.patch.object(aggiornamenti.subprocess, "Popen", lambda comando, **_: self.avviati.append(comando)))

    def test_sostituisce_e_riavvia(self):
        self.github()
        aggiornamenti.stato()
        self.assertEqual(aggiornamenti.installa(), "0.9.0")
        self.assertEqual(self.exe.read_bytes(), NUOVO)
        self.assertEqual(self.exe.with_name("zaino.vecchio.exe").read_bytes(), b"MZ zaino 0.5.1")
        self.assertEqual(self.avviati, [[str(self.exe), "--dopo-aggiornamento"]])

    def test_impronta_sbagliata(self):
        self.github(impronta="0" * 64)
        aggiornamenti.stato()
        with self.assertRaisesRegex(ErroreAggiornamento, "non corrisponde"):
            aggiornamenti.installa()
        self.assertEqual(self.exe.read_bytes(), b"MZ zaino 0.5.1")  # resta quello di prima
        self.assertEqual(sorted(p.name for p in self.exe.parent.iterdir()), ["zaino.exe"])
        self.assertEqual(self.avviati, [])

    def test_niente_da_installare(self):
        self.github(release("0.5.1"))
        aggiornamenti.stato()
        with self.assertRaisesRegex(ErroreAggiornamento, "Non c'è"):
            aggiornamenti.installa()

    def test_download_interrotto(self):
        self.github()
        aggiornamenti.stato()
        self.github(errore=True)
        with self.assertRaisesRegex(ErroreAggiornamento, "Download non riuscito"):
            aggiornamenti.installa()
        self.assertEqual(sorted(p.name for p in self.exe.parent.iterdir()), ["zaino.exe"])


if __name__ == "__main__":
    unittest.main()
