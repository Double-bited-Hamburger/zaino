"""Prove dell'orario scritto a mano, delle ore doppie (Italiano-Storia) e del limite di assenze calcolato sull'orario."""

import http.client
import threading
import unittest
from datetime import date
from unittest import mock

import config
import dati
import orario
import profili
import server
import stats
import test_profili
from test_profili import ARGO, NUVOLA, Base

LUNEDI = date(2026, 1, 5)
DOPPIA = "ITALIANO - STORIA"
CHIAVE = "italiano - storia|0|12:00"


def _ora(giorno=0, inizio="08:00", fine="09:00", materia="Matematica", **altro):
    return {"giorno": giorno, "inizio": inizio, "fine": fine, "materia": materia, **altro}


def _settimana(materia=DOPPIA, giorno=20260105, inizio=1200):
    """Una settimana di WebUntis con una sola lezione."""
    return {"elementi": [{"type": orario.MATERIA, "id": 1, "name": materia}],
            "lezioni": [{"id": 7, "date": giorno, "startTime": inizio, "endTime": inizio + 100, "elements": [{"type": orario.MATERIA, "id": 1}]}]}


def _settimana_piena(ore):
    """`ore` ore distinte, spalmate su lunedì-venerdì: quello che basta per ore_settimanali."""
    return [_ora(i % 5, f"{8 + i // 5:02d}:00", f"{9 + i // 5:02d}:00") for i in range(ore)]


class OreDoppie(unittest.TestCase):
    def setUp(self):
        self.enterContext(mock.patch.object(config, "ORARIO_DIVISIONE", {}))

    def test_parti(self):
        self.assertEqual(orario.parti("ITALIANO - STORIA"), ["Italiano", "Storia"])
        self.assertEqual(orario.parti("Italiano/Storia"), ["Italiano", "Storia"])
        self.assertEqual(orario.parti("Fisica"), [])
        self.assertEqual(orario.parti("Lingua-L2"), [])  # «L2» non è una materia: è un nome con il trattino
        self.assertEqual(orario.parti(""), [])
        self.assertEqual(orario.parti(None), [])

    def test_chiave(self):
        self.assertEqual(orario.chiave_divisione(f" {DOPPIA} ", 0, "12:00"), CHIAVE)

    def test_senza_scelta_resta_doppia(self):
        lezione = orario.converti([_settimana()])[0]
        self.assertEqual((lezione.materia, lezione.originale, lezione.scelte), ("Italiano - storia", DOPPIA, ["Italiano", "Storia"]))

    def test_scelta_in_converti(self):
        lezione = orario.converti([_settimana()], divisione={CHIAVE: "Storia"})[0]
        self.assertEqual((lezione.materia, lezione.originale), ("Storia", DOPPIA))
        # La scelta vale solo per quel giorno e quell'ora.
        self.assertEqual(orario.converti([_settimana(inizio=1000)], divisione={CHIAVE: "Storia"})[0].materia, "Italiano - storia")
        self.assertEqual(orario.converti([_settimana(giorno=20260106)], divisione={CHIAVE: "Storia"})[0].materia, "Italiano - storia")

    def test_scelta_in_manuali(self):
        ore = [_ora(0, "12:00", "13:00", DOPPIA)]
        self.assertEqual(orario.manuali(ore, LUNEDI)[0].scelte, ["Italiano", "Storia"])
        self.assertEqual({l.materia for l in orario.manuali(ore, LUNEDI, {CHIAVE: "Italiano"})}, {"Italiano"})

    def test_config_ancora_valida(self):
        regole = {DOPPIA.lower(): {(0, "12:00"): "Italiano"}, "laboratorio": {(0, "12:00"): "Fisica"}}
        with mock.patch.object(config, "ORARIO_DIVISIONE", regole):
            self.assertEqual(orario.converti([_settimana()])[0].materia, "Italiano")
            self.assertEqual(orario.converti([_settimana()], divisione={CHIAVE: "Storia"})[0].materia, "Storia")  # la pagina vince
            lezione = orario.converti([_settimana("Laboratorio")])[0]  # una materia sola, come prima
            self.assertEqual((lezione.materia, lezione.originale, lezione.scelte), ("Fisica", "", []))


