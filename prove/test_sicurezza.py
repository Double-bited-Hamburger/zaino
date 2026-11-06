"""Prove delle difese: il gettone che apre la pagina e i messaggi della sincronizzazione."""

import http.client
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import main
import sincronizza
from prove import aiuti as base

GETTONE = "g" * 43
CODICE = "ABCDEFGHIJKLMNOPQRST"


class Gettone(base.ServerProfili):
    GETTONE = GETTONE  # il server ora vuole il gettone

    def grezza(self, percorso, cookie="", host=None):
        connessione = http.client.HTTPConnection("127.0.0.1", self.PORTA, timeout=20)
        connessione.request("GET", percorso, headers={"Host": host or f"127.0.0.1:{self.PORTA}", "Cookie": cookie})
        risposta = connessione.getresponse()
        corpo = risposta.read()
        connessione.close()
        return risposta.status, risposta.msg, corpo

    def test_senza_gettone_niente_dati(self):
        """Un altro programma del computer (o un altro utente) non legge né i dati né il codice di abbinamento."""
        for percorso in ("/api/dati", "/api/profili", "/api/sincronizzazione", "/api/panoramica"):
            self.assertEqual(self.chiama("GET", percorso)[0], 403, percorso)
        self.assertEqual(self.chiama("POST", "/api/sincronizzazione", {"azione": "attiva"})[0], 403)
        stato, _, corpo = self.grezza("/")
        self.assertEqual(stato, 403)
        self.assertIn(b"avvia.bat", corpo)
        self.assertEqual(self.grezza("/", cookie="gettone=sbagliato")[0], 403)

    def test_collegamento_di_avvio(self):
        stato, intestazioni, _ = self.grezza(f"/?accesso={GETTONE}")
        self.assertEqual((stato, intestazioni["Location"]), (302, "/"))
        cookie = intestazioni["Set-Cookie"]
        for parte in (f"gettone={GETTONE}", "HttpOnly", "SameSite=Strict"):
            self.assertIn(parte, cookie)
        self.assertEqual(self.grezza("/", cookie=f"gettone={GETTONE}")[0], 200)
        self.cookie = f"gettone={GETTONE}"
        self.assertEqual(self.chiama("GET", "/api/profili")[0], 200)

    def test_collegamento_sbagliato_o_da_fuori(self):
        self.assertEqual(self.grezza("/?accesso=indovino")[0], 403)
        self.assertEqual(self.grezza(f"/?accesso={GETTONE}", host="sito-malevolo.example")[0], 403)
        self.assertEqual(self.grezza("/?accesso=%C3%A0%C3%A0%00")[0], 403)  # caratteri strani: nessun errore interno

    def test_due_profili_e_panoramica(self):
        """Ogni richiesta lavora sul profilo del proprio cookie; la panoramica li mostra tutti."""
        import dati
        import profili

        a = profili.salva({"nome": "Anna", "registro": "nuvola", "utente": "a", "password": "x"})
        b = profili.salva({"nome": "Bruno", "registro": "nuvola", "utente": "b", "password": "y"})
        for p in (a, b):
            dati.attiva(p, ricorda=False)
            dati._scrivi(dati.CACHE, {"scaricato": "2026-10-10T08:00:00", "profilo": {}, "dashboard": {}})
        dati.attiva(None)
        for p in (a, b):
            self.cookie = f"gettone={GETTONE}; profilo={p['id']}"
            self.assertEqual(self.chiama("GET", "/api/dati")[1]["profilo"]["id"], p["id"])
        stato, carte = self.chiama("GET", "/api/panoramica")
        self.assertEqual((stato, {c["nome"] for c in carte["profili"]}), (200, {"Anna", "Bruno"}))

    def test_gettone_ricordato_tra_un_avvio_e_l_altro(self):
        with tempfile.TemporaryDirectory() as cartella, mock.patch.object(main.config, "DATI_DIR", cartella):
            primo = main.gettone_locale()
            self.assertGreaterEqual(len(primo), 32)
            self.assertEqual(main.gettone_locale(), primo)
            self.assertTrue((Path(cartella) / "cache" / "gettone_locale").exists())


class Messaggi(unittest.TestCase):
    def setUp(self):
        sincronizza._visti.clear()

    def test_messaggio_rimandato_rifiutato(self):
        messaggio = sincronizza.cifra(CODICE, {"profili": {}})
        self.assertEqual(sincronizza.decifra(CODICE, messaggio), {"profili": {}})
        with self.assertRaisesRegex(sincronizza.ErroreSincronizzazione, "già ricevuto"):
            sincronizza.decifra(CODICE, messaggio)

    def test_messaggio_vecchio_rifiutato(self):
        vecchio = sincronizza.cifra(CODICE, {}, adesso=1_000_000)
        with self.assertRaisesRegex(sincronizza.ErroreSincronizzazione, "data e ora"):
            sincronizza.decifra(CODICE, vecchio, adesso=1_000_000 + 20 * 60)
        # Orologi un po' diversi tra PC e telefono vanno bene.
        self.assertEqual(sincronizza.decifra(CODICE, sincronizza.cifra(CODICE, {}, adesso=1_000_000), adesso=1_000_000 + 5 * 60), {})

    def test_codice_sbagliato(self):
        with self.assertRaises(sincronizza.CodiceSbagliato):
            sincronizza.decifra("SBAGLIATOSBAGLIATOAA", sincronizza.cifra(CODICE, {}))


class TroppiScambi(base.Base):
    PORTA = 8792

    def setUp(self):
        super().setUp()
        self.enterContext(mock.patch.object(sincronizza.config, "PORTA_SYNC", self.PORTA))
        self.addCleanup(sincronizza.ferma_ascolto)
        sincronizza._ricorda(codice=CODICE)
        self.assertTrue(sincronizza.avvia_ascolto(threading.RLock()))

    def test_terzo_scambio_insieme_rifiutato(self):
        for _ in range(2):
            self.assertTrue(sincronizza._scambi.acquire(blocking=False))
        try:
            with self.assertRaisesRegex(sincronizza.ErroreSincronizzazione, "occupato"):
                sincronizza._scambia("127.0.0.1", CODICE, {"profili": {}, "eliminati": {}, "dati": {}})
        finally:
            sincronizza._scambi.release()
            sincronizza._scambi.release()
        self.assertIn("profili", sincronizza._scambia("127.0.0.1", CODICE, {"profili": {}, "eliminati": {}, "dati": {}}))

    def test_errore_spiegato_al_telefono(self):
        """Con il codice giusto ma l'orologio sbagliato, il telefono riceve il motivo vero."""
        vecchio = sincronizza.cifra(CODICE, {"profili": {}, "eliminati": {}, "dati": {}}, adesso=1_000_000)
        connessione = http.client.HTTPConnection("127.0.0.1", self.PORTA, timeout=20)
        connessione.request("POST", "/sync", body=vecchio)
        risposta = connessione.getresponse()
        self.assertEqual(risposta.status, 400)
        self.assertIn("data e ora", risposta.read().decode())
        connessione.close()


if __name__ == "__main__":
    unittest.main()
