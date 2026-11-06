"""Prove di tenuta: un anno scolastico intero simulato, dati sporchi e casi limite."""

import copy
import json
import random
import tempfile
import threading
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

import dati
import orario
import profili
import pdf_settimana
import stats

MATERIE = [
    ("ITA", "LINGUA E LETTERATURA ITALIANA"), ("STO", "STORIA"), ("ING", "LINGUA INGLESE"),
    ("MAT", "MATEMATICA/COMPLEMENTI DI MATEMATICA"), ("INF", "INFORMATICA"), ("TEL", "TELECOMUNICAZIONI"),
    ("S.RET", "SISTEMI E RETI"), ("TPI", "TEC. E PROG. DI SISTEMI INFORMATICI E TELEC."), ("SMS", "SCIENZE MOTORIE E SPORTIVE"),
]
DOCENTI = [("ROSSI", "ANNA", ["ITA", "STO"]), ("BIANCHI", "LUCA", ["ING"]), ("VERDI", "UGO MARIA", ["MAT"]),
           ("NERI", "EVA", ["INF", "S.RET", "TPI"]), ("GALLI", "PIA", ["TEL"]), ("D'AMICO", "IVO", ["SMS"])]
INIZIO, FINE = date(2026, 9, 14), date(2027, 6, 8)
PROFILO_PROVA = {"id": "0000abcd", "nome": "Prova", "registro": "argo", "scuola": "SC1", "utente": "u",
                 "untis": {"server": "prova.webuntis.com", "scuola": "prova", "classe": "1A"}}


def anno_simulato(seme=1):
    """Una dashboard Argo verosimile per tutto l'anno: lezioni, compiti, promemoria, voti, assenze."""
    r = random.Random(seme)
    docenti = [{"pk": f"d{i}", "desCognome": c, "desNome": n, "materie": m, "desEmail": ""} for i, (c, n, m) in enumerate(DOCENTI)]
    di_materia = {a: d for d in docenti for a in d["materie"]}
    firma = lambda d: f"{d['desNome'][0]}. {d['desCognome']}"
    registro, promemoria, voti, appello = [], [], [], []
    giorno, n = INIZIO, 0
    while giorno <= FINE:
        vacanza = date(2026, 12, 23) <= giorno <= date(2027, 1, 6) or date(2027, 3, 25) <= giorno <= date(2027, 3, 30)
        if giorno.weekday() < 5 and not vacanza:
            for ora in range(1, r.choice([6, 6, 6, 8]) + 1):
                sigla, materia = r.choice(MATERIE)
                docente = di_materia[sigla]
                compiti = []
                if r.random() < 0.3:
                    compiti.append({"compito": f"Esercizi pag. {r.randint(1, 400)}\n n. {r.randint(1, 90)} <b>&", "dataConsegna": (giorno + timedelta(days=r.randint(1, 9))).isoformat()})
                registro.append({"pk": f"r{n}", "datGiorno": giorno.isoformat(), "ora": ora, "materia": materia, "pkMateria": sigla,
                                 "docente": firma(docente), "pkDocente": docente["pk"], "compiti": compiti, "attivita": "Lezione", "operazione": "I"})
                n += 1
                if r.random() < 0.035:
                    quando = giorno + timedelta(days=r.randint(2, 15))
                    testo = r.choice(["Verifica di {}", "Interrogazioni {}", "Uscita didattica", "VERIFICA", "Consegna relazione {}", "test {}"]).format(materia.lower())
                    promemoria.append({"pk": f"p{n}", "datGiorno": quando.isoformat(), "desAnnotazioni": testo, "docente": firma(docente),
                                       "pkDocente": docente["pk"], "oraInizio": f"{7 + ora:02d}:00", "oraFine": f"{8 + ora:02d}:00", "operazione": "I"})
                if r.random() < 0.1:
                    valore = r.choice([3, 4, 4.5, 5, 5.5, 6, 6, 6.5, 7, 7, 7.5, 8, 8.5, 9, 10, 0])
                    voti.append({"pk": f"v{n}", "datGiorno": giorno.isoformat(), "desMateria": materia, "pkMateria": sigla, "valore": valore,
                                 "codCodice": str(valore) if valore else "+", "codVotoPratico": r.choice("SNP"), "faMenoMedia": r.choice(["", "", "", "S"]),
                                 "numMedia": 1.0, "docente": firma(docente), "descrizioneProva": "Prova", "desCommento": None, "operazione": "I"})
            if r.random() < 0.08:
                tipo = r.choice("AAIU")
                nota = {"A": "", "I": f"Ingresso in {r.randint(1, 3)}^ ora alle ore 09:05", "U": r.choice([f"Uscita in {r.randint(3, 6)}^ ora", "Uscita anticipata"])}[tipo]
                appello.append({"pk": f"a{n}", "data": giorno.isoformat(), "datEvento": f"{giorno.isoformat()} 00:00:00", "codEvento": tipo,
                                "descrizione": {"A": "Assenza", "I": "Ritardo", "U": "Uscita"}[tipo], "nota": nota,
                                "giustificata": r.choice("SN"), "daGiustificare": True, "operazione": "I"})
        giorno += timedelta(days=1)
    registro.append({"pk": "eliminata", "operazione": "D"})
    return {
        "listaMaterie": [{"abbreviazione": a, "materia": m, "faMedia": True, "pk": a} for a, m in MATERIE],
        "listaDocentiClasse": docenti, "registro": registro, "promemoria": promemoria, "voti": voti, "appello": appello,
        "listaPeriodi": [{"descrizione": "PRIMO QUADRIMESTRE", "dataInizio": "01/09/2026", "dataFine": "31/01/2027"},
                         {"descrizione": "SCRUTINIO FINALE", "dataInizio": "01/02/2027", "dataFine": "31/08/2027"},
                         {"descrizione": "Intero Anno", "dataInizio": "2026-09-01", "dataFine": "2027-08-31"}],
        "mediaMaterie": {},
    }


