"""Prove del registro ClasseViva, con risposte finte costruite sui campi documentati dell'API."""

import json
import unittest
from datetime import date
from unittest import mock

import requests

import classeviva_adatta
import classeviva_client
import dati
from classeviva_client import ClassevivaClient, ClassevivaError

OGGI = date(2026, 10, 8)

GREZZO = {
    "card": {"ident": "S1234567X", "usrId": 1234567, "firstName": "MARIO", "lastName": "ROSSI", "schName": "ISTITUTO DI PROVA"},
    "materie": [
        {"id": 11, "description": "MATEMATICA", "teachers": [{"teacherId": "T1", "teacherName": "BIANCHI ANNA"}]},
        {"id": 12, "description": "STORIA", "teachers": [{"teacherId": "T2", "teacherName": "VERDI LUCA"}]},
        {"id": 13, "description": "FISICA", "teachers": [{"teacherId": "T1", "teacherName": "BIANCHI ANNA"}]},
    ],
    "periodi": [{"periodCode": "Q1", "periodDesc": "Trimestre", "dateStart": "2026-09-14", "dateEnd": "2026-12-22", "isFinal": False}],
    "voti": [
        {"subjectId": 11, "subjectDesc": "MATEMATICA", "evtDate": "2026-09-20", "decimalValue": 7.5, "displayValue": "7½", "color": "green",
         "canceled": False, "componentDesc": "Scritto/Grafico", "notesForFamily": "Equazioni"},
        {"subjectId": 11, "subjectDesc": "MATEMATICA", "evtDate": "2026-09-28", "decimalValue": None, "displayValue": "6+", "color": "green",
         "canceled": False, "componentDesc": "Orale", "notesForFamily": ""},
        {"subjectId": 12, "subjectDesc": "STORIA", "evtDate": "2026-09-25", "decimalValue": 4, "displayValue": "4", "color": "blue",
         "canceled": False, "componentDesc": "Orale", "notesForFamily": "Non fa media"},
        {"subjectId": 12, "subjectDesc": "STORIA", "evtDate": "2026-09-26", "decimalValue": 9, "displayValue": "9", "color": "green",
         "canceled": True, "componentDesc": "Orale"},
    ],
    "agenda": [
        {"evtId": 1, "evtCode": "AGHW", "evtDatetimeBegin": "2026-10-09T08:00:00+02:00", "evtDatetimeEnd": "2026-10-09T09:00:00+02:00",
         "isFullDay": False, "notes": "Es. 1-5 pag. 40", "authorName": "BIANCHI ANNA", "classDesc": "3A INFORMATICA", "subjectDesc": "MATEMATICA"},
        {"evtId": 2, "evtCode": "AGNT", "evtDatetimeBegin": "2026-10-12T09:00:00+02:00", "evtDatetimeEnd": "2026-10-12T11:00:00+02:00",
         "isFullDay": False, "notes": "Verifica di storia cap. 3", "authorName": "VERDI LUCA", "classDesc": "3A INFORMATICA", "subjectDesc": None},
        {"evtId": 3, "evtCode": "AGNT", "evtDatetimeBegin": "2026-10-20T00:00:00+02:00", "evtDatetimeEnd": "2026-10-20T23:59:59+02:00",
         "isFullDay": True, "notes": "Uscita didattica", "authorName": "BIANCHI ANNA", "classDesc": "3A INFORMATICA", "subjectDesc": ""},
        {"evtId": 4, "evtCode": "AGCR", "evtDatetimeBegin": "2026-10-13T10:00:00+02:00", "notes": "Laboratorio prenotato", "authorName": "X"},
        {"evtId": 5, "evtCode": "AGNT", "evtDatetimeBegin": "2026-10-14T10:00:00+02:00", "notes": "   ", "authorName": "X"},
    ],
    "assenze": [
        {"evtId": 1, "evtCode": "ABA0", "evtDate": "2026-10-06", "evtHPos": None, "isJustified": False, "justifReasonDesc": None},
        {"evtId": 2, "evtCode": "ABR0", "evtDate": "2026-10-07", "evtHPos": 2, "isJustified": True, "justifReasonDesc": "Motivi di salute"},
        {"evtId": 3, "evtCode": "ABU0", "evtDate": "2026-10-07", "evtHPos": 4, "isJustified": True},
        {"evtId": 4, "evtCode": "ABR1", "evtDate": "2026-10-05", "evtHPos": 1, "isJustified": True},
    ],
    "lezioni": [
        {"evtDate": "2026-10-06", "evtCode": "LSF0", "evtHPos": 1, "evtDuration": 2, "subjectDesc": "MATEMATICA", "authorName": "BIANCHI ANNA", "classDesc": "3A INFORMATICA"},
        {"evtDate": "2026-10-07", "evtCode": "LSC0", "evtHPos": 1, "evtDuration": 1, "subjectDesc": "SOSTEGNO", "authorName": "NERI EVA"},
        {"evtDate": "2026-10-07", "evtCode": "LSF0", "evtHPos": 1, "evtDuration": 1, "subjectDesc": "STORIA", "authorName": "VERDI LUCA"},
        {"evtDate": "2026-10-07", "evtCode": "LSF0", "evtHPos": 2, "evtDuration": 3, "subjectDesc": "FISICA", "authorName": "BIANCHI ANNA"},
        {"evtDate": "2026-10-07", "evtCode": "LSF0", "evtHPos": "x", "subjectDesc": "STORIA"},
    ],
    "avviso": None,
}