class OrarioManuale(unittest.TestCase):
    def test_due_settimane(self):
        lezioni = orario.manuali([_ora(4, aula="A1", docente="Bianchi"), _ora(0)], date(2026, 1, 7))
        self.assertEqual([l.data for l in lezioni], [date(2026, 1, 5), date(2026, 1, 9), date(2026, 1, 12), date(2026, 1, 16)])
        self.assertEqual((lezioni[1].aule, lezioni[1].docenti, lezioni[0].aule, lezioni[0].docenti), (["A1"], ["Bianchi"], [], []))
        self.assertEqual(len({l.chiave for l in lezioni}), 4)

    def test_di_domenica_parte_dalla_settimana_che_inizia(self):
        self.assertEqual(orario.manuali([_ora(0)], date(2026, 1, 4))[0].data, LUNEDI)
        self.assertEqual(orario.manuali([_ora(0)], date(2026, 1, 3))[0].data, date(2025, 12, 29))  # di sabato no

    def test_ore_settimanali(self):
        self.assertEqual(orario.ore_settimanali(orario.manuali(_settimana_piena(30), LUNEDI)), 30)
        self.assertIsNone(orario.ore_settimanali(orario.manuali(_settimana_piena(9), LUNEDI)))
        self.assertEqual(orario.ore_settimanali(orario.manuali(_settimana_piena(10), LUNEDI)), 10)
        self.assertIsNone(orario.ore_settimanali([]))

    def test_ore_settimanali_non_conta_le_aggiunte_e_i_doppioni(self):
        lezioni = orario.manuali(_settimana_piena(10), LUNEDI)
        extra = orario.Lezione(LUNEDI, "15:00", "16:00", "Recupero", stato="aggiuntiva")
        insieme = orario.Lezione(LUNEDI, "08:00", "09:00", "Inglese")  # la classe divisa in due gruppi: è la stessa ora
        self.assertEqual(orario.ore_settimanali(lezioni + [extra, insieme]), 10)

    def test_settimana_piu_piena(self):
        lezioni = orario.manuali(_settimana_piena(30), LUNEDI)
        self.assertEqual(orario.ore_settimanali([l for l in lezioni if l.data < date(2026, 1, 12) or l.inizio == "08:00"]), 30)


