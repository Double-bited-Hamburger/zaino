"""Prove per i profili e per il registro Nuvola (con dati e risposte finti: nessun accesso reale)."""

import http.client
import json
import tempfile
import threading
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

import dati
import nuvola_adatta
import nuvola_client
import profili
import server
from archivio import ErroreRegistro

ARGO = {"nome": "Mario", "registro": "argo", "scuola": "SC12345", "utente": "mario.r", "password": "segreta-argo"}
NUVOLA = {"nome": "Amico", "registro": "nuvola", "utente": "amico", "password": "segreta-nuvola",
          "untis": {"server": "https://Scuola.WebUntis.com/", "scuola": "scuola", "classe": "3A"}}
CLASSEVIVA = {"nome": "Rossi", "registro": "classeviva", "utente": "genitore@example.com", "password": "segreta-cv"}
FIGLI = [{"ident": "S1234567X", "name": "MARIO ROSSI"}, {"ident": "S1111111X", "name": "LUCIA ROSSI"}]

def _ora(numero, *argomenti):
    return {"numeroOra": numero, "inizioOra": f"{7 + numero:02d}:00", "fineOra": f"{8 + numero:02d}:00", "giorno": "", "argomenti": list(argomenti)}


def _argomento(materia, tipo="Lezione ordinaria", nome="Spiegazione", docente="Rossi Anna"):
    return {"id": 1, "materia": materia, "docente": docente, "tipo": tipo, "nomeArgomento": nome, "annotazioni": None, "compresenza": "", "cofirme": []}


def _voto(giorno, materia, valutazione, tipologia="ORALE", fa_media=True, matematica=None):
    return {"data": giorno, "docente": "Rossi Anna", "tipologia": tipologia, "valutazione": valutazione, "valutazioneMatematica": matematica, "faMedia": fa_media,
            "peso": "100%", "descrizione": "Prova", "nomeObiettivo": None, "obiettivi": [], "nomeMateria": materia, "idMateria": 5, "idFrazioneTemporale": 1}


# Stessa forma delle risposte vere di Nuvola (nomi dei campi verificati su un account reale), contenuti inventati.
GREZZO_NUVOLA = {
    "alunno": {"id": 77, "nome": "Luca", "cognome": "Bianchi", "classe": "3A", "isTutore": True, "apiAttive": True},
    "frazioni": [{"id": 1, "nome": "1° QUADRIMESTRE", "corrente": True}, {"id": 3, "nome": "INTERO ANNO", "corrente": False}],
    "materie": [{"id": 5, "materia": "MATEMATICA"}, {"id": 6, "materia": "STORIA"}, {"id": 7, "materia": "MUSICA"}],
    "voti": [
        _voto("2026-10-01T00:00:00+02:00", "MATEMATICA", "7½", "SCRITTO"),
        _voto("2026-10-05T22:00:00Z", "MATEMATICA", "5+"),
        _voto("2026-10-06T00:00:00+02:00", "MATEMATICA", "4", "PRATICO", fa_media=False),
        _voto("2026-10-07T00:00:00+02:00", "MATEMATICA", "B."),
        _voto("2026-10-02T00:00:00+02:00", "STORIA", "8", matematica=8.0),
    ],
    "giorni": {
        "2026-10-07": {"compiti": [], "lezioni": [
            {"classe": "3A", "isGruppoClasse": False, "ore": [_ora(1, _argomento("STORIA", docente="Verdi Ugo")), _ora(2, _argomento("MATEMATICA"), _argomento("MATEMATICA")), _ora(3)]},
            {"classe": "3A gruppo", "isGruppoClasse": True, "ore": [_ora(1), _ora(7, _argomento("MUSICA"))]}]},
        "2026-10-08": {"compiti": [], "lezioni": [{"classe": "3A", "ore": [_ora(1, _argomento("STORIA", "Compito in classe", "Capitolo 2", "Verdi Ugo")), _ora(2, _argomento("MATEMATICA"))]}]},
        "2026-10-09": {"compiti": [{"docente": "Verdi Ugo", "materia": "STORIA", "nomeArgomento": "Cap. 3", "dataAssegnazione": "2026-10-07T00:00:00+02:00",
                                    "dataConsegna": "2026-10-09T00:00:00+02:00", "descrizioneCompito": ["Studiare cap. 3", "Esercizi pag. 40"], "allegati": []}], "lezioni": []},
        "2026-10-12": {"compiti": [{"materia": "MATEMATICA", "dataConsegna": "2026-10-12T00:00:00+02:00", "descrizioneCompito": ["Es. 5"]}, {"materia": "X", "descrizioneCompito": []}],
                       "lezioni": [{"classe": "3A", "ore": [_ora(3, _argomento("MATEMATICA", "Compito in classe", "Equazioni")), _ora(4, _argomento("MATEMATICA", "Compito in classe", "Equazioni")),
                                                           _ora(5, _argomento("STORIA", nome="Lezione programmata")), _ora(6, _argomento("MUSICA", nome="Verifica di teoria"))]}]},
    },
    "assenze": [{"id": 1, "data": "2026-10-07T00:00:00+02:00", "turno": "TURNO MATTINO", "tipo": "ASSENZA", "tipoAssenza": None, "giustificata": False, "giustificabile": True, "ora": None},
                {"id": 2, "data": "2026-10-07T00:00:00+02:00", "tipo": "USCITA", "giustificata": True, "giustificabile": False, "ora": "09:10"},
                {"id": 3, "data": "2026-09-20T00:00:00+02:00", "tipo": "RITARDO", "giustificata": False, "giustificabile": False, "ora": None}],
    "note": [],
    "eventi_classe": [{"id": 1, "tipo": "Evento", "nome": "Uscita didattica", "descrizione": "<p>Testo lungo</p>", "dataInizio": "2026-10-20T00:00:00+02:00", "oraInizio": "08:00",
                       "dataFine": "2026-10-20T00:00:00+02:00", "oraFine": "13:00", "docente": "Segreteria"}, {"tipo": "Avviso", "nome": "Circolare vecchia", "dataInizio": "2026-09-03T00:00:00+02:00"}],
    "eventi_alunno": "formato inatteso",
}


