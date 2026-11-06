"""Prove dell'accesso ai registri: i casi in cui dati giusti venivano rifiutati, o l'app diceva «dati non validi» a torto.

- campi scritti dal telefono o copiati e incollati (maiuscola automatica, spazi, caratteri invisibili);
- password che il portachiavi del sistema accetta ma poi non restituisce (Linux, zaino.exe);
- registro lento o in manutenzione, che non vuol dire password sbagliata;
- dati di accesso provati subito quando si salva il profilo.
"""

import os
import socket
import sys
import types
import unittest
from unittest import mock

import requests

import dati
import profili
import prove
from archivio import CredenzialiRifiutate, ErroreRegistro
from prove import aiuti
from prove.aiuti import ARGO, NUVOLA, Base


class ClientFinto:
    """Al posto di ArgoClient/NuvolaClient: ogni login prende il prossimo esito dell'elenco (None = entra)."""

    def __init__(self, esiti, giusta=None):
        self.esiti, self.giusta, self.accessi = list(esiti), giusta, []

    def __call__(self, *argomenti):
        finto = self

        class Client:
            def __init__(self):
                self.argomenti = argomenti

            def login(self):
                finto.accessi.append(argomenti)
                esito = finto.esiti.pop(0) if finto.esiti else None
                if esito is not None:
                    raise esito
                if finto.giusta is not None and argomenti[-1] != finto.giusta:
                    raise CredenzialiRifiutate("Username e/o password non validi")

            def dashboard(self):
                return {"alunno": {}}, {"voti": []}

        return Client()


class Campi(Base):
    def test_campi_scritti_dal_telefono(self):
        """Spazi, a capo, spazi «non separabili» e caratteri invisibili spariscono; il codice scuola va in maiuscolo."""
        p = profili.salva({**ARGO, "scuola": " sc 12345​", "utente": "﻿mario.r \n"})
        self.assertEqual((p["scuola"], p["utente"]), ("SC12345", "mario.r"))
        self.assertEqual(profili.nome_utente("argo", "mario .r"), "mario.r")  # su Argo i nomi utente non hanno spazi
        self.assertEqual(profili.nome_utente("nuvola", " Mario Rossi "), "Mario Rossi")
        self.assertEqual(profili.codice_scuola(None), "")

    def test_password_di_soli_spazi_non_cambia_quella_salvata(self):
        p = profili.salva(dict(ARGO))
        profili.salva({**ARGO, "nome": "Max", "password": "   "}, p["id"])
        self.assertEqual(profili.password(p["id"]), "segreta-argo")
        with self.assertRaisesRegex(profili.ProfiloNonValido, "password"):
            profili.salva({**ARGO, "password": " ​ "})

    def test_vecchio_profilo_col_codice_in_minuscolo(self):
        """Un profilo salvato prima della pulizia non perde i dati scaricati quando lo si modifica, e Argo riceve il codice giusto."""
        p = profili.salva(dict(ARGO))
        tutti = profili._leggi()
        tutti["profili"][0]["scuola"] = "sc12345 "
        profili.archivio.scrivi(profili._elenco_file(), tutti)
        dati.attiva(profili.trova(p["id"]))
        dati._scrivi(dati.CACHE, {"dashboard": {}})
        profili.salva({**ARGO, "nome": "Max", "password": ""}, p["id"])
        self.assertTrue(dati.CACHE.exists())

        finto = ClientFinto([])
        with mock.patch.object(dati, "ArgoClient", finto):
            dati.accedi({**profili.trova(p["id"]), "scuola": "sc12345 "}, "pw")
        self.assertEqual(finto.accessi, [("SC12345", "mario.r", "pw")])