def orario_simulato(lunedi, r):
    """Una settimana WebUntis grezza, con qualche variazione."""
    elementi = [{"type": 2, "id": i, "name": f"{c[:3]}_{n[0]}"} for i, (c, n, _) in enumerate(DOCENTI)]
    elementi += [{"type": 2, "id": 99, "name": "XYZ_Q"}]
    elementi += [{"type": 3, "id": 100 + i, "name": a, "longName": m} for i, (a, m) in enumerate(MATERIE)]
    elementi += [{"type": 3, "id": 199, "name": "REL", "longName": "RELIGIONE"}, {"type": 4, "id": 200, "name": "1B05", "longName": "1B05"}, {"type": 4, "id": 201, "name": "LAB", "longName": None}]
    lezioni, n = [], 0
    for g in range(5):
        giorno = int((lunedi + timedelta(days=g)).strftime("%Y%m%d"))
        for ora in range(8, 14):
            stato = r.choice(["STANDARD"] * 12 + ["SUBSTITUTION", "CANCEL", "ROOMSUBSTITUTION", "SHIFT", "ADDITIONAL", "FREE", "EXAM", "STANDBY", "STATO_NUOVO"])
            docente = r.randrange(len(DOCENTI))
            parti = [{"type": 2, "id": 99 if stato == "SUBSTITUTION" else docente, "orgId": docente if stato == "SUBSTITUTION" else 0},
                     {"type": 3, "id": r.choice([100 + r.randrange(len(MATERIE)), 199]), "orgId": 0},
                     {"type": 4, "id": r.choice([200, 201]), "orgId": 200 if stato == "ROOMSUBSTITUTION" else 0}, {"type": 1, "id": 1, "orgId": 0}]
            lezioni.append({"id": n, "date": giorno, "startTime": ora * 100, "endTime": ora * 100 + 100, "cellState": stato,
                            "elements": parti if r.random() > 0.03 else [], "substText": r.choice([None, "", "Comp."]), "periodText": None})
            n += 1
    return {"lezioni": lezioni, "elementi": elementi}