class ImpostaOrario(Base):
    def setUp(self):
        super().setUp()
        self.profilo = profili.salva(dict(ARGO))

    def imposta(self, *ore):
        return profili.imposta_orario(self.profilo["id"], ore=list(ore))

    def test_salva_in_ordine_e_aggiorna_modificato(self):
        with mock.patch.object(profili, "adesso", return_value="2099-01-01T00:00:00"):
            profilo = self.imposta(_ora(1, aula=" A1 "), _ora(0, "09:00", "10:00"), _ora(0))
        self.assertEqual([(o["giorno"], o["inizio"]) for o in profilo["orario_personale"]["ore"]], [(0, "08:00"), (0, "09:00"), (1, "08:00")])
        self.assertEqual(profilo["orario_personale"]["ore"][2]["aula"], "A1")
        self.assertEqual(profilo["modificato"], "2099-01-01T00:00:00")

    def test_righe_senza_materia_saltate(self):
        profilo = self.imposta(_ora(), _ora(1, materia="  "), _ora(9, "brutto", "", materia=""))
        self.assertEqual(len(profilo["orario_personale"]["ore"]), 1)

    def test_rifiuta(self):
        cattive = {
            "giorno": [_ora(6)], "domenica negativa": [_ora(-1)], "giorno testo": [_ora("0")], "giorno sì/no": [_ora(True)],
            "ora scritta male": [_ora(inizio="8:00")], "ora impossibile": [_ora(fine="25:00")],
            "fine prima": [_ora(inizio="10:00", fine="09:00")], "fine uguale": [_ora(inizio="09:00", fine="09:00")],
            "stesso inizio": [_ora(), _ora(fine="10:00", materia="Fisica")],
            "troppe": [_ora()] * (profili.MASSIMO_ORE + 1), "non un'ora": ["lunedì"],
        }
        for nome, ore in cattive.items():
            with self.subTest(nome), self.assertRaises(profili.ProfiloNonValido):
                self.imposta(*ore)
        with self.assertRaises(profili.ProfiloNonValido):
            profili.imposta_orario(self.profilo["id"], ore="lunedì")
        self.assertNotIn("orario_personale", profili.trova(self.profilo["id"]))

    def test_ottanta_ore_vanno_bene(self):
        ore = [_ora(g, f"{h:02d}:{m}", f"{h:02d}:{m[0]}5") for g in range(6) for h in range(7, 12) for m in ("00", "10", "20")]
        self.assertEqual(len(self.imposta(*ore[:80])["orario_personale"]["ore"]), 80)

    def test_profilo_sconosciuto(self):
        with self.assertRaises(profili.ProfiloNonValido):
            profili.imposta_orario("ffffffff", ore=[])

    def test_divisione(self):
        identita = self.profilo["id"]
        profilo = profili.imposta_orario(identita, divisione=(CHIAVE, "Storia"))
        self.assertEqual(profilo["orario_personale"], {"divisione": {CHIAVE: "Storia"}})
        self.assertEqual(profili.imposta_orario(identita, divisione=(CHIAVE, ""))["orario_personale"], {})
        for cattiva in ((None, "Storia"), ("", "Storia"), ("x" * 141, "Storia"), (CHIAVE, 3)):
            with self.subTest(cattiva), self.assertRaises(profili.ProfiloNonValido):
                profili.imposta_orario(identita, divisione=cattiva)

    def test_ore_e_divisione_convivono(self):
        self.imposta(_ora())
        profilo = profili.imposta_orario(self.profilo["id"], divisione=(CHIAVE, "Storia"))
        self.assertEqual(len(profilo["orario_personale"]["ore"]), 1)
        self.assertEqual(self.imposta(_ora(1))["orario_personale"]["divisione"], {CHIAVE: "Storia"})

    def test_modificare_il_profilo_non_lo_perde(self):
        self.imposta(_ora())
        salvato = profili.salva({**ARGO, "nome": "Altro nome"}, self.profilo["id"])
        self.assertEqual(salvato["nome"], "Altro nome")
        self.assertEqual(profili.trova(self.profilo["id"])["orario_personale"]["ore"][0]["materia"], "Matematica")


class LezioniOrario(Base):
    def attiva(self, *ore, modello=ARGO):
        profilo = profili.salva(dict(modello))
        if ore:
            profilo = profili.imposta_orario(profilo["id"], ore=list(ore))
        dati.attiva(profilo, ricorda=False)
        return profilo

    def test_nessun_orario(self):
        self.attiva()
        self.assertEqual(dati.lezioni_orario({}), ([], None))

    def test_a_mano(self):
        self.attiva(_ora())
        lezioni, grezzo = dati.lezioni_orario({}, LUNEDI)
        self.assertEqual((len(lezioni), grezzo["fonte"]), (2, "manuale"))

    def test_webuntis_vince_sulle_ore_a_mano(self):
        self.attiva(_ora(), modello=NUVOLA)
        self.assertEqual(dati.lezioni_orario({}, LUNEDI)[1]["fonte"], "manuale")  # WebUntis non ancora scaricato
        dati._scrivi(dati.CACHE_ORARIO, {"scaricato": "2026-01-05T08:00:00", "settimane": [_settimana()], "viste": {}})
        lezioni, grezzo = dati.lezioni_orario({}, LUNEDI)
        self.assertEqual(([l.originale for l in lezioni], grezzo["fonte"]), ([DOPPIA], "untis"))

    def test_scelta_nella_pagina(self):
        profilo = self.attiva(modello=NUVOLA)
        dati._scrivi(dati.CACHE_ORARIO, {"scaricato": "2026-01-05T08:00:00", "settimane": [_settimana()], "viste": {}})
        dati.attiva(profili.imposta_orario(profilo["id"], divisione=(CHIAVE, "Storia")), ricorda=False)
        pagina = dati.elabora({"dashboard": {}, "profilo": {}}, LUNEDI)
        self.assertEqual(pagina["orario"]["fonte"], "untis")
        self.assertEqual((pagina["orario"]["lezioni"][0]["materia"], pagina["orario"]["lezioni"][0]["originale"]), ("Storia", DOPPIA))

    def test_la_pagina_usa_le_ore_dell_orario(self):
        self.attiva(*_settimana_piena(30))
        pagina = dati.elabora({"dashboard": {}, "profilo": {}}, LUNEDI)
        self.assertEqual(pagina["orario"]["fonte"], "manuale")
        self.assertEqual((pagina["assenze"]["ore_settimanali"], pagina["assenze"]["ore_dall_orario"]), (30, True))