# Un compito della sezione «Compiti», come lo dà il sito (campi da open-viva/endpoints).
COMPITO_SITO = {
    "evtId": 125021, "evtCode": "NEWDC", "teacherId": 7654321, "teacherName": "VERDI LUCA", "homeworkDesc": "Leggere il cap. 4",
    "homeworkDone": False, "homeworkMarkedDone": False, "assignmentDate": "2026-10-06", "assignmentTime": None, "expiryDate": "2026-10-10",
    "expiryTime": None, "studentAttachmentsAllowed": False, "subjectId": 12, "subjectDesc": "STORIA", "lastStudentMsg": None,
    "lastTeacherMsg": None, "newMessages": False, "teacherFiles": [], "teacherLinks": [], "studentFiles": [], "correctedFiles": [],
}


class Adattatore(unittest.TestCase):
    def setUp(self):
        self.pagina = dati.elabora({"classeviva": json.loads(json.dumps(GREZZO)), "dashboard": {}, "profilo": {}}, OGGI)

    def test_studente_e_classe(self):
        self.assertEqual((self.pagina["studente"], self.pagina["classe"]), ("Rossi Mario", "3A"))
        self.assertEqual(self.pagina["scartate"], {})

    def test_voti_blu_e_annullati_fuori_media(self):
        self.assertEqual([(v["materia"], v["valore"], v["tipo"]) for v in self.pagina["voti"]], [("Matematica", 7.5, "Scritto"), ("Matematica", 6.25, "Orale")])
        self.assertEqual({v["codice"] for v in self.pagina["voti_fuori_media"]}, {"4", "9"})
        self.assertEqual(self.pagina["voti"][0]["descrizione"], "Equazioni")

    def test_compiti_e_verifiche_dall_agenda(self):
        self.assertEqual([(c["materia"], c["testo"], c["consegna"]) for c in self.pagina["compiti"]], [("Matematica", "Es. 1-5 pag. 40", "2026-10-09")])
        promemoria = {p["testo"]: p for p in self.pagina["promemoria"]}
        self.assertEqual(set(promemoria), {"Verifica di storia cap. 3", "Uscita didattica"})  # niente aule prenotate né note vuote
        verifica = promemoria["Verifica di storia cap. 3"]
        self.assertEqual((verifica["verifica"], verifica["orario"], verifica["materia"]), (True, "09:00–11:00", "Storia"))
        self.assertEqual((promemoria["Uscita didattica"]["verifica"], promemoria["Uscita didattica"]["orario"]), (False, ""))

    def test_assenze_e_ore_perse(self):
        assenze = self.pagina["assenze"]
        self.assertEqual((assenze["giorni_assenza"], assenze["ritardi"], assenze["uscite"], assenze["da_giustificare"]), (1, 2, 1, 1))
        per_tipo = {(e["data"], e["tipo"]): e for e in assenze["eventi"]}
        self.assertEqual(per_tipo[("2026-10-06", "assenza")]["ore"], 2)  # la lezione di due ore conta due ore
        self.assertEqual(per_tipo[("2026-10-07", "ritardo")]["ore"], 1)  # entrato alla 2ª: persa la 1ª
        self.assertEqual(per_tipo[("2026-10-07", "uscita")]["ore"], 1)  # uscito alla 4ª: persa la 4ª
        self.assertEqual(per_tipo[("2026-10-05", "ritardo")]["descrizione"], "Ritardo breve")

    def test_compresenza_non_sostituisce_la_lezione(self):
        _, dashboard = classeviva_adatta.converti(GREZZO, OGGI)
        ore = {(r["datGiorno"], r["ora"]): r["materia"] for r in reversed(dashboard["registro"]) if r.get("ora")}
        self.assertEqual(ore[("2026-10-07", 1)], "STORIA")
        self.assertNotIn("Sostegno", self.pagina["materie"])

    def test_compiti_della_sezione_compiti(self):
        # Lo stesso compito di matematica è anche in agenda, senza materia: resta una volta, quello del sito con materia e data di assegnazione.
        doppio = {**COMPITO_SITO, "homeworkDesc": "Es. 1-5  pag. 40", "expiryDate": "2026-10-09", "assignmentDate": "2026-10-02", "subjectDesc": "MATEMATICA"}
        grezzo = json.loads(json.dumps({**GREZZO, "compiti": [COMPITO_SITO, doppio, {"homeworkDesc": "Senza consegna"}, {"expiryDate": "2026-10-10"}, None]}))
        grezzo["agenda"][0]["subjectDesc"] = None
        pagina = dati.elabora({"classeviva": grezzo, "dashboard": {}, "profilo": {}}, OGGI)
        self.assertEqual([(c["materia"], c["testo"], c["consegna"], c["assegnato"], c["docente"]) for c in pagina["compiti"]], [
            ("Matematica", "Es. 1-5 pag. 40", "2026-10-09", "2026-10-02", "VERDI LUCA"),
            ("Storia", "Leggere il cap. 4", "2026-10-10", "2026-10-06", "VERDI LUCA"),
        ])

    def test_dati_malformati_non_bloccano(self):
        rotto = {"card": [], "materie": "x", "voti": [None, {"decimalValue": "dieci"}], "agenda": [{"evtCode": "AGHW"}], "assenze": [{}], "lezioni": [{}]}
        pagina = dati.elabora({"classeviva": rotto, "dashboard": {}, "profilo": {}}, OGGI)
        self.assertEqual(pagina["voti"], [])