def controlla_pagina(test, pagina):
    """Proprietà che devono valere sempre, qualunque sia il giorno."""
    json.dumps(pagina)
    for s in pagina["statistiche"]:
        test.assertTrue(1 <= s["minimo"] <= s["media"] <= s["massimo"] <= 10, s)
        test.assertAlmostEqual(s["media"], s["somma"] / s["numero"])
    if pagina["statistiche"]:
        test.assertTrue(1 <= pagina["media_generale"] <= 10)
    test.assertEqual(sum(d["numero"] for d in pagina["distribuzione"]), len(pagina["voti"]))
    a = pagina["assenze"]
    test.assertTrue(0 <= a["ore_perse"] <= a["ore_svolte"])
    test.assertEqual(a["ore_perse"], sum(e["ore"] or 0 for e in a["eventi"]))
    test.assertEqual(a["ore_perse"], sum(m["ore"] for m in a["per_materia"]))
    test.assertEqual(len(a["eventi"]), a["giorni_assenza"] + a["ritardi"] + a["uscite"])
    c = pagina["carico"]
    test.assertEqual(sum(s["compiti"] for s in c["per_settimana"]), c["totale_compiti"])
    test.assertEqual(sum(s["verifiche"] for s in c["per_settimana"]), c["totale_verifiche"])
    test.assertEqual(sum(m["compiti"] for m in c["per_materia"]), c["totale_compiti"])
    test.assertEqual(len(c["prossimi_giorni"]), 14)
    test.assertEqual(len({x["id"] for x in pagina["compiti"]}), len(pagina["compiti"]))


