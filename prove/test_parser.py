import unittest
from datetime import date

import dati
import parser as estrai
import stats

OGGI = date(2026, 10, 8)

DASHBOARD = {
    "listaMaterie": [
        {"materia": "MATEMATICA", "abbreviazione": "MAT"}, {"materia": "STORIA", "abbreviazione": "STO"},
        {"materia": "FISICA", "abbreviazione": "FIS"}, {"materia": "LINGUA INGLESE", "abbreviazione": "ING"},
        {"materia": "TEC. E PROG. DI SISTEMI INFORMATICI E TELEC.", "abbreviazione": "TPI"},
        {"materia": "SISTEMI E RETI", "abbreviazione": "S.RET"},
    ],
    "listaDocentiClasse": [
        {"pk": "d1", "desCognome": "ROSSI", "desNome": "ANNA", "materie": ["MAT", "FIS"]},
        {"pk": "d2", "desCognome": "BIANCHI", "desNome": "LUCA", "materie": ["ING"]},
        {"pk": "d3", "desCognome": "NERI", "desNome": "EVA", "materie": ["TPI", "S.RET"]},
    ],
    "promemoria": [
        {"pk": "1", "datGiorno": "2026-10-12", "desAnnotazioni": "Verifica di storia <cap. 3>", "docente": "(Prof. VERDI UGO)", "pkDocente": "d9", "oraInizio": "09:00", "oraFine": "10:00"},
        {"pk": "2", "datGiorno": "2026-10-09", "desAnnotazioni": "Interrogazione", "docente": "L. BIANCHI", "pkDocente": "d2", "oraInizio": "00:00", "oraFine": "00:00"},
        {"pk": "3", "datGiorno": "2026-10-20", "desAnnotazioni": "Uscita didattica", "docente": "(Prof. ROSSI ANNA)", "pkDocente": "d1", "oraInizio": "08:00", "oraFine": "08:00"},
        {"pk": "6", "datGiorno": "2026-10-21", "desAnnotazioni": "Verifica pratica TPS", "docente": "E. NERI", "pkDocente": "d3", "oraInizio": "10:00", "oraFine": "12:00"},
        {"pk": "7", "datGiorno": "2026-10-22", "desAnnotazioni": "Prova di laboratorio Sistemi e Reti", "docente": "E. NERI", "pkDocente": "d3", "oraInizio": "10:00", "oraFine": "12:00"},
        {"pk": "8", "datGiorno": "2026-10-23", "desAnnotazioni": "Consegna del testo", "docente": "E. NERI", "pkDocente": "d3", "oraInizio": "10:00", "oraFine": "12:00"},
        {"pk": "4", "datGiorno": "2026-10-01", "desAnnotazioni": "Verifica passata", "docente": "", "pkDocente": ""},
        {"pk": "5", "operazione": "D"},
    ],
    "registro": [
        {"pk": "r1", "datGiorno": "2026-10-07", "materia": "MATEMATICA", "docente": "(Prof. ROSSI ANNA)", "compiti": [
            {"compito": "Es. 1-5 pag. 40", "dataConsegna": "2026-10-09"},
            {"compito": "Vecchio", "dataConsegna": "2026-10-07"},
        ]},
        {"pk": "r2", "datGiorno": "2026-10-07", "materia": "STORIA", "docente": "", "compiti": []},
    ],
    "voti": [
        {"pk": "v1", "datGiorno": "2026-09-20", "desMateria": "MATEMATICA", "valore": 4, "codCodice": "4", "codVotoPratico": "S", "faMenoMedia": ""},
        {"pk": "v2", "datGiorno": "2026-09-28", "desMateria": "MATEMATICA", "valore": 5.5, "codCodice": "5½", "codVotoPratico": "N", "faMenoMedia": "", "numMedia": 1.0},
        {"pk": "v3", "datGiorno": "2026-09-25", "desMateria": "STORIA", "valore": 8, "codCodice": "8", "codVotoPratico": "N", "faMenoMedia": "", "numMedia": 1.0},
        {"pk": "v4", "datGiorno": "2026-09-26", "desMateria": "STORIA", "valore": 0, "codCodice": "+", "codVotoPratico": "N", "faMenoMedia": "", "numMedia": 1.0},
        {"pk": "v5", "datGiorno": "2026-09-27", "desMateria": "STORIA", "valore": 3, "codCodice": "3", "codVotoPratico": "N", "faMenoMedia": "S"},
    ],
}