class Risposta:
    def __init__(self, stato=200, corpo=None, cookies=None):
        self.status_code, self._corpo, self.cookies = stato, corpo, cookies or {}

    def json(self):
        if self._corpo is None:
            raise ValueError
        return self._corpo


class SessioneFinta:
    """Al posto di requests.Session: risponde secondo il percorso e ricorda cosa le è stato chiesto.

    Le chiamate all'API del sito hanno il percorso che comincia con «sito:»; il suo login risponde con risposte["accesso al sito"].
    """

    def __init__(self, risposte, chiamate):
        self.risposte, self.headers, self.cookies, self.chiamate = risposte, {}, requests.cookies.RequestsCookieJar(), chiamate

    def post(self, url, json=None, data=None, params=None, **kwargs):
        if "/AuthApi4.php" in url:
            self.chiamate.append(("POST", f"{url}?a={params['a']}", data, dict(self.headers)))
            return self.risposte.get("accesso al sito", lambda azione, campi: Risposta(404))(params["a"], data)
        self.chiamate.append(("POST", url, json, dict(self.headers)))
        return self.risposte["login"](json)

    def get(self, url, **kwargs):
        self.chiamate.append(("GET", url, None, dict(self.headers)))
        sito = "/rest/w1/" in url
        percorso = ("sito:" if sito else "") + url.split("/rest/w1/" if sito else "/rest/v1/")[1].removeprefix("students/1234567/")
        for prefisso, risposta in self.risposte.items():
            if percorso.startswith(prefisso):
                return risposta
        return Risposta(404)