class LungoPeriodo(unittest.TestCase):
    def setUp(self):
        cartella = Path(self.enterContext(tempfile.TemporaryDirectory()))
        for nome, file in (("CACHE", "dashboard.json"), ("CACHE_ORARIO", "orario.json"), ("STATO", "stato.json")):
            self.enterContext(mock.patch.object(dati, nome, cartella / file))
        self.enterContext(mock.patch.object(dati, "PROFILO", PROFILO_PROVA))
        self.enterContext(mock.patch.object(profili, "CARTELLA", cartella / "profili"))
        self.enterContext(mock.patch.object(profili, "_portachiavi", lambda: None))  # niente credenziali vere di Windows

    def test_ogni_giorno_dell_anno(self):
        """La pagina si costruisce senza errori in ogni giorno, dall'estate prima all'estate dopo."""
        dashboard = anno_simulato()
        self.assertGreater(len(dashboard["voti"]), 60)
        self.assertGreater(len(dashboard["appello"]), 5)
        giorno = date(2026, 8, 20)
        while giorno <= date(2027, 9, 5):
            # Ogni giorno il registro contiene solo ciò che è successo fino a quel momento.
            parziale = {**dashboard,
                        "registro": [x for x in dashboard["registro"] if x.get("datGiorno", "") <= giorno.isoformat()],
                        "voti": [x for x in dashboard["voti"] if x["datGiorno"] <= giorno.isoformat()],
                        "appello": [x for x in dashboard["appello"] if x["data"] <= giorno.isoformat()]}
            controlla_pagina(self, dati.elabora({"dashboard": parziale, "profilo": {}}, giorno))
            giorno += timedelta(days=1)

    def test_fine_anno_completa(self):
        pagina = dati.elabora({"dashboard": anno_simulato(), "profilo": {}}, date(2027, 7, 15))
        self.assertEqual(len(pagina["statistiche"]), len(MATERIE))
        self.assertEqual(len(pagina["voti_per_periodo"]), 2)
        self.assertGreater(pagina["assenze"]["ore_perse"], 0)
        self.assertEqual(pagina["promemoria"], [])
        self.assertGreater(len(pagina["carico"]["per_settimana"]), 35)

    def test_registro_vuoto(self):
        """Inizio anno o account nuovo: nessun dato, nessun errore."""
        for dashboard in ({}, {"voti": None, "registro": None, "promemoria": None, "appello": None, "listaMaterie": None, "listaPeriodi": None}):
            pagina = dati.elabora({"dashboard": dashboard}, date(2026, 9, 1))
            controlla_pagina(self, pagina)
            self.assertIsNone(pagina["media_generale"])
            self.assertEqual(pagina["consigli"], [])

    def test_dati_sporchi(self):
        """Campi mancanti, nulli o di tipo inatteso in voci a caso non devono far cadere nulla."""
        base = anno_simulato(seme=2)
        r = random.Random(7)
        sporco = [None, "", 0, "abc", [], {}, -5, 99999, "31/02/2027", "2027-13-45", 7.5, True]
        for giro in range(60):
            dashboard = copy.deepcopy(base)
            for chiave in ("registro", "promemoria", "voti", "appello", "listaMaterie", "listaDocentiClasse", "listaPeriodi"):
                for voce in r.sample(dashboard[chiave], min(len(dashboard[chiave]), 25)):
                    for campo in r.sample(sorted(voce), r.randint(1, min(3, len(voce)))):
                        if r.random() < 0.4:
                            del voce[campo]
                        else:
                            voce[campo] = r.choice(sporco)
            try:
                pagina = dati.elabora({"dashboard": dashboard, "profilo": {}}, date(2027, 2, 1) + timedelta(days=giro))
                json.dumps(pagina)
            except Exception as errore:
                self.fail(f"giro {giro}: {type(errore).__name__}: {errore}")

    def test_orario_e_pdf(self):
        """Orario con ogni tipo di variazione, settimane vuote (vacanze) e PDF per ogni settimana."""
        r = random.Random(3)
        dashboard = anno_simulato()
        noti = orario.docenti_noti(dashboard)
        for giro in range(25):
            lunedi = date(2026, 9, 14) + timedelta(days=7 * giro)
            settimane = [orario_simulato(lunedi, r), orario_simulato(lunedi + timedelta(days=7), r)]
            if giro % 6 == 5:
                settimane[1]["lezioni"] = []  # settimana di vacanza
            lezioni = orario.converti(settimane, noti)
            self.assertTrue(all("Religione" not in l.materia for l in lezioni))
            self.assertEqual(len({l.chiave for l in lezioni}), len(lezioni))
            dati.CACHE_ORARIO.write_text(json.dumps({"scaricato": "2026-10-08T10:00:00", "settimane": settimane, "viste": {}}), encoding="utf-8")
            pagina = {**dati.elabora({"dashboard": dashboard, "profilo": {}}, lunedi + timedelta(days=giro % 7)), "stato": {"fatti": {}}}
            json.dumps(pagina)
            for indice in range(len(pagina["orario"]["settimane"])):
                self.assertTrue(pdf_settimana.genera(pagina, indice).startswith(b"%PDF"))

    def test_orario_assente_o_vuoto(self):
        dashboard = anno_simulato()
        self.assertIsNone(dati.elabora({"dashboard": dashboard}, date(2026, 10, 8))["orario"])
        dati.CACHE_ORARIO.write_text(json.dumps({"scaricato": "2026-12-28T10:00:00", "settimane": [{"lezioni": [], "elementi": []}] * 2, "viste": {}}), encoding="utf-8")
        pagina = dati.elabora({"dashboard": dashboard}, date(2026, 12, 28))
        self.assertEqual(pagina["orario"]["settimane"], [])
        with self.assertRaises(ValueError):
            pdf_settimana.genera(pagina)
        dati.CACHE_ORARIO.write_text("{ file troncato", encoding="utf-8")
        self.assertIsNone(dati.elabora({"dashboard": dashboard}, date(2026, 10, 8))["orario"])

    def test_variazioni_nuove(self):
        """Una variazione è «nuova» solo all'aggiornamento in cui compare la prima volta."""
        lunedi = date(2026, 10, 5)
        lezione = lambda stato: {"id": 1, "date": 20261008, "startTime": 800, "endTime": 900, "cellState": stato,
                                 "elements": [{"type": 3, "id": 100, "orgId": 0}]}
        elementi = [{"type": 3, "id": 100, "name": "MAT", "longName": "MATEMATICA"}]
        nuove = lambda: [l["nuova"] for l in dati.elabora({"dashboard": {}}, lunedi)["orario"]["lezioni"]]
        from datetime import datetime
        prove = (("CANCEL", [False]), ("CANCEL", [False]), ("STANDARD", [False]), ("SUBSTITUTION", [True]), ("SUBSTITUTION", [False]))
        for minuto, (stato, atteso) in enumerate(prove):
            with mock.patch.object(dati.untis_client, "scarica", return_value=[{"lezioni": [lezione(stato)], "elementi": elementi}]), \
                 mock.patch.object(dati, "datetime", wraps=datetime) as orologio:
                orologio.now.return_value = datetime(2026, 10, 5, 8, minuto)
                dati.scarica_orario(lunedi)
            self.assertEqual(nuove(), atteso, f"aggiornamento {minuto}: {stato}")

    def test_spunte_concorrenti_e_file_rovinati(self):
        """Molte spunte in contemporanea non si perdono; un file di stato rovinato non blocca l'app."""
        fili = [threading.Thread(target=dati.segna_compito, args=(f"id{i}", True)) for i in range(40)]
        [f.start() for f in fili]
        [f.join() for f in fili]
        self.assertEqual(len(dati.leggi_stato()["fatti"]), 40)
        dati.segna_compito("id0", False)
        self.assertEqual(len(dati.leggi_stato()["fatti"]), 39)
        for rovinato in ("", "{", "[]", '{"fatti": null}', '"testo"'):
            dati.STATO.write_text(rovinato, encoding="utf-8")
            self.assertEqual(dati.leggi_stato(), {"fatti": {}})
            dati.segna_compito("x", True)
            self.assertEqual(dati.leggi_stato()["fatti"].keys(), {"x"})
        dati.CACHE.write_text("{ file troncato", encoding="utf-8")
        self.assertIsNone(dati.carica())

    def test_voto_necessario_sempre_coerente(self):
        """Prendendo il voto indicato la media raggiunge l'obiettivo; con un quarto di voto in meno no."""
        r = random.Random(5)
        for _ in range(2000):
            valori = [r.choice([2, 3, 4, 4.5, 5, 5.5, 6, 6.5, 7, 7.5, 8, 9, 10]) for _ in range(r.randint(0, 25))]
            obiettivo = r.choice([6, 7, 8])
            serve = stats.voto_necessario(valori, obiettivo)
            media = lambda extra: (sum(valori) + extra) / (len(valori) + 1)
            self.assertGreaterEqual(media(serve) + 1e-9, obiettivo)
            self.assertLess(media(serve - 0.25), obiettivo)