class Base(unittest.TestCase):
    def setUp(self):
        self.cartella = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(mock.patch.object(profili, "CARTELLA", self.cartella / "profili"))
        self.enterContext(mock.patch.object(profili, "BASE", self.cartella))
        self.portachiavi = None  # None = senza Gestione credenziali: le password vanno su file
        self.enterContext(mock.patch.object(profili, "_portachiavi", lambda: self.portachiavi))
        self.addCleanup(dati.attiva, None)
        dati.attiva(None)


class Profili(Base):
    def test_crea_modifica_elimina(self):
        a, n = profili.salva(dict(ARGO)), profili.salva(dict(NUVOLA))
        self.assertEqual([p["nome"] for p in profili.elenco()], ["Mario", "Amico"])
        self.assertNotIn("password", a)
        self.assertNotIn("segreta", (self.cartella / "profili" / "profili.json").read_text(encoding="utf-8"))
        self.assertEqual((profili.password(a["id"]), profili.password(n["id"])), ("segreta-argo", "segreta-nuvola"))
        self.assertEqual(n["untis"], {"server": "scuola.webuntis.com", "scuola": "scuola", "classe": "3A"})
        self.assertEqual((n["scuola"], a["untis"]), ("", None))

        # Modifica senza password: resta quella di prima. I dati scaricati restano se l'account non cambia.
        dati.attiva(a)
        dati._scrivi(dati.CACHE, {"dashboard": {}})
        profili.salva({**ARGO, "nome": "Max", "password": ""}, a["id"])
        self.assertEqual((profili.trova(a["id"])["nome"], profili.password(a["id"])), ("Max", "segreta-argo"))
        self.assertTrue(dati.CACHE.exists())
        profili.salva({**ARGO, "utente": "altro", "password": "nuova"}, a["id"])
        self.assertEqual(profili.password(a["id"]), "nuova")
        self.assertFalse(dati.CACHE.exists())

        self.assertEqual(profili.ultimo(), a["id"])
        profili.elimina(a["id"])
        self.assertEqual([p["id"] for p in profili.elenco()], [n["id"]])
        self.assertFalse(profili.cartella(a["id"]).exists())
        self.assertEqual((profili.password(a["id"]), profili.ultimo()), ("", None))

    def test_portachiavi_di_sistema(self):
        """Con il Gestione credenziali la password non viene mai scritta su file."""
        deposito = {}
        self.portachiavi = mock.Mock(set_password=lambda s, u, p: deposito.__setitem__((s, u), p), get_password=lambda s, u: deposito.get((s, u)),
                                     delete_password=lambda s, u: deposito.pop((s, u)))
        p = profili.salva(dict(ARGO))
        self.assertEqual(deposito, {("ParserCompiti", p["id"]): "segreta-argo"})
        self.assertFalse((profili.cartella(p["id"]) / "credenziali.json").exists())
        self.assertEqual(profili.password(p["id"]), "segreta-argo")
        profili.elimina(p["id"])
        self.assertEqual(deposito, {})
        # Se il portachiavi smette di funzionare si ripiega sul file, senza errori.
        self.portachiavi = mock.Mock(set_password=mock.Mock(side_effect=RuntimeError), get_password=mock.Mock(side_effect=RuntimeError))
        q = profili.salva(dict(ARGO))
        self.assertEqual(profili.password(q["id"]), "segreta-argo")

    def test_dati_non_validi(self):
        casi = [None, [], {}, {**ARGO, "registro": "altro"}, {**ARGO, "nome": "  "}, {**ARGO, "utente": ""}, {**ARGO, "scuola": ""}, {**ARGO, "password": ""},
                {**ARGO, "password": 123}, {**NUVOLA, "untis": {"server": "scuola.webuntis.com", "scuola": "", "classe": "3A"}},
                {**NUVOLA, "untis": {"server": "sito-qualsiasi.example", "scuola": "x", "classe": "y"}},
                {**NUVOLA, "untis": {"server": "127.0.0.1", "scuola": "x", "classe": "y"}}]
        for caso in casi:
            with self.assertRaises(profili.ProfiloNonValido, msg=str(caso)[:60]):
                profili.salva(caso)
        self.assertEqual(profili.elenco(), [])
        for id_sbagliato in ("../..", "", None, "ZZZZZZZZ", "abc"):
            with self.assertRaises(profili.ProfiloNonValido):
                profili.cartella(id_sbagliato)
        with self.assertRaises(profili.ProfiloNonValido):
            profili.salva(dict(ARGO), "00000000")

    def test_elenco_rovinato(self):
        (self.cartella / "profili").mkdir()
        for rovinato in ("{ troncato", "[]", '{"profili": "x"}', '{"profili": [1, {"nome": "senza id"}]}'):
            (self.cartella / "profili" / "profili.json").write_text(rovinato, encoding="utf-8")
            self.assertEqual(profili.elenco(), [])
        self.assertEqual(profili.salva(dict(ARGO))["nome"], "Mario")

    def test_migrazione_dalla_vecchia_versione(self):
        """Il vecchio .env con i suoi dati diventa il primo profilo, senza perdere nulla."""
        self.assertIsNone(profili.migra_vecchia_installazione())  # niente .env: nulla da fare
        (self.cartella / ".env").write_text("ARGO_SCUOLA=SC1\nARGO_UTENTE=mario\nARGO_PASSWORD=pw vecchia\n", encoding="utf-8")
        (self.cartella / "cache").mkdir()
        (self.cartella / "cache" / "dashboard.json").write_text(json.dumps({"dashboard": {"voti": []}, "profilo": {"alunno": {"nominativo": "ROSSI MARIO"}}}), encoding="utf-8")
        (self.cartella / "stato.json").write_text('{"fatti": {"abc": "2026-10-08T10:00:00"}}', encoding="utf-8")
        p = profili.migra_vecchia_installazione()
        self.assertEqual((p["nome"], p["registro"], p["scuola"], p["utente"]), ("Rossi Mario", "argo", "SC1", "mario"))
        self.assertEqual(profili.password(p["id"]), "pw vecchia")
        dati.attiva(p)
        self.assertEqual(dati.leggi_stato()["fatti"].keys(), {"abc"})
        self.assertIsNotNone(dati.carica())
        self.assertFalse((self.cartella / "stato.json").exists())
        self.assertIsNone(profili.migra_vecchia_installazione())  # una volta sola
        self.assertEqual(len(profili.elenco()), 1)

    def test_dati_separati_tra_profili(self):
        a, n = profili.salva(dict(ARGO)), profili.salva(dict(NUVOLA))
        dati.attiva(a)
        dati.segna_compito("compito-di-a", True)
        dati.attiva(n)
        self.assertEqual(dati.leggi_stato(), {"fatti": {}})
        dati.segna_compito("compito-di-n", True)
        dati.attiva(a)
        self.assertEqual(dati.leggi_stato()["fatti"].keys(), {"compito-di-a"})
        dati.attiva(None)
        self.assertIsNone(dati.carica())
        with self.assertRaises(ErroreRegistro):
            dati.segna_compito("x", True)
        with self.assertRaises(ErroreRegistro):
            dati.scarica()

    def test_studente_classeviva(self):
        c = profili.salva(dict(CLASSEVIVA))
        self.assertEqual(c["studente"], "")
        self.assertEqual(profili.salva({**ARGO, "studente": "S1234567X"})["studente"], "")  # solo per ClasseViva
        with self.assertRaises(profili.ProfiloNonValido):
            profili.salva({**CLASSEVIVA, "studente": "../x"}, c["id"])
        self.assertEqual(profili.studenti(c["id"]), [])
        profili.annota_studenti(c["id"], FIGLI)
        self.assertEqual(profili.studenti(c["id"]), FIGLI)

        # Scegliere il primo, che era già quello mostrato, non butta i dati scaricati; passare all'altro studente sì.
        dati.attiva(c)
        dati._scrivi(dati.CACHE, {"dashboard": {}})
        profili.salva({**CLASSEVIVA, "studente": "S1234567X", "password": ""}, c["id"])
        self.assertTrue(dati.CACHE.exists())
        profili.salva({**CLASSEVIVA, "studente": "S1111111X", "password": ""}, c["id"])
        self.assertFalse(dati.CACHE.exists())
        self.assertEqual((profili.trova(c["id"])["studente"], profili.password(c["id"])), ("S1111111X", "segreta-cv"))

        # Con un altro account l'elenco degli studenti non vale più; con uno studente solo non c'è elenco.
        profili.salva({**CLASSEVIVA, "utente": "altro@example.com", "password": ""}, c["id"])
        self.assertEqual(profili.studenti(c["id"]), [])
        profili.annota_studenti(c["id"], FIGLI)
        profili.annota_studenti(c["id"], [])
        self.assertFalse((profili.cartella(c["id"]) / "studenti.json").exists())

    def test_scarica_classeviva_con_lo_studente_scelto(self):
        c = profili.salva({**CLASSEVIVA, "studente": "S1111111X"})
        with mock.patch.object(dati, "ClassevivaClient") as cv, mock.patch.object(dati.classeviva_adatta, "converti", return_value=({}, {"voti": []})):
            cv.return_value.scelte = FIGLI
            cv.return_value.scarica.return_value = {}
            dati.attiva(c)
            dati.scarica()
        cv.assert_called_once_with("genitore@example.com", "segreta-cv", "S1111111X")
        self.assertEqual(profili.studenti(c["id"]), FIGLI)

    def test_classeviva_tiene_i_compiti_se_il_sito_non_risponde(self):
        c = profili.salva(dict(CLASSEVIVA))
        compito = {"homeworkDesc": "Leggere il cap. 4", "expiryDate": "2026-10-10", "subjectDesc": "STORIA"}
        with mock.patch.object(dati, "ClassevivaClient") as cv:
            cv.return_value.scelte = []
            dati.attiva(c)
            cv.return_value.scarica.return_value = {"compiti": [compito]}
            dati.scarica()
            cv.return_value.scarica.return_value = {"compiti": None}  # il sito non ha risposto
            self.assertEqual(dati.scarica()["classeviva"]["compiti"], [compito])

    def test_scarica_usa_il_registro_del_profilo(self):
        a, n = profili.salva(dict(ARGO)), profili.salva(dict(NUVOLA))
        with mock.patch.object(dati, "ArgoClient") as argo, mock.patch.object(dati, "NuvolaClient") as nuvola:
            argo.return_value.dashboard.return_value = ({"alunno": {}}, {"voti": []})
            nuvola.return_value.scarica.return_value = json.loads(json.dumps(GREZZO_NUVOLA))
            dati.attiva(a)
            dati.scarica()
            argo.assert_called_once_with("SC12345", "mario.r", "segreta-argo")
            nuvola.assert_not_called()
            dati.attiva(n)
            scaricati = dati.scarica()
            nuvola.assert_called_once_with("amico", "segreta-nuvola")
            self.assertEqual(len(scaricati["dashboard"]["voti"]), 5)
            # Secondo aggiornamento: i giorni già letti vengono passati al client e quelli vecchi restano.
            # Il giorno 9 viene riletto (ora senza compiti) e arriva un giorno nuovo, il 13.
            nuvola.return_value.scarica.return_value = {**GREZZO_NUVOLA, "giorni": {"2026-10-09": {"compiti": [], "lezioni": []}, "2026-10-13": {"compiti": [], "lezioni": []}}}
            scaricati = dati.scarica()
            self.assertEqual(set(nuvola.return_value.scarica.call_args.kwargs["giorni_gia_letti"]), {"2026-10-07", "2026-10-08", "2026-10-09", "2026-10-12"})
            self.assertEqual(set(scaricati["nuvola"]["giorni"]), {"2026-10-07", "2026-10-08", "2026-10-09", "2026-10-12", "2026-10-13"})
            self.assertEqual([c["materia"] for c in dati.elabora(scaricati, date(2026, 10, 8))["compiti"]], ["Matematica"])

    def test_cambio_profilo_durante_il_download(self):
        """Se si cambia profilo mentre scarica, i dati finiscono comunque nel profilo giusto."""
        a, n = profili.salva(dict(ARGO)), profili.salva(dict(NUVOLA))

        def dashboard_lenta():
            dati.attiva(n)  # l'utente cambia profilo a metà
            return {"alunno": {}}, {"voti": [], "segno": "dati di A"}

        with mock.patch.object(dati, "ArgoClient") as argo:
            argo.return_value.dashboard.side_effect = dashboard_lenta
            dati.attiva(a)
            dati.scarica()
        self.assertIsNone(dati.carica())  # il profilo N è rimasto vuoto
        dati.attiva(a)
        self.assertEqual(dati.carica()["dashboard"]["segno"], "dati di A")


