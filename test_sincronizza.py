"""Prove della sincronizzazione tra PC e telefono: unione delle copie, scambio in rete, comandi della pagina."""

import contextlib
import json
import socket
import threading
import unittest
from datetime import datetime
from unittest import mock

import archivio
import dati
import profili
import server
import sincronizza
import test_profili as base

ARGO, NUVOLA = base.ARGO, base.NUVOLA
CODICE = "ABCDEFGHIJKLMNOPQRST"


class DueDispositivi(base.Base):
    """PC e telefono sono due cartelle: si lavora sull'una o sull'altra con «with self.su(...)»."""

    def setUp(self):
        super().setUp()
        self.pc, self.telefono = self.cartella / "pc", self.cartella / "telefono"
        self.blocco = threading.RLock()
        self.orologio = iter(f"2026-10-12T10:00:{s:02d}" for s in range(60))
        self.enterContext(mock.patch.object(profili, "adesso", lambda: next(self.orologio)))
        self.enterContext(mock.patch.object(sincronizza, "ATTESA_RICERCA", 0.4))

    @contextlib.contextmanager
    def su(self, dispositivo):
        with mock.patch.object(profili, "CARTELLA", dispositivo):
            yield

    def sincronizza(self):
        """Uno scambio completo, senza rete: il telefono manda la sua copia, il PC risponde con l'unione. True se qualcosa è cambiato."""
        with self.su(self.telefono):
            copia = sincronizza.istantanea()
        with self.su(self.pc):
            unione, sul_pc = sincronizza.ricevi(json.loads(json.dumps(copia)), self.blocco)
        with self.su(self.telefono):
            return sincronizza.ricevi(json.loads(json.dumps(unione)), self.blocco)[1] or sul_pc

    def spunta(self, dispositivo, profilo, compito, fatto, quando):
        with self.su(dispositivo), mock.patch.object(dati, "datetime") as orologio:
            orologio.now.return_value = datetime.fromisoformat(quando)
            dati.attiva(profilo, ricorda=False)
            dati.segna_compito(compito, fatto)
            dati.attiva(None)

    def fatti(self, dispositivo, profilo):
        with self.su(dispositivo):
            return set(sincronizza.istantanea()["dati"][profilo["id"]]["stato"]["fatti"])