def login_giusto(corpo):
    if corpo.get("pass") != "segreta":
        return Risposta(422, {"error": "auth/authentication failed", "info": "credenziali errate"})
    return Risposta(200, {"ident": "S1234567X", "firstName": "MARIO", "lastName": "ROSSI", "token": "tok", "expire": "2026-10-08T12:00:00+02:00"})


def accesso_al_sito(azione, campi):
    entrato = azione == "aLoginSam" or campi.get("pwd") == "segreta"
    return Risposta(200, {"data": {"auth": {"verified": entrato, "loggedIn": entrato, "accountInfo": {"type": "S", "id": 1234567}}}, "error": []})


SITO = {
    "accesso al sito": accesso_al_sito,
    "sito:misc/whoami": Risposta(200, {"id": "1234567", "account_type": "S"}),
    "sito:homeworks/index": Risposta(200, {"items": [COMPITO_SITO]}),
}


class Client(unittest.TestCase):
    def client(self, risposte, password="segreta", scelta=""):
        """Il client con sessioni finte (quella dell'app e quella del sito), che restano finte per tutta la prova."""
        chiamate, sessioni = [], []

        def nuova_sessione():
            sessioni.append(SessioneFinta(risposte, chiamate))
            return sessioni[-1]

        self.enterContext(mock.patch.object(classeviva_client.requests, "Session", nuova_sessione))
        return ClassevivaClient("S1234567X", password, scelta), sessioni[0]

    def test_login_e_intestazioni(self):
        client, sessione = self.client({"login": login_giusto})
        client.login()
        metodo, url, corpo, intestazioni = sessione.chiamate[0]
        self.assertEqual((metodo, url, corpo), ("POST", "https://web.spaggiari.eu/rest/v1/auth/login", {"uid": "S1234567X", "pass": "segreta"}))
        self.assertEqual(intestazioni["Z-Dev-Apikey"], "Tg1NWEwNGIgIC0K")
        self.assertTrue(intestazioni["User-Agent"].startswith("CVVS/"))
        self.assertEqual((client.studente, sessione.headers["Z-Auth-Token"]), ("1234567", "tok"))

    def test_password_sbagliata(self):
        client, _ = self.client({"login": login_giusto}, password="no")
        with self.assertRaisesRegex(ClassevivaError, "Login rifiutato"):
            client.login()

    @staticmethod
    def login_con_scelte(*scelte):
        def login(corpo):
            if "ident" not in corpo:
                return Risposta(200, {"choices": list(scelte)})
            return login_giusto({**corpo, "pass": "segreta"})
        return login

    GENITORE = {"ident": "G7654321Y", "name": "Genitore"}
    MARIO, LUCIA = {"ident": "S1234567X", "name": "MARIO ROSSI"}, {"ident": "S1111111X", "name": "LUCIA ROSSI"}

    def test_account_con_piu_studenti(self):
        client, sessione = self.client({"login": self.login_con_scelte(self.GENITORE, self.MARIO, self.LUCIA)})
        client.login()
        self.assertEqual(sessione.chiamate[1][2]["ident"], "S1234567X")  # il primo studente, non il genitore
        self.assertIn("MARIO ROSSI", client.avviso)
        self.assertIn("modificando il profilo", client.avviso)
        self.assertEqual(client.scelte, [self.MARIO, self.LUCIA])  # il genitore non si può scegliere: non ha voti

    def test_studente_scelto_nel_profilo(self):
        client, sessione = self.client({"login": self.login_con_scelte(self.GENITORE, self.MARIO, self.LUCIA)}, scelta="S1111111X")
        client.login()
        self.assertEqual(sessione.chiamate[1][2]["ident"], "S1111111X")
        self.assertIsNone(client.avviso)
        self.assertEqual(len(client.scelte), 2)

    def test_studente_scelto_non_piu_collegato(self):
        client, sessione = self.client({"login": self.login_con_scelte(self.MARIO, self.LUCIA)}, scelta="S9999999X")
        client.login()
        self.assertEqual(sessione.chiamate[1][2]["ident"], "S1234567X")
        self.assertIn("non è più collegato", client.avviso)

    def test_genitore_con_un_solo_studente(self):
        client, sessione = self.client({"login": self.login_con_scelte(self.GENITORE, self.MARIO)})
        client.login()
        self.assertEqual(sessione.chiamate[1][2]["ident"], "S1234567X")
        self.assertEqual((client.scelte, client.avviso), ([], None))  # niente da scegliere

    def test_studente_scelto_ignorato_se_l_account_e_di_uno_studente(self):
        client, sessione = self.client({"login": login_giusto}, scelta="S1111111X")
        client.login()
        self.assertEqual((len(sessione.chiamate), client.studente, client.scelte, client.avviso), (1, "1234567", [], None))

    def test_scarica(self):
        risposte = {
            "login": login_giusto,
            "card": Risposta(200, {"card": GREZZO["card"]}),
            "subjects": Risposta(200, {"subjects": GREZZO["materie"]}),
            "periods": Risposta(403),  # sezione disattivata dalla scuola
            "grades2": Risposta(404),
            "grades": Risposta(200, {"grades": GREZZO["voti"]}),
            "agenda/all/20260908/20261207": Risposta(200, {"agenda": GREZZO["agenda"]}),
            "absences/details": Risposta(200, {"events": GREZZO["assenze"]}),
            "lessons/20260901/20261008": Risposta(200, {"lessons": GREZZO["lezioni"]}),
            **SITO,
        }
        client, _ = self.client(risposte)
        client.login()
        grezzo = client.scarica(OGGI)
        self.assertEqual((len(grezzo["voti"]), len(grezzo["agenda"]), len(grezzo["lezioni"]), grezzo["periodi"]), (4, 5, 5, []))
        self.assertEqual(grezzo["card"]["lastName"], "ROSSI")
        self.assertEqual((grezzo["compiti"], grezzo["avviso"]), ([COMPITO_SITO], None))

    def test_compiti_dal_sito(self):
        client, sessione = self.client({"login": login_giusto, **SITO})
        client.login()
        self.assertEqual(client.compiti(), [COMPITO_SITO])
        metodo, url, campi, intestazioni = next(c for c in sessione.chiamate if "AuthApi4.php" in c[1])
        self.assertEqual((metodo, url), ("POST", "https://web.spaggiari.eu/auth-p7/app/default/AuthApi4.php?a=aLoginPwd"))
        self.assertEqual(campi, {"cid": "", "uid": "S1234567X", "pwd": "segreta", "pin": "", "target": ""})
        self.assertEqual((intestazioni["Origin"], intestazioni["X-Requested-With"]), ("https://web.spaggiari.eu", "XMLHttpRequest"))
        self.assertNotIn("Z-Dev-Apikey", intestazioni)  # il sito non è l'app: niente chiave né token dell'app
        self.assertIn(("GET", "https://web.spaggiari.eu/rest/w1/students/1234567/homeworks/index"), [c[:2] for c in sessione.chiamate])

    def test_compiti_dal_sito_con_piu_account(self):
        def accesso(azione, campi):
            if azione == "aLoginPwd":  # credenziali giuste, ma valgono per più account: bisogna sceglierne uno
                return Risposta(200, {"data": {"auth": {"verified": True, "loggedIn": False}}})
            return accesso_al_sito(azione, campi)

        client, sessione = self.client({"login": self.login_con_scelte(self.GENITORE, self.MARIO, self.LUCIA), **SITO, "accesso al sito": accesso})
        client.login()
        self.assertEqual(client.compiti(), [COMPITO_SITO])
        scelta = [c for c in sessione.chiamate if c[1].endswith("?a=aLoginSam")]
        self.assertEqual([c[2] for c in scelta], [{"uid": "S1234567X"}])  # lo stesso studente dell'app

    def test_sito_che_non_risponde_non_blocca_il_resto(self):
        def firewall(azione, campi):
            return Risposta(403)  # pagina HTML del firewall, non JSON

        def irraggiungibile(azione, campi):
            raise requests.ConnectionError("rete giù")

        for accesso, motivo in ((firewall, "risposta 403"), (irraggiungibile, "non è raggiungibile")):
            client, _ = self.client({"login": login_giusto, "card": Risposta(200, {"card": GREZZO["card"]}), **SITO, "accesso al sito": accesso})
            client.login()
            grezzo = client.scarica(OGGI)
            self.assertIsNone(grezzo["compiti"])
            self.assertEqual(grezzo["card"]["lastName"], "ROSSI")
            self.assertIn("non aggiornati", grezzo["avviso"])
            self.assertIn(motivo, grezzo["avviso"])

    def test_sessione_nuova_dal_login_del_sito(self):
        # Il sito dà un PHPSESSID nuovo all'accesso: le chiamate dopo portano solo quello, altrimenti l'API risponde 401.
        def accesso(azione, campi):
            risposta = accesso_al_sito(azione, campi)
            risposta.cookies = {"PHPSESSID": "nuova", "webidentity": "S1234567X", "altro": "x"}
            return risposta

        client, sessione = self.client({"login": login_giusto, **SITO, "accesso al sito": accesso})
        client.login()
        self.assertEqual(client.compiti(), [COMPITO_SITO])
        accesso_fatto = next(c for c in sessione.chiamate if "AuthApi4.php" in c[1])
        self.assertIn("webrole=gen; PHPSESSID=", accesso_fatto[3]["Cookie"])
        for _, url, _, intestazioni in sessione.chiamate:
            if "/rest/w1/" in url:
                self.assertEqual(intestazioni["Cookie"], "webrole=gen; PHPSESSID=nuova; webidentity=S1234567X")

    def test_sessione_rifiutata_dal_sito(self):
        client, _ = self.client({"login": login_giusto, **SITO, "sito:misc/whoami": Risposta(401)})
        client.login()
        with self.assertRaisesRegex(ClassevivaError, "401"):
            client.compiti()

    def test_password_sbagliata_sul_sito(self):
        client, _ = self.client({"login": login_giusto, **SITO})
        client.login()
        client.password = "cambiata"
        with self.assertRaisesRegex(ClassevivaError, "non ha accettato"):
            client.compiti()

    def test_sessione_scaduta_e_troppe_richieste(self):
        for stato, messaggio in ((401, "scaduta"), (429, "troppe richieste")):
            client, _ = self.client({"login": login_giusto, "card": Risposta(stato)})
            client.login()
            with self.assertRaisesRegex(ClassevivaError, messaggio):
                client.scarica(OGGI)

    def test_inizio_anno(self):
        self.assertEqual(classeviva_client.inizio_anno(date(2027, 3, 1)), date(2026, 9, 1))
        self.assertEqual(classeviva_client.inizio_anno(date(2026, 9, 1)), date(2026, 9, 1))


if __name__ == "__main__":
    unittest.main()