class Nuvola(Base):
    def test_valore_del_voto(self):
        casi = {"7": 7, "7½": 7.5, "6+": 6.25, "7-": 6.75, "7/8": 7.5, "6,5": 6.5, "8.25": 8.25, "10": 10, "impreparato": 0, "": 0, "+": 0, "B.": 0}
        for testo, atteso in casi.items():
            self.assertEqual(nuvola_adatta.valore_voto({"valutazione": testo}), atteso, testo)
        self.assertEqual(nuvola_adatta.valore_voto({"valutazione": "7+", "valutazioneMatematica": 7.3}), 7.3)
        self.assertEqual(nuvola_adatta.valore_voto({"valutazione": "7+", "valutazioneMatematica": "7.25"}), 7.25)
        self.assertEqual(nuvola_adatta.valore_voto({"valutazioneMatematica": True}), 0)

    def test_giorno_in_ora_italiana(self):
        # Il giorno non dipende dal fuso del computer: conta l'ora italiana, con l'ora legale.
        casi = {"2026-12-01T22:30:00Z": "2026-12-01", "2026-12-01T23:30:00Z": "2026-12-02", "2026-07-01T21:30:00Z": "2026-07-01",
                "2026-07-01T22:30:00Z": "2026-07-02", "2026-03-29T00:30:00Z": "2026-03-29", "2026-10-24T22:30:00Z": "2026-10-25",
                "2026-10-01T00:00:00+02:00": "2026-10-01", "2026-10-01T00:00:00": "2026-10-01", "01/10/2026": "2026-10-01"}
        for testo, atteso in casi.items():
            self.assertEqual(nuvola_adatta._giorno(testo), atteso, testo)

    def pagina(self, giorno):
        return dati.elabora({"dashboard": {}, "profilo": {}, "nuvola": json.loads(json.dumps(GREZZO_NUVOLA)), "scaricato": "2026-10-08T07:00:00"}, giorno)

    def test_conversione(self):
        pagina = self.pagina(date(2026, 10, 8))
        json.dumps(pagina)
        self.assertEqual((pagina["studente"], pagina["classe"]), ("Bianchi Luca", "3A"))
        # Voti: mezzo voto, «5+», data in UTC riportata al giorno locale; fuori chi non fa media e i giudizi a lettere.
        self.assertEqual([(v["materia"], v["data"], v["valore"], v["tipo"], v["codice"]) for v in pagina["voti"]],
                         [("Matematica", "2026-10-01", 7.5, "Scritto", "7½"), ("Storia", "2026-10-02", 8.0, "Orale", "8"), ("Matematica", "2026-10-06", 5.25, "Orale", "5+")])
        self.assertEqual({s["materia"]: s["media"] for s in pagina["statistiche"]}, {"Matematica": 6.375, "Storia": 8})
        self.assertEqual(pagina["materie"], ["Matematica", "Musica", "Storia"])
        self.assertEqual([(v["codice"], v["tipo"]) for v in pagina["voti_fuori_media"]], [("4", "Pratico"), ("B.", "Orale")])
        # Compiti per giorno di consegna; quello senza testo è ignorato.
        self.assertEqual([(c["materia"], c["consegna"], c["assegnato"], c["testo"]) for c in pagina["compiti"]],
                         [("Storia", "2026-10-09", "2026-10-07", "Studiare cap. 3 Esercizi pag. 40"), ("Matematica", "2026-10-12", "2026-10-12", "Es. 5")])
        # Verifiche: i «Compito in classe» da oggi in poi (due ore consecutive = una voce), più le lezioni che nominano una verifica.
        self.assertEqual([(p["data"], p["orario"], p["materia"], p["verifica"], p["testo"]) for p in pagina["promemoria"]], [
            ("2026-10-08", "08:00–09:00", "Storia", True, "Compito in classe: Capitolo 2"),
            ("2026-10-12", "10:00–12:00", "Matematica", True, "Compito in classe: Equazioni"),
            ("2026-10-12", "13:00–14:00", "Musica", True, "Lezione ordinaria: Verifica di teoria"),
            ("2026-10-20", "08:00–13:00", "", False, "Uscita didattica")])
        # Assenze: giorno intero (3 ore firmate il 7), uscita alle 09:10 = dalla 2ª ora (2 ore), ritardo senza orario = ore non determinate.
        a = pagina["assenze"]
        self.assertEqual([(e["tipo"], e["ore"], e["da_giustificare"]) for e in a["eventi"]], [("ritardo", None, False), ("assenza", 3, True), ("uscita", 2, False)])
        self.assertEqual((a["ore_svolte"], a["eventi_senza_ore"]), (5, 1))
        self.assertEqual(pagina["scartate"], {})

    def test_il_giorno_dopo(self):
        """Riaprendo l'app il giorno dopo, la verifica di ieri non è più «in arrivo» e conta tra le lezioni svolte."""
        pagina = self.pagina(date(2026, 10, 9))
        self.assertEqual([p["data"] for p in pagina["promemoria"] if p["verifica"]], ["2026-10-12", "2026-10-12"])
        self.assertEqual(pagina["assenze"]["ore_svolte"], 5)

    def test_dati_nuvola_sporchi(self):
        """Qualunque forma abbiano i dati grezzi, la conversione non deve mai fermare l'app."""
        sporchi = [{}, {"voti": {}, "giorni": [], "assenze": {}, "frazioni": "x", "alunno": None, "materie": 5},
                   {"voti": [None, 5, {"nomeMateria": None, "data": 5, "valutazione": []}], "materie": [None, {"materia": 7}],
                    "giorni": {"2026-10-08": None, "x": {"compiti": [None, {"descrizioneCompito": {}}], "lezioni": "no"},
                               "2026-10-09": {"lezioni": [{"ore": [None, {"numeroOra": "x", "argomenti": [None, {"tipo": 5, "materia": []}]}, {"argomenti": "no"}]}, {"ore": 3}]}},
                    "assenze": [{"data": None, "tipo": None}, {"data": "2026-10-09T00:00:00+02:00", "tipo": "USCITA", "ora": "25:99"}],
                    "eventi_classe": [{"dataInizio": "ieri", "nome": 5}], "frazioni": [None, {"nome": 3}]}]
        for grezzo in sporchi:
            json.dumps(dati.elabora({"dashboard": {}, "nuvola": grezzo}, date(2026, 10, 8)))

    def test_client_con_risposte_finte(self):
        """Il percorso di accesso e di download, con un server Nuvola simulato."""
        chiamate, blocco = [], threading.Lock()

        class Risposta:
            def __init__(self, url, stato=200, dati=None, testo=""):
                self.url, self.status_code, self._dati, self.text, self.is_redirect = url, stato, dati, testo, stato in (301, 302)

            def json(self):
                if self._dati is None:
                    raise ValueError
                return self._dati

        def get(url, **k):
            with blocco:
                chiamate.append(url.replace(nuvola_client.API, ""))
            if url == nuvola_client.ACCESSO:
                return Risposta("https://auth.nuvola.madisoft.it/realms/nuvola/x", testo='<script>{"loginAction": "https:\\/\\/auth.nuvola.madisoft.it\\/azione?a=1\\u0026b=2"}</script>')
            if url.endswith("/login-from-web"):
                return Risposta(url, dati={"token": "tok"})
            if url.endswith("/alunni"):
                return Risposta(url, dati={"valori": [{"id": 77, "nome": "Luca", "apiAttive": True}]})
            if url.endswith("/frazioni-temporali"):
                return Risposta(url, dati={"valori": [{"id": 1, "nome": "Q1", "corrente": False}, {"id": 2, "nome": "Q2", "corrente": True}]})
            if url.endswith("/frazione-temporale/2/voti/materie"):
                return Risposta(url, dati={"valori": [{"id": 5, "materia": "MATEMATICA", "voti": []}]})
            if url.endswith("/voti"):
                return Risposta(url, dati={"valori": [{"valutazione": "7", "nomeMateria": "MATEMATICA"}]})
            if "/compito/elenco/" in url:
                return Risposta(url, dati={"valori": [{"materia": "STORIA"}]})
            if url.endswith("/note"):
                return Risposta(url, stato=404)
            if url.endswith("/eventi-classe"):
                return Risposta(url, stato=403)  # sezione disattivata dalla scuola: non deve fermare il download
            if url.endswith("/assenze"):
                return Risposta(url, dati=[{"id": 1}])
            return Risposta(url, dati={"valori": []})

        def post(url, data=None, **k):
            self.assertEqual(url, "https://auth.nuvola.madisoft.it/azione?a=1&b=2")
            giusta = data == {"username": "amico", "password": "pw", "credentialId": ""}
            return Risposta("https://nuvola.madisoft.it/area-tutore" if giusta else "https://auth.nuvola.madisoft.it/realms/nuvola/x")

        sessione = mock.Mock(get=get, post=post, headers={})
        with mock.patch.object(nuvola_client.requests, "Session", return_value=sessione):
            with self.assertRaisesRegex(nuvola_client.NuvolaError, "Login rifiutato"):
                nuvola_client.NuvolaClient("amico", "sbagliata").login()
            client = nuvola_client.NuvolaClient("amico", "pw")
            client.login()
            self.assertEqual(sessione.headers["Authorization"], "Bearer tok")
            chiamate.clear()
            oggi = date(2026, 10, 8)
            grezzo = client.scarica(oggi)
            self.assertEqual(len(grezzo["giorni"]), nuvola_client.GIORNI_INDIETRO + nuvola_client.GIORNI_AVANTI + 1)
            self.assertEqual((grezzo["materie"], grezzo["voti"]), ([{"id": 5, "materia": "MATEMATICA"}], [{"valutazione": "7", "nomeMateria": "MATEMATICA"}]))
            self.assertEqual((grezzo["note"], grezzo["eventi_classe"], grezzo["assenze"]), ([], [], [{"id": 1}]))
            self.assertIn("/alunno/77/compito/elenco/08-10-2026", chiamate)
            self.assertIn("/alunno/77/argomento-lezione/elenco/20-10-2026", chiamate)  # le lezioni future contengono le verifiche
            # Con i giorni passati già in cache si richiedono solo gli ultimi tre, oggi e quelli futuri.
            vecchi = {date.fromordinal(oggi.toordinal() - n).isoformat() for n in range(1, 31)}
            self.assertEqual(len(client.scarica(oggi, giorni_gia_letti=vecchi)["giorni"]), 3 + 1 + nuvola_client.GIORNI_AVANTI)

        # Casi di rifiuto: token non rilasciato, consultazione non attivata dalla scuola, sessione scaduta a metà.
        def con(sostituzioni):
            return lambda url, **k: next((r(url) for fine, r in sostituzioni.items() if url.endswith(fine)), None) or get(url, **k)

        casi = [({"/login-from-web": lambda u: Risposta(u, stato=302)}, "token"),
                ({"/alunni": lambda u: Risposta(u, dati={"valori": [{"id": 77, "apiAttive": False}]})}, "non ha attivato"),
                ({"/alunni": lambda u: Risposta(u, stato=401)}, "scaduta")]
        for sostituzioni, messaggio in casi:
            sessione.get = con(sostituzioni)
            with mock.patch.object(nuvola_client.requests, "Session", return_value=sessione):
                with self.assertRaisesRegex(nuvola_client.NuvolaError, messaggio):
                    nuvola_client.NuvolaClient("amico", "pw").login()