class Unione(DueDispositivi):
    def test_stesso_risultato_in_qualunque_ordine(self):
        profilo = {"id": "aaaaaaaa", "nome": "Mario", "registro": "nuvola", "scuola": "", "utente": "m", "untis": None, "password": "pw"}
        a = {"profili": {"aaaaaaaa": {**profilo, "modificato": "2026-10-01T10:00:00"}}, "eliminati": {"bbbbbbbb": "2026-10-02T10:00:00"},
             "dati": {"aaaaaaaa": {"stato": {"fatti": {"x": "2026-10-03T10:00:00", "y": "2026-10-03T10:00:00"}},
                                   "dashboard": {"scaricato": "2026-10-05T08:00:00", "dashboard": {}, "nuvola": {"giorni": {"2026-10-01": {"v": "a"}, "2026-10-02": {"v": "a"}}}},
                                   "orario": {"scaricato": "2026-10-05T08:00:00", "settimane": [], "viste": {"k": "2026-10-05T08:00:00", "j": ""}}}}}
        b = {"profili": {"aaaaaaaa": {**profilo, "nome": "Max", "password": "", "modificato": "2026-10-04T10:00:00"},
                         "bbbbbbbb": {**profilo, "id": "bbbbbbbb", "modificato": "2026-10-01T10:00:00"}}, "eliminati": {},
             "dati": {"aaaaaaaa": {"stato": {"fatti": {"z": "2026-10-03T10:00:00"}, "tolti": {"x": "2026-10-04T10:00:00", "y": "2026-10-02T10:00:00"}},
                                   "dashboard": {"scaricato": "2026-10-04T08:00:00", "dashboard": {}, "nuvola": {"giorni": {"2026-09-30": {"v": "b"}, "2026-10-02": {"v": "b"}}}},
                                   "orario": {"scaricato": "2026-10-04T08:00:00", "settimane": [], "viste": {"k": "2026-10-04T08:00:00", "j": "2026-10-04T08:00:00"}}},
                      "bbbbbbbb": {"stato": {"fatti": {}}, "dashboard": None, "orario": None}}}
        unione = sincronizza.unisci(a, b)
        self.assertEqual(unione, sincronizza.unisci(b, a))
        self.assertEqual(unione, sincronizza.unisci(unione, a))
        self.assertEqual(unione, sincronizza.unisci(b, unione))

        # Vince la modifica più recente, ma la password che manca si prende dall'altra copia; il profilo eliminato dopo non torna.
        self.assertEqual(list(unione["profili"]), ["aaaaaaaa"])
        self.assertEqual((unione["profili"]["aaaaaaaa"]["nome"], unione["profili"]["aaaaaaaa"]["password"]), ("Max", "pw"))
        suoi = unione["dati"]["aaaaaaaa"]
        # x è stata tolta dopo essere stata messa, y rimessa dopo essere stata tolta.
        self.assertEqual((set(suoi["stato"]["fatti"]), set(suoi["stato"]["tolti"])), ({"y", "z"}, {"x"}))
        self.assertEqual(suoi["dashboard"]["scaricato"], "2026-10-05T08:00:00")
        self.assertEqual(suoi["dashboard"]["nuvola"]["giorni"], {"2026-09-30": {"v": "b"}, "2026-10-01": {"v": "a"}, "2026-10-02": {"v": "a"}})
        self.assertEqual(suoi["orario"]["viste"], {"k": "2026-10-04T08:00:00", "j": "2026-10-04T08:00:00"})

    def test_copia_ricevuta_rovinata(self):
        pulita = sincronizza._controlla({"profili": {"../../x": {"id": "../../x"}, "aaaaaaaa": "no", "bbbbbbbb": {"id": "bbbbbbbb", "registro": "altro"},
                                                     "cccccccc": {"id": "cccccccc", "nome": "N", "registro": "argo", "scuola": "S", "utente": "u", "password": "p",
                                                                  "untis": {"server": "esempio.it", "scuola": "s", "classe": "c"}}},
                                        "eliminati": {"zz": "x", "dddddddd": 5}, "dati": "no"})
        self.assertEqual(pulita, {"profili": {}, "eliminati": {}, "dati": {}})

    def test_profili_e_password_arrivano_sull_altro_dispositivo(self):
        with self.su(self.pc):
            a, n = profili.salva(dict(ARGO)), profili.salva(dict(NUVOLA))
            archivio.scrivi(profili.cartella(a["id"]) / "dashboard.json", {"scaricato": "2026-10-12T11:00:00", "dashboard": {"voti": []}})
        self.assertTrue(self.sincronizza())
        self.assertFalse(self.sincronizza())  # la seconda volta non c'è più nulla da cambiare
        with self.su(self.telefono):
            self.assertEqual([p["nome"] for p in profili.elenco()], ["Mario", "Amico"])
            self.assertEqual((profili.password(a["id"]), profili.password(n["id"])), ("segreta-argo", "segreta-nuvola"))
            self.assertNotIn("segreta", (self.telefono / "profili.json").read_text(encoding="utf-8"))
            self.assertEqual(archivio.leggi(profili.cartella(a["id"]) / "dashboard.json")["scaricato"], "2026-10-12T11:00:00")
            # Dal telefono: cambio password e nome di un profilo, eliminazione dell'altro.
            profili.salva({**ARGO, "nome": "Max", "password": "nuova"}, a["id"])
            profili.elimina(n["id"])
        self.assertTrue(self.sincronizza())
        with self.su(self.pc):
            self.assertEqual([(p["nome"], profili.password(p["id"])) for p in profili.elenco()], [("Max", "nuova")])
            self.assertFalse(profili.cartella(n["id"]).exists())
            self.assertEqual(archivio.leggi(profili.cartella(a["id"]) / "dashboard.json")["scaricato"], "2026-10-12T11:00:00")
        self.assertFalse(self.sincronizza())

    def test_spunta_tolta_non_ritorna(self):
        with self.su(self.pc):
            a = profili.salva(dict(ARGO))
        self.sincronizza()
        self.spunta(self.pc, a, "uno", True, "2026-10-12T12:00:00")
        self.spunta(self.telefono, a, "due", True, "2026-10-12T12:01:00")
        self.assertTrue(self.sincronizza())
        self.assertEqual((self.fatti(self.pc, a), self.fatti(self.telefono, a)), ({"uno", "due"}, {"uno", "due"}))
        self.spunta(self.telefono, a, "uno", False, "2026-10-12T12:02:00")
        self.sincronizza()
        self.assertEqual((self.fatti(self.pc, a), self.fatti(self.telefono, a)), ({"due"}, {"due"}))
        self.spunta(self.pc, a, "uno", True, "2026-10-12T12:03:00")  # rimessa: vale di nuovo
        self.sincronizza()
        self.assertEqual(self.fatti(self.telefono, a), {"uno", "due"})

    def test_cambio_account_scarta_i_dati_vecchi(self):
        with self.su(self.pc):
            a = profili.salva(dict(ARGO))
            archivio.scrivi(profili.cartella(a["id"]) / "dashboard.json", {"scaricato": "2026-10-12T10:00:00", "dashboard": {}})
        self.sincronizza()
        with self.su(self.telefono):
            self.assertTrue((profili.cartella(a["id"]) / "dashboard.json").exists())
        with self.su(self.pc):
            profili.salva({**ARGO, "utente": "un.altro", "password": ""}, a["id"])  # dal PC i dati spariscono subito
        self.sincronizza()
        for dispositivo in (self.pc, self.telefono):
            with self.su(dispositivo):
                self.assertFalse((profili.cartella(a["id"]) / "dashboard.json").exists())
                self.assertEqual(profili.password(a["id"]), "segreta-argo")