class Portachiavi(Base):
    def test_portachiavi_che_accetta_ma_non_restituisce(self):
        """Succede con un portachiavi bloccato: la password finisce nel file del profilo invece di andare persa."""
        self.portachiavi = aiuti.PortachiaviFinto(guasto=True)
        p = profili.salva(dict(ARGO))
        self.assertEqual(profili.password(p["id"]), "segreta-argo")
        if os.name == "posix":
            self.assertEqual(os.stat(profili.cartella(p["id"]) / "credenziali.json").st_mode & 0o777, 0o600)

    def test_password_sparita_dal_portachiavi_spiegata(self):
        self.portachiavi = aiuti.PortachiaviFinto()
        p = profili.salva(dict(ARGO))
        self.portachiavi.deposito.clear()  # per esempio: un altro utente del PC, o il portachiavi ricreato
        self.assertEqual(profili.password(p["id"]), "")
        self.assertIn("portachiavi", profili.perche_manca_password(p["id"]))
        dati.attiva(profili.trova(p["id"]))
        with self.assertRaisesRegex(ErroreRegistro, "portachiavi"):
            dati.scarica()
        self.portachiavi.guasto = True  # bloccato: non risponde proprio
        self.assertIn("Sbloccalo", profili.perche_manca_password(p["id"]))

    def test_chiave_del_telefono_cambiata_spiegata(self):
        with mock.patch.object(profili.config, "CHIAVE_CREDENZIALI", "chiave-vecchia"):
            p = profili.salva(dict(ARGO))
            self.assertEqual(profili.password(p["id"]), "segreta-argo")
        with mock.patch.object(profili.config, "CHIAVE_CREDENZIALI", "chiave-nuova"):
            self.assertEqual(profili.password(p["id"]), "")
            self.assertIn("chiave del telefono", profili.perche_manca_password(p["id"]))

    def test_senza_password_messaggio_semplice(self):
        p = profili.salva(dict(ARGO))
        (profili.cartella(p["id"]) / "credenziali.json").unlink()
        self.assertEqual(profili.perche_manca_password(p["id"]), profili.MANCANTE)

    def test_zaino_exe_ritrova_il_gestione_credenziali(self):
        """Se keyring non trova nessun portachiavi (PyInstaller ne perde l'elenco) si sceglie quello del sistema."""
        finto = types.SimpleNamespace(get_keyring=lambda: types.SimpleNamespace(priority=0), set_keyring=mock.Mock())
        windows = types.SimpleNamespace(WinVaultKeyring=lambda: "gestione credenziali")
        with mock.patch.dict(sys.modules, {"keyring": finto}), mock.patch.object(profili.sys, "platform", "win32"), \
                mock.patch.object(profili, "_portachiavi_scelto", False), \
                mock.patch.object(profili.importlib, "import_module", return_value=windows) as importa:
            self.assertIs(prove.PORTACHIAVI_VERO(), finto)
            prove.PORTACHIAVI_VERO()  # la scelta si fa una volta sola
        importa.assert_called_once_with("keyring.backends.Windows")
        finto.set_keyring.assert_called_once_with("gestione credenziali")


class Accedi(Base):
    def profilo(self, registro=ARGO):
        return profili.trova(profili.salva(dict(registro))["id"])

    def test_registro_lento_si_riprova_da_solo(self):
        finto = ClientFinto([ErroreRegistro("Argo non risponde", temporaneo=True)])
        with mock.patch.object(dati, "ArgoClient", finto):
            client, usata = dati.accedi(self.profilo(), "segreta-argo")
        self.assertEqual((len(finto.accessi), usata), (2, "segreta-argo"))

        finto = ClientFinto([requests.ConnectionError(), requests.Timeout()])
        with mock.patch.object(dati, "ArgoClient", finto), self.assertRaises(requests.Timeout):
            dati.accedi(self.profilo(), "segreta-argo")
        self.assertEqual(len(finto.accessi), dati.TENTATIVI)

    def test_password_sbagliata_un_tentativo_solo(self):
        """Niente tentativi a ripetizione: troppi errori possono bloccare l'account."""
        finto = ClientFinto([], giusta="giusta")
        with mock.patch.object(dati, "ArgoClient", finto), self.assertRaises(CredenzialiRifiutate):
            dati.accedi(self.profilo(), "sbagliata")
        self.assertEqual(len(finto.accessi), 1)

        finto = ClientFinto([ErroreRegistro("La scuola non ha attivato l'accesso")])  # non temporaneo: inutile riprovare
        with mock.patch.object(dati, "NuvolaClient", finto), self.assertRaises(ErroreRegistro):
            dati.accedi(self.profilo(NUVOLA), "pw")
        self.assertEqual(len(finto.accessi), 1)

    def test_password_con_uno_spazio_di_troppo(self):
        """La tastiera del telefono (o un copia e incolla) aggiunge uno spazio: si riprova senza, e si salva così."""
        profilo = profili.trova(profili.salva({**ARGO, "password": "segreta-argo "})["id"])
        self.assertEqual(profili.password(profilo["id"]), "segreta-argo ")
        finto = ClientFinto([], giusta="segreta-argo")
        dati.attiva(profilo)
        with mock.patch.object(dati, "ArgoClient", finto):
            dati.scarica()
        self.assertEqual([a[-1] for a in finto.accessi], ["segreta-argo ", "segreta-argo"])
        self.assertEqual(profili.password(profilo["id"]), "segreta-argo")
        # Una password che ha davvero uno spazio alla fine e va bene così non si tocca.
        finto = ClientFinto([], giusta="con spazio ")
        with mock.patch.object(dati, "ArgoClient", finto):
            self.assertEqual(dati.accedi(profilo, "con spazio ")[1], "con spazio ")

    def test_prova_accesso_vera(self):
        finto = ClientFinto([], giusta="pw")
        with mock.patch.object(dati, "ArgoClient", finto):
            aiuti.PROVA_ACCESSO_VERA({**ARGO, "scuola": "sc 12345"}, "pw")
            with self.assertRaises(CredenzialiRifiutate):
                aiuti.PROVA_ACCESSO_VERA(ARGO, "no")
        self.assertEqual(finto.accessi[0], ("SC12345", "mario.r", "pw"))