class ServerLocale(unittest.TestCase):
    """Il server vero, su una porta di prova, con dati finti e senza toccare Argo o WebUntis."""

    def setUp(self):
        import http.client
        import server

        self.server, self.http = server, http.client
        cartella = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(mock.patch.object(profili, "CARTELLA", cartella / "profili"))
        # Il server sceglie il profilo dal cookie: il profilo di prova esiste davvero e i file sono i suoi.
        dati._scrivi(profili.CARTELLA / "profili.json", {"profili": [PROFILO_PROVA], "ultimo": None})
        dati.attiva(PROFILO_PROVA, ricorda=False)
        self.addCleanup(dati.attiva, None)
        self.enterContext(mock.patch.object(profili, "_portachiavi", lambda: None))  # niente credenziali vere di Windows
        self.enterContext(mock.patch.object(server, "REGISTRO_ERRORI", cartella / "errori.log"))
        self.errori = cartella / "errori.log"
        dati._scrivi(dati.CACHE, {"dashboard": anno_simulato(), "profilo": {}, "scaricato": "2027-01-10T08:00:00"})
        self.app = server.avvia(porta=0)  # una porta libera qualsiasi
        self.PORTA = self.app.server_address[1]
        self.enterContext(mock.patch.object(server.config, "PORTA", self.PORTA))
        self.enterContext(mock.patch.object(server.config, "GETTONE", ""))
        threading.Thread(target=self.app.serve_forever, daemon=True).start()
        self.addCleanup(self.app.server_close)
        self.addCleanup(self.app.shutdown)

    def chiama(self, metodo, percorso, corpo=None, intestazioni=None, host=None):
        connessione = self.http.HTTPConnection("127.0.0.1", self.PORTA, timeout=20)
        tutte = {"Host": host or f"127.0.0.1:{self.PORTA}", "Cookie": f"profilo={PROFILO_PROVA['id']}", **(intestazioni or {})}
        if isinstance(corpo, (dict, list)):
            corpo = json.dumps(corpo)
        connessione.request(metodo, percorso, body=corpo, headers=tutte)
        risposta = connessione.getresponse()
        contenuto = risposta.read()
        connessione.close()
        return risposta.status, contenuto

    def invia(self, percorso, corpo):
        return self.chiama("POST", percorso, corpo, {"X-Parser-Compiti": "1", "Content-Type": "application/json"})

    def test_pagina_e_dati(self):
        for percorso in ("/", "/app.js", "/style.css"):
            self.assertEqual(self.chiama("GET", percorso)[0], 200, percorso)
        stato, corpo = self.chiama("GET", "/api/dati")
        self.assertEqual(stato, 200)
        self.assertGreater(len(json.loads(corpo)["voti"]), 20)

    def test_accessi_non_consentiti(self):
        """Un altro sito o un altro computer non devono poter usare l'app."""
        self.assertEqual(self.chiama("GET", "/api/dati", host="sito-malevolo.example")[0], 403)
        self.assertEqual(self.chiama("POST", "/api/stato", {"id": "x", "fatto": True}, {"Content-Type": "application/json"})[0], 403)
        self.assertEqual(self.chiama("POST", "/api/aggiorna", {}, {"X-Parser-Compiti": "1"}, host="altro:80")[0], 403)
        self.assertEqual(self.app.server_address[0], "127.0.0.1")
        for percorso in ("/../.env", "/..%2f.env", "/../dati.py", "/%2e%2e/config.py", "/non-esiste.js"):
            stato, corpo = self.chiama("GET", percorso)
            self.assertEqual(stato, 404, percorso)
            self.assertNotIn(b"ARGO_", corpo)
        self.assertEqual(dati.leggi_stato(), {"fatti": {}})

    def test_richieste_sbagliate(self):
        for corpo in ("{ non json", "[1, 2]", '"testo"', "null", json.dumps({"id": 5}), json.dumps({"id": ""}), json.dumps({"id": "x" * 500}), "x" * 50_000):
            self.assertEqual(self.invia("/api/stato", corpo)[0], 400, corpo[:30])
        self.assertEqual(self.invia("/api/altro", {})[0], 404)
        self.assertEqual(self.chiama("GET", "/api/pdf?settimana=abc")[0], 404)  # nessun orario scaricato
        self.assertEqual(dati.leggi_stato(), {"fatti": {}})

    def test_spunte_dal_browser(self):
        self.assertEqual(self.invia("/api/stato", {"id": "abc", "fatto": True})[0], 200)
        self.assertIn("abc", json.loads(self.chiama("GET", "/api/dati")[1])["stato"]["fatti"])
        self.assertEqual(json.loads(self.invia("/api/stato", {"id": "abc", "fatto": False})[1]), {"fatti": {}})

    def test_argo_e_untis_non_raggiungibili(self):
        """Senza rete l'app resta in piedi e continua a mostrare gli ultimi dati salvati."""
        import requests

        from argo_client import ArgoError
        from untis_client import UntisError

        prima = dati.CACHE.read_bytes()
        casi = [
            (requests.ConnectionError("rete assente"), requests.Timeout("lento"), 502, "Impossibile raggiungere il registro"),
            (ArgoError("Login rifiutato"), UntisError("classe non trovata"), 502, "Login rifiutato"),
            (ArgoError("x"), RuntimeError("imprevisto"), 502, "x"),
        ]
        for errore_argo, errore_untis, atteso, messaggio in casi:
            with mock.patch.object(dati, "scarica", side_effect=errore_argo), mock.patch.object(dati, "scarica_orario", side_effect=errore_untis):
                stato, corpo = self.invia("/api/aggiorna", {})
            self.assertEqual(stato, atteso)
            self.assertIn(messaggio, json.loads(corpo)["errore"])
        self.assertEqual(dati.CACHE.read_bytes(), prima)
        self.assertEqual(self.chiama("GET", "/api/dati")[0], 200)
        # WebUntis giù ma Argo su: i dati del registro arrivano, con un avviso.
        with mock.patch.object(dati, "scarica"), mock.patch.object(dati, "scarica_orario", side_effect=requests.ConnectionError()):
            stato, corpo = self.invia("/api/aggiorna", {})
        self.assertEqual(stato, 200)
        self.assertIn("WebUntis non è raggiungibile", json.loads(corpo)["avviso"])

    def test_errore_imprevisto(self):
        """Un errore nel codice diventa una risposta leggibile e finisce nel file degli errori."""
        with mock.patch.object(dati, "elabora", side_effect=ZeroDivisionError("guasto")):
            stato, corpo = self.chiama("GET", "/api/dati")
        self.assertEqual(stato, 500)
        self.assertIn("ZeroDivisionError", json.loads(corpo)["errore"])
        self.assertIn("guasto", self.errori.read_text(encoding="utf-8"))
        self.assertEqual(self.chiama("GET", "/api/dati")[0], 200)

    def test_dati_mancanti_o_rovinati(self):
        dati.CACHE.write_text("{ troncato", encoding="utf-8")
        self.assertTrue(json.loads(self.chiama("GET", "/api/dati")[1])["vuoto"])
        dati.CACHE.unlink()
        self.assertTrue(json.loads(self.chiama("GET", "/api/dati")[1])["vuoto"])

    def test_uso_prolungato(self):
        """Centinaia di richieste, anche in parallelo: nessun errore e nessuna spunta persa."""
        esiti = []

        def utente(numero):
            for giro in range(15):
                esiti.append(self.invia("/api/stato", {"id": f"u{numero}-{giro}", "fatto": True})[0])
                esiti.append(self.chiama("GET", "/api/dati")[0])

        fili = [threading.Thread(target=utente, args=(n,)) for n in range(8)]
        [f.start() for f in fili]
        [f.join() for f in fili]
        self.assertEqual(set(esiti), {200})
        self.assertEqual(len(dati.leggi_stato()["fatti"]), 8 * 15)
        self.assertFalse(self.errori.exists())

    def test_pdf_dal_server(self):
        r = random.Random(1)
        dati._scrivi(dati.CACHE_ORARIO, {"scaricato": "2027-01-10T08:00:00", "viste": {},
                                         "settimane": [orario_simulato(date(2027, 1, 11), r), orario_simulato(date(2027, 1, 18), r)]})
        for indice in ("0", "1", "7", "abc"):
            stato, corpo = self.chiama("GET", f"/api/pdf?settimana={indice}")
            self.assertEqual((stato, corpo[:4]), (200, b"%PDF"), indice)


if __name__ == "__main__":
    unittest.main()