class LimiteAssenze(unittest.TestCase):
    def test_dall_orario(self):
        a = stats.assenze([], [], 30)
        self.assertEqual(a["limite_ore"], round(30 * config.SETTIMANE_SCUOLA * config.LIMITE_ASSENZE))
        self.assertEqual((a["ore_settimanali"], a["ore_dall_orario"]), (30, True))

    def test_senza_orario_resta_la_stima(self):
        a = stats.assenze([], [])
        self.assertEqual(a["limite_ore"], round(config.ORE_SETTIMANALI * config.SETTIMANE_SCUOLA * config.LIMITE_ASSENZE))
        self.assertEqual((a["ore_settimanali"], a["ore_dall_orario"]), (config.ORE_SETTIMANALI, False))


class ServerOrario(Base):
    PORTA = 8799
    chiama = test_profili.ServerProfili.chiama

    def setUp(self):
        super().setUp()
        self.enterContext(mock.patch.object(server, "REGISTRO_ERRORI", self.cartella / "errori.log"))
        self.enterContext(mock.patch.object(server.config, "PORTA", self.PORTA))
        self.app = server.avvia()
        threading.Thread(target=self.app.serve_forever, daemon=True).start()
        self.addCleanup(self.app.server_close)
        self.addCleanup(self.app.shutdown)
        self.cookie = ""

    def attiva(self):
        profilo = profili.salva(dict(ARGO))
        self.chiama("POST", "/api/profili/attiva", {"id": profilo["id"]})
        dati._scrivi(dati.CACHE, {"dashboard": {}, "profilo": {}})
        return profilo

    def test_senza_profilo(self):
        self.assertEqual(self.chiama("POST", "/api/orario", {"ore": []})[0], 409)

    def test_andata_e_ritorno(self):
        profilo = self.attiva()
        stato, pagina = self.chiama("POST", "/api/orario", {"ore": _settimana_piena(12)})
        self.assertEqual((stato, pagina["orario"]["fonte"], pagina["assenze"]["ore_settimanali"]), (200, "manuale", 12))
        self.assertEqual(len(pagina["profilo"]["orario_personale"]["ore"]), 12)
        self.assertEqual(len(profili.trova(profilo["id"])["orario_personale"]["ore"]), 12)

        stato, pagina = self.chiama("POST", "/api/orario", {"ore": [_ora(materia=DOPPIA)]})
        self.assertEqual(pagina["orario"]["lezioni"][0]["scelte"], ["Italiano", "Storia"])
        chiave = orario.chiave_divisione(DOPPIA, 0, "08:00")
        stato, pagina = self.chiama("POST", "/api/orario", {"chiave": chiave, "materia": "Storia"})
        self.assertEqual((stato, pagina["orario"]["lezioni"][0]["materia"]), (200, "Storia"))
        stato, pagina = self.chiama("POST", "/api/orario", {"chiave": chiave, "materia": ""})
        self.assertEqual((stato, pagina["orario"]["lezioni"][0]["materia"]), (200, "Italiano - storia"))

        stato, pagina = self.chiama("POST", "/api/orario", {"ore": []})
        self.assertEqual((stato, pagina["orario"]), (200, None))

    def test_ore_non_valide(self):
        self.attiva()
        stato, risposta = self.chiama("POST", "/api/orario", {"ore": [_ora(inizio="10:00", fine="09:00")]})
        self.assertEqual(stato, 400)
        self.assertIn("errore", risposta)

    def test_orario_piu_lungo_ci_sta(self):
        self.attiva()
        ore = [_ora(g, f"{h:02d}:{m}", f"{h:02d}:{m[0]}5", "Tecnologie e progettazione di sistemi", aula="Laboratorio", docente="Rossi")
               for g in range(6) for h in range(7, 12) for m in ("00", "10", "20")]
        self.assertEqual(self.chiama("POST", "/api/orario", {"ore": ore[:80]})[0], 200)


if __name__ == "__main__":
    unittest.main()