class SalvataggioProvato(aiuti.ServerProfili):
    def salva(self, profilo, **altro):
        return self.chiama("POST", "/api/profili", {"profilo": profilo, **altro})

    def test_dati_sbagliati_non_si_salvano(self):
        self.prova_accesso.side_effect = CredenzialiRifiutate("Argo dice: «Username e/o password non validi».")
        stato, risposta = self.salva(ARGO)
        self.assertEqual((stato, risposta["credenziali"]), (400, True))
        self.assertIn("non validi", risposta["errore"])
        self.assertEqual(profili.elenco(), [])
        # «Salva senza provare»: per quando il registro sbaglia a rifiutare.
        stato, risposta = self.salva(ARGO, forza=True)
        self.assertEqual((stato, len(profili.elenco())), (200, 1))
        self.assertEqual(self.prova_accesso.call_count, 1)

    def test_registro_che_non_risponde_non_blocca_il_salvataggio(self):
        for guasto, messaggio in ((ErroreRegistro("Argo non risponde (HTTP 503)", temporaneo=True), "503"),
                                  (requests.ConnectionError(), "non è raggiungibile"),
                                  (ZeroDivisionError(), "errore imprevisto")):
            with self.subTest(messaggio):
                self.prova_accesso.side_effect = guasto
                stato, risposta = self.salva(ARGO)
                self.assertEqual(stato, 200)
                self.assertIn("Profilo salvato", risposta["avviso"])
                self.assertIn(messaggio, risposta["avviso"])

    def test_si_prova_solo_se_cambia_l_accesso(self):
        stato, risposta = self.salva({**ARGO, "scuola": "sc12345", "utente": " mario.r "})
        id_ = risposta["salvato"]
        self.assertIsNone(risposta["avviso"])
        provato, password = self.prova_accesso.call_args.args
        self.assertEqual((provato["scuola"], provato["utente"], password), ("SC12345", "mario.r", "segreta-argo"))

        self.salva({**ARGO, "nome": "Max", "password": ""}, id=id_)  # cambia solo il nome
        self.assertEqual(self.prova_accesso.call_count, 1)
        self.salva({**ARGO, "utente": "altro", "password": ""}, id=id_)  # utente nuovo, password di prima
        self.assertEqual(self.prova_accesso.call_args.args[1], "segreta-argo")
        self.salva({**ARGO, "utente": "altro", "password": "nuova"}, id=id_)
        self.assertEqual((self.prova_accesso.call_count, self.prova_accesso.call_args.args[1]), (3, "nuova"))

    def test_campi_mancanti_prima_della_prova(self):
        """Gli errori del modulo arrivano subito, senza disturbare il registro."""
        self.assertEqual(self.salva({**ARGO, "scuola": " "})[0], 400)
        self.assertEqual(self.salva({**ARGO, "password": ""})[0], 400)
        self.prova_accesso.assert_not_called()


class Diagnosi(Base):
    def test_dice_cosa_non_va_senza_mostrare_segreti(self):
        import diagnosi

        buona = profili.salva({**ARGO, "nome": "Buono"})
        profili.salva({**ARGO, "nome": "Sbagliato", "utente": "altro.utente", "password": "password-sbagliata"})
        senza = profili.salva({**NUVOLA, "nome": "Senza"})
        (profili.cartella(senza["id"]) / "credenziali.json").unlink()
        righe = []
        finto = ClientFinto([], giusta="segreta-argo")
        with mock.patch.object(diagnosi, "_sito", return_value=(None, "")), mock.patch.object(dati, "ArgoClient", finto):
            problemi = diagnosi.esegui(stampa=righe.append)
        testo = "\n".join(righe)
        self.assertEqual(problemi, 2)
        self.assertIn("accesso al registro riuscito", testo)
        self.assertIn("non validi", testo)
        self.assertIn(profili.MANCANTE, testo)
        for segreto in ("segreta-argo", "password-sbagliata", "mario.r", "altro.utente", "SC12345", "Buono", "Sbagliato"):
            self.assertNotIn(segreto, testo)
        self.assertIn("ma•••", testo)
        self.assertTrue(profili.password(buona["id"]))

    def test_sito_irraggiungibile(self):
        import diagnosi

        righe = []
        with mock.patch.object(diagnosi.requests, "get", side_effect=requests.exceptions.SSLError()):
            self.assertEqual(diagnosi.esegui(stampa=righe.append), len(diagnosi.SITI))
        self.assertIn("antivirus", "\n".join(righe))


class NienteInternet(unittest.TestCase):
    def test_le_prove_non_escono_su_internet(self):
        with self.assertRaises(requests.ConnectionError):
            requests.get("https://www.portaleargo.it/", timeout=5)
        self.assertEqual(prove.TENTATIVI_RETE, ["www.portaleargo.it"])
        prove.TENTATIVI_RETE.clear()
        self.assertTrue(socket.getaddrinfo("127.0.0.1", 80))


if __name__ == "__main__":
    unittest.main()