class Rete(DueDispositivi):
    PORTA = 8796

    def setUp(self):
        super().setUp()
        self.enterContext(mock.patch.object(sincronizza.config, "PORTA_SYNC", self.PORTA))
        self.addCleanup(sincronizza.ferma_ascolto)

    def assertQuestoPc(self, indirizzo):
        """La ricerca va anche a tutta la rete, come dal telefono: può rispondere prima dall'indirizzo di rete
        di questo computer che da 127.0.0.1 (succede sulle macchine macOS di GitHub). Va bene uno qualsiasi dei suoi."""
        self.assertIsNotNone(indirizzo)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as prova:
            prova.bind((indirizzo, 0))  # riesce solo con un indirizzo di questo computer

    def test_ricerca_e_scambio(self):
        with self.su(self.pc):
            a = profili.salva(dict(ARGO))
            self.assertFalse(sincronizza.avvia_ascolto(self.blocco))  # non attivata: il PC non ascolta nessuno
            sincronizza._ricorda(codice=CODICE)
            self.assertTrue(sincronizza.avvia_ascolto(self.blocco))
            self.assertIsNone(sincronizza._trova_pc("SBAGLIATOSBAGLIATOAA", "127.0.0.1"))
            with self.assertRaisesRegex(sincronizza.ErroreSincronizzazione, "sbagliato"):
                sincronizza._scambia("127.0.0.1", "SBAGLIATOSBAGLIATOAA", {"profili": {}, "eliminati": {}, "dati": {}})
            # Più ricerche di fila: il PC deve continuare a rispondere anche dopo risposte arrivate a chi ha già chiuso.
            for _ in range(4):
                self.assertQuestoPc(sincronizza._trova_pc(CODICE, "127.0.0.1"))
            unione =sincronizza._scambia("127.0.0.1", CODICE, {"profili": {}, "eliminati": {}, "dati": {}})
            self.assertEqual(unione["profili"][a["id"]]["password"], "segreta-argo")
            # In rete passa solo testo cifrato.
            self.assertNotIn(b"segreta", sincronizza.cifra(CODICE, unione))
            self.assertIn("telefono", sincronizza.impostazioni()["esito"])
            sincronizza.ferma_ascolto()
            self.assertIsNone(sincronizza._trova_pc(CODICE, "127.0.0.1"))

    def test_riattivazione_e_avvio_rapido(self):
        # Fermato l'ascolto la porta torna subito libera (su Linux restava occupata), e l'avvio non cerca
        # il nome del computer in rete (su macOS ci voleva più di un minuto).
        with self.su(self.pc), mock.patch.object(sincronizza.socket, "getfqdn", side_effect=AssertionError("getfqdn")):
            sincronizza._ricorda(codice=CODICE)
            for _ in range(3):
                self.assertTrue(sincronizza.avvia_ascolto(self.blocco))
                self.assertQuestoPc(sincronizza._trova_pc(CODICE, "127.0.0.1"))
                sincronizza.ferma_ascolto()

    def test_telefono_senza_pc(self):
        with self.su(self.telefono), mock.patch.object(sincronizza.config, "ANDROID", True):
            self.assertEqual(sincronizza.sincronizza_ora(self.blocco), {"trovato": False, "cambiato": False, "esito": None})  # non abbinato
            with self.assertRaisesRegex(sincronizza.ErroreSincronizzazione, "20 caratteri"):
                sincronizza.comando({"azione": "abbina", "codice": "corto"}, self.blocco)
            with self.assertRaisesRegex(sincronizza.ErroreSincronizzazione, "indirizzo"):
                sincronizza.comando({"azione": "abbina", "codice": CODICE, "indirizzo": "8.8.8.8"}, self.blocco)
            esito = sincronizza.comando({"azione": "abbina", "codice": "abcde-fghij klmno-pqrst", "indirizzo": "127.0.0.1"}, self.blocco)
            self.assertEqual((esito["ruolo"], esito["attiva"], esito["trovato"], esito["pc"]), ("telefono", True, False, "127.0.0.1"))
            self.assertNotIn("codice", esito)
            self.assertEqual(sincronizza.impostazioni()["codice"], CODICE)
            self.assertFalse(sincronizza.comando({"azione": "disattiva"}, self.blocco)["attiva"])