class ParserTest(unittest.TestCase):
    def test_promemoria(self):
        items = estrai.promemoria(DASHBOARD, OGGI)
        self.assertEqual([p.testo for p in items], ["Interrogazione", "Verifica di storia <cap. 3>", "Uscita didattica", "Verifica pratica TPS", "Prova di laboratorio Sistemi e Reti", "Consegna del testo"])
        self.assertEqual([p.verifica for p in items], [True, True, False, True, True, False])
        self.assertEqual([p.materia for p in items], ["Inglese", "Storia", "Matematica / Fisica", "TPSIT", "Sistemi e reti", "TPSIT / Sistemi e reti"])
        self.assertEqual([p.orario for p in items[:3]], ["", "09:00–10:00", "08:00"])
        self.assertEqual(items[0].docente, "L. BIANCHI")

    def test_compiti(self):
        items = estrai.compiti(DASHBOARD, OGGI)
        self.assertEqual([(c.materia, c.testo, c.consegna) for c in items], [("Matematica", "Es. 1-5 pag. 40", date(2026, 10, 9))])
        self.assertEqual(len(estrai.compiti(DASHBOARD)), 2)
        self.assertEqual(len(estrai.promemoria(DASHBOARD)), 7)

    def test_voti_e_statistiche(self):
        voti = estrai.voti(DASHBOARD)
        self.assertEqual(len(voti), 3)
        statistiche = stats.per_materia(voti)
        matematica, storia = statistiche
        self.assertEqual((matematica.materia, matematica.media, matematica.numero), ("Matematica", 4.75, 2))
        self.assertEqual((matematica.media_scritto, matematica.media_orale), (4, 5.5))
        self.assertEqual(matematica.minimo_sufficienza, 8.5)
        self.assertTrue(matematica.insufficiente)
        self.assertEqual(storia.minimo_sufficienza, 4)
        self.assertEqual(stats.media_generale(statistiche), 6.375)

    def test_voto_necessario(self):
        self.assertEqual(stats.voto_necessario([5, 5]), 8)
        self.assertEqual(stats.voto_necessario([2, 2, 2]), 18)
        self.assertEqual(stats.voto_necessario([6]), 6)
        self.assertEqual(stats.voto_necessario([9, 9]), 0)
        self.assertEqual(stats.voto_necessario([7, 7], obiettivo=8), 10)
        self.assertEqual(stats.voto_necessario([]), 6)

    def test_andamento(self):
        voti = [estrai.Voto(date(2026, 9, i + 1), "X", v, "", "Orale", "", "") for i, v in enumerate([4, 5, 7, 7, 8])]
        self.assertEqual(stats.per_materia(voti)[0].andamento, "su")

    def test_raggruppamenti_voti(self):
        voti = estrai.voti(DASHBOARD)
        self.assertEqual({d["fascia"]: d["numero"] for d in stats.distribuzione(voti) if d["numero"]}, {"4": 1, "5": 1, "8": 1})
        self.assertEqual(stats.per_mese(voti), [{"mese": "2026-09", "media": 17.5 / 3, "numero": 3}])
        self.assertEqual({t["tipo"]: t["media"] for t in stats.per_tipo(voti)}, {"Orale": 6.75, "Scritto": 4})
        periodi = [("Primo", date(2026, 9, 1), date(2026, 9, 22)), ("Secondo", date(2026, 9, 23), date(2027, 6, 1))]
        self.assertEqual([(p["numero"], p["media"]) for p in stats.per_periodo(voti, periodi)], [(1, 4), (2, 6.75)])

    def test_id_compito_stabile(self):
        primo, secondo = estrai.compiti(DASHBOARD), estrai.compiti(DASHBOARD)
        self.assertEqual([c.id for c in primo], [c.id for c in secondo])
        self.assertEqual(len({c.id for c in primo}), 2)

    def test_carico(self):
        carico = stats.carico(estrai.compiti(DASHBOARD), estrai.promemoria(DASHBOARD), OGGI)
        self.assertEqual((carico["totale_compiti"], carico["totale_verifiche"]), (2, 5))
        self.assertEqual(carico["per_materia"][0], {"materia": "Matematica", "compiti": 2, "verifiche": 0})
        settimane = {s["inizio"]: (s["compiti"], s["verifiche"], s["corrente"]) for s in carico["per_settimana"]}
        self.assertEqual(settimane[date(2026, 10, 5)], (2, 1, True))
        self.assertEqual(settimane[date(2026, 9, 28)], (0, 1, False))
        self.assertEqual(settimane[date(2026, 10, 19)], (0, 2, False))
        self.assertEqual(len(carico["prossimi_giorni"]), 14)
        self.assertEqual(carico["prossimi_giorni"][1], {"data": date(2026, 10, 9), "compiti": 1, "verifiche": 1})
        self.assertEqual(carico["per_giorno_settimana"][2], {"giorno": "Mercoledì", "compiti": 1})

    def test_assenze(self):
        registro = [{"datGiorno": g, "ora": o, "materia": m, "docente": ""} for g, o, m in [
            ("2026-09-10", 1, "STORIA"), ("2026-09-10", 2, "STORIA"), ("2026-09-10", 3, "MATEMATICA"),
            ("2026-09-11", 1, "MATEMATICA"), ("2026-09-11", 2, "STORIA"), ("2026-09-11", 3, "FISICA"), ("2026-09-11", 4, "FISICA"),
            ("2026-09-14", 1, "FISICA"), ("2026-09-14", 2, "STORIA"), ("2026-09-14", 2, "STORIA"),
        ]]
        appello = [
            {"data": "2026-09-10", "codEvento": "A", "descrizione": "Assenza", "nota": "", "giustificata": "S", "daGiustificare": True},
            {"data": "2026-09-11", "codEvento": "I", "descrizione": "Ritardo", "nota": "Ingresso in 3^ ora alle ore 10:05", "giustificata": "N", "daGiustificare": True},
            {"data": "2026-09-14", "codEvento": "U", "descrizione": "Uscita", "nota": "Uscita in 2^ ora", "giustificata": "S"},
            {"data": "2026-09-15", "codEvento": "A", "descrizione": "Assenza", "nota": ""},
            {"data": "2026-09-16", "operazione": "D"},
        ]
        dashboard = {"registro": registro, "appello": appello}
        a = stats.assenze(estrai.assenze(dashboard), estrai.lezioni(dashboard))
        self.assertEqual([e["ore"] for e in a["eventi"]], [3, 2, 1, None])
        self.assertEqual((a["giorni_assenza"], a["ritardi"], a["uscite"], a["da_giustificare"]), (2, 1, 1, 1))
        self.assertEqual((a["ore_perse"], a["ore_svolte"], a["eventi_senza_ore"]), (6, 9, 1))
        self.assertEqual({m["materia"]: m["ore"] for m in a["per_materia"]}, {"Storia": 4, "Matematica": 2})
        self.assertEqual((a["limite_ore"], a["ore_rimaste"]), (264, 258))
        self.assertEqual((a["ore_al_giorno"], a["previsione"]), (3, 704))  # 9 ore in 3 giorni; 6 perse su 9 → 2/3 di 32 × 33
        vuoto = stats.assenze([], [])
        self.assertEqual((vuoto["ore_al_giorno"], vuoto["previsione"]), (None, None))

    def test_consigli(self):
        voti = [estrai.Voto(date(2026, 9, i + 1), "Matematica", v, "", t, "", "") for i, (v, t) in enumerate([(4, "Scritto"), (5, "Scritto"), (7, "Orale")])]
        voti += [estrai.Voto(date(2026, 9, i + 1), "Storia", v, "", "Orale", "", "") for i, v in enumerate([9, 9, 7, 7, 7])]
        statistiche = stats.per_materia(voti)
        verifiche = [estrai.Promemoria(date(2026, 10, 9), "", m, "", "Verifica", True) for m in ("Matematica", "Storia")]
        carico = stats.carico([], verifiche, OGGI)
        voci = stats.consigli(statistiche, verifiche, ["Matematica", "Storia", "Fisica"], carico, OGGI)
        titoli = [v["titolo"] for v in voci]
        self.assertEqual(voci[0]["livello"], "critico")
        self.assertIn("serve almeno 8", voci[0]["testo"])
        self.assertIn("Verifica di Matematica domani", titoli)
        self.assertIn("Verifica di Storia domani", titoli)
        self.assertIn("Storia: in calo", titoli)
        self.assertIn("Matematica: divario tra scritto e orale", titoli)
        self.assertIn("Venerdì 9: 2 verifiche lo stesso giorno", titoli)
        self.assertEqual(voci[-1], {"livello": "info", "titolo": "Materie ancora senza voti", "testo": "Fisica."})
        self.assertEqual(stats.consigli([], [], ["Fisica"], stats.carico([], [], OGGI), OGGI), [])

    def test_orario(self):
        import orario
        import pdf_settimana

        argo = {
            "listaDocentiClasse": [
                {"desCognome": "FERRO", "desNome": "ALDO"}, {"desCognome": "FERRUCCI", "desNome": "SIMONE"},
                {"desCognome": "D'ANGELO", "desNome": "LUCIA GRAZIA"}, {"desCognome": "CARONE", "desNome": "BIANCA (coord.) "},
            ],
            "registro": [{"docente": "F. NICOLO'"}, {"docente": "A. FERRO"}],
        }
        noti = orario.docenti_noti(argo)
        nomi = {s: orario.nome_docente(s, noti) for s in ("FER_An", "FRR_S", "DNG_G", "CAR_B", "NIC_F", "ZAN_EF", "CAR_C")}
        self.assertEqual(nomi, {"FER_An": "A. FERRO", "FRR_S": "S. FERRUCCI", "DNG_G": "L. D'ANGELO", "CAR_B": "B. CARONE",
                                "NIC_F": "F. NICOLO'", "ZAN_EF": "ZAN_EF", "CAR_C": "CAR_C"})

        elementi = [
            {"type": 2, "id": 1, "name": "FER_An"}, {"type": 2, "id": 2, "name": "ZAN_EF"}, {"type": 2, "id": 3, "name": "FRR_S"},
            {"type": 3, "id": 10, "name": "INF", "longName": "INFORMATICA"}, {"type": 3, "id": 11, "name": "SMS", "longName": "SCIENZE MOTORIE"},
            {"type": 3, "id": 12, "name": "REL", "longName": "RELIGIONE"}, {"type": 3, "id": 13, "name": "TPS", "longName": "LAB TPSIT"},
            {"type": 4, "id": 20, "name": "1B05", "longName": "1B05"}, {"type": 4, "id": 21, "name": "LAB2", "longName": "LAB2"},
        ]
        def periodo(id_, data, inizio, stato, parti, **extra):
            return {"id": id_, "date": data, "startTime": inizio, "endTime": inizio + 100, "cellState": stato,
                    "elements": [{"type": t, "id": i, "orgId": o} for t, i, o in parti], **extra}
        settimana = {"elementi": elementi, "lezioni": [
            periodo(1, 20261008, 900, "STANDARD", [(2, 1, 0), (3, 10, 0), (4, 20, 0)]),
            periodo(2, 20261007, 1200, "SUBSTITUTION", [(2, 2, 3), (3, 11, 0), (4, 21, 0)], substText="Rec.", periodText="Rec."),
            periodo(3, 20261008, 800, "STANDARD", [(3, 12, 0)]),
            periodo(4, 20261009, 800, "CANCEL", [(2, 1, 0), (3, 13, 0), (4, 21, 20)]),
            periodo(5, 20261005, 800, "STANDBY", [(2, 1, 0), (3, 10, 0)]),
        ]}
        lezioni = orario.converti([settimana], noti)
        self.assertEqual([(l.data.day, l.inizio, l.fine, l.materia, l.stato) for l in lezioni], [
            (5, "08:00", "09:00", "Informatica", "regolare"), (7, "12:00", "13:00", "Scienze motorie", "supplenza"),
            (8, "09:00", "10:00", "Informatica", "regolare"), (9, "08:00", "09:00", "Lab TPSIT", "annullata")])
        supplenza, annullata = lezioni[1], lezioni[3]
        self.assertEqual((supplenza.docenti, supplenza.docenti_previsti, supplenza.aule, supplenza.nota), (["ZAN_EF"], ["S. FERRUCCI"], ["LAB2"], "Rec."))
        self.assertEqual(annullata.aule_previste, ["1B05"])
        self.assertTrue(supplenza.variazione and not lezioni[0].variazione)
        self.assertNotEqual(supplenza.chiave, annullata.chiave)
        settimane = orario.per_settimana(lezioni)
        self.assertEqual((settimane[0]["inizio"], settimane[0]["fine"], len(settimane[0]["giorni"])), (date(2026, 10, 5), date(2026, 10, 9), 4))
        self.assertEqual(settimane[0]["fasce"], [("08:00", "09:00"), ("09:00", "10:00"), ("12:00", "13:00")])

        pagina = dati.elabora({"dashboard": DASHBOARD, "profilo": {}}, OGGI)
        pagina["orario"] = dati._json({"scaricato": "2026-10-08T10:00:00", "settimane": settimane, "lezioni": [
            {**vars(l), "variazione": l.variazione, "nuova": False} for l in lezioni]})
        self.assertTrue(pdf_settimana.genera(pagina).startswith(b"%PDF"))
        with self.assertRaises(ValueError):
            pdf_settimana.genera({**pagina, "orario": None})

    def test_elabora(self):
        import json
        pagina = dati.elabora({"dashboard": DASHBOARD, "profilo": {"alunno": {"nominativo": "ROSSI MARIO"}}}, OGGI)
        json.dumps(pagina)
        self.assertEqual(pagina["studente"], "Rossi Mario")
        self.assertEqual([p["testo"] for p in pagina["promemoria"]][0], "Interrogazione")
        self.assertEqual([(c["testo"], c["consegna"]) for c in pagina["compiti"]], [("Vecchio", "2026-10-07"), ("Es. 1-5 pag. 40", "2026-10-09")])
        self.assertEqual(pagina["scartate"], {})
        self.assertEqual([(v["materia"], v["codice"]) for v in pagina["voti_fuori_media"]], [("Storia", "+"), ("Storia", "3")])
        self.assertEqual(pagina["media_generale"], 6.375)


if __name__ == "__main__":
    unittest.main()