class ServerProfili(Base):
    PORTA = 8798

    def setUp(self):
        super().setUp()
        self.enterContext(mock.patch.object(server, "REGISTRO_ERRORI", self.cartella / "errori.log"))
        self.enterContext(mock.patch.object(server.config, "PORTA", self.PORTA))
        self.app = server.avvia()
        threading.Thread(target=self.app.serve_forever, daemon=True).start()
        self.addCleanup(self.app.server_close)
        self.addCleanup(self.app.shutdown)
        self.cookie = ""  # come il browser: ricorda il cookie del profilo scelto

    def chiama(self, metodo, percorso, corpo=None):
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

    def test_percorso_completo(self):
        stato, elenco = self.chiama("GET", "/api/profili")
        self.assertEqual((stato, elenco["profili"], elenco["attivo"]), (200, [], None))
        self.assertEqual(set(elenco["registri"]), {"argo", "nuvola", "classeviva"})
        self.assertTrue(self.chiama("GET", "/api/dati")[1]["senza_profilo"])
        self.assertEqual(self.chiama("POST", "/api/stato", {"id": "x", "fatto": True})[0], 409)
        self.assertEqual(self.chiama("POST", "/api/aggiorna", {})[0], 502)

        # Creazione: dati sbagliati rifiutati, password mai restituita.
        self.assertEqual(self.chiama("POST", "/api/profili", {"profilo": {**ARGO, "scuola": ""}})[0], 400)
        self.assertEqual(self.chiama("POST", "/api/profili", {"profilo": "x"})[0], 400)
        stato, risposta = self.chiama("POST", "/api/profili", {"profilo": ARGO})
        a = risposta["salvato"]
        n = self.chiama("POST", "/api/profili", {"profilo": NUVOLA})[1]["salvato"]
        self.assertNotIn("segreta", json.dumps(self.chiama("GET", "/api/profili")[1]))

        # Ogni profilo ha le sue spunte e i suoi dati.
        self.assertEqual(self.chiama("POST", "/api/profili/attiva", {"id": a})[1]["attivo"], a)
        self.chiama("POST", "/api/stato", {"id": "di-a", "fatto": True})
        with mock.patch.object(dati, "ArgoClient") as argo:
            argo.return_value.dashboard.return_value = ({"alunno": {"nominativo": "ROSSI MARIO"}}, {"voti": []})
            stato, pagina = self.chiama("POST", "/api/aggiorna", {})
        self.assertEqual((stato, pagina["studente"], pagina["profilo"]["nome"]), (200, "Rossi Mario", "Mario"))
        self.assertNotIn("segreta", json.dumps(pagina))
        self.assertEqual(self.chiama("POST", "/api/profili/attiva", {"id": n})[1]["attivo"], n)
        pagina = self.chiama("GET", "/api/dati")[1]
        self.assertEqual((pagina.get("vuoto"), pagina["stato"], pagina["profilo"]["registro"]), (True, {"fatti": {}}, "nuvola"))
        with mock.patch.object(dati, "NuvolaClient") as nuvola, mock.patch.object(dati.untis_client, "scarica", return_value=[]):
            nuvola.return_value.scarica.return_value = json.loads(json.dumps(GREZZO_NUVOLA))
            stato, pagina = self.chiama("POST", "/api/aggiorna", {})
        self.assertEqual((stato, pagina["studente"], len(pagina["voti"])), (200, "Bianchi Luca", 3))

        # Modifica del profilo attivo, profilo inesistente, uscita, eliminazione.
        self.assertEqual(self.chiama("POST", "/api/profili", {"id": n, "profilo": {**NUVOLA, "nome": "Luca", "password": ""}})[0], 200)
        self.assertEqual(self.chiama("GET", "/api/dati")[1]["profilo"]["nome"], "Luca")
        self.assertEqual(self.chiama("POST", "/api/profili/attiva", {"id": "ffffffff"})[0], 404)
        self.assertEqual(self.chiama("POST", "/api/profili/elimina", {"id": "../.."})[0], 400)
        stato, elenco = self.chiama("POST", "/api/profili/elimina", {"id": n})
        self.assertEqual((elenco["attivo"], [p["id"] for p in elenco["profili"]]), (None, [a]))
        self.assertIsNone(self.chiama("POST", "/api/profili/attiva", {"id": None})[1]["attivo"])
        self.assertFalse((self.cartella / "errori.log").exists())

    def test_studenti_classeviva_nell_elenco_dei_profili(self):
        self.chiama("POST", "/api/profili", {"profilo": ARGO})
        c = self.chiama("POST", "/api/profili", {"profilo": CLASSEVIVA})[1]["salvato"]
        self.assertEqual(self.chiama("GET", "/api/profili")[1]["studenti"], {})
        profili.annota_studenti(c, FIGLI)
        self.assertEqual(self.chiama("GET", "/api/profili")[1]["studenti"], {c: FIGLI})
        stato, risposta = self.chiama("POST", "/api/profili", {"id": c, "profilo": {**CLASSEVIVA, "studente": "S1111111X", "password": ""}})
        self.assertEqual((stato, next(p for p in risposta["profili"] if p["id"] == c)["studente"]), (200, "S1111111X"))

    def test_ricerca_scuole_webuntis(self):
        trovate = {"result": {"schools": [{"displayName": "ITI Esempio", "address": "Bergamo", "server": "esempio.webuntis.com", "loginName": "esempio"}, {"displayName": "senza server"}]}}
        with mock.patch.object(server.untis_client.requests, "post") as post:
            post.return_value.json.return_value = trovate
            self.assertEqual(self.chiama("GET", "/api/untis/scuole?q=esempio")[1]["scuole"],
                             [{"nome": "ITI Esempio", "indirizzo": "Bergamo", "server": "esempio.webuntis.com", "scuola": "esempio"}])
            self.assertEqual(self.chiama("GET", "/api/untis/scuole?q=ab")[1]["scuole"], [])  # troppo corto: nessuna chiamata
            self.assertEqual(post.call_count, 1)
            post.return_value.json.return_value = {"error": {"message": "too many results"}}
            self.assertEqual(self.chiama("GET", "/api/untis/scuole?q=scuola")[1]["scuole"], [])


if __name__ == "__main__":
    unittest.main()