class Pagina(base.ServerProfili):
    PORTA = 8795

    def test_riquadro_sincronizzazione(self):
        self.enterContext(mock.patch.object(sincronizza.config, "PORTA_SYNC", 8794))
        self.addCleanup(sincronizza.ferma_ascolto)
        stato, riquadro = self.chiama("GET", "/api/sincronizzazione")
        self.assertEqual((stato, riquadro["ruolo"], riquadro["attiva"], riquadro["codice"]), (200, "pc", False, ""))
        self.assertEqual(self.chiama("POST", "/api/sincronizzazione", {"azione": "ora"})[0], 400)  # dal PC non si cerca nessuno
        stato, riquadro = self.chiama("POST", "/api/sincronizzazione", {"azione": "attiva"})
        self.assertEqual((stato, riquadro["attiva"], riquadro["in_ascolto"]), (200, True, True))
        self.assertRegex(riquadro["codice"], r"^([A-Z2-7]{5}-){3}[A-Z2-7]{5}$")
        self.assertEqual(self.chiama("POST", "/api/sincronizzazione", {"azione": "attiva"})[1]["codice"], riquadro["codice"])
        riquadro = self.chiama("POST", "/api/sincronizzazione", {"azione": "disattiva"})[1]
        self.assertEqual((riquadro["attiva"], riquadro["in_ascolto"], riquadro["codice"]), (False, False, ""))

    def test_gettone_del_telefono(self):
        with mock.patch.object(server.config, "GETTONE", "segreto-di-questo-avvio"):
            self.assertEqual(self.chiama("GET", "/api/profili")[0], 403)
            self.assertEqual(self.chiama("POST", "/api/profili", {"profilo": ARGO})[0], 403)
            self.cookie = "gettone=segreto-di-questo-avvio"
            self.assertEqual(self.chiama("GET", "/api/profili")[0], 200)


if __name__ == "__main__":
    unittest.main()
