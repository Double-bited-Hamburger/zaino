"""Prove dell'aspetto della pagina: icone che esistono davvero, la cartella web piatta e il carattere servito bene."""

import http.client
import re
import unittest
from pathlib import Path

from prove import aiuti as base

WEB = Path(__file__).resolve().parent.parent / "web"


class Sprite(unittest.TestCase):
    def setUp(self):
        self.pagina = (WEB / "index.html").read_text(encoding="utf-8")
        self.codice = (WEB / "app.js").read_text(encoding="utf-8")
        self.simboli = set(re.findall(r'<symbol id="([^"]+)"', self.pagina))

    def test_ogni_icona_usata_esiste(self):
        """Un'icona che manca nello sprite non dà errori: diventa solo uno spazio vuoto. Meglio accorgersene qui."""
        usate = set(re.findall(r'href="#(i-[a-z0-9-]+)"', self.pagina))
        nomi = set(re.findall(r'\bico\(\s*"([a-z0-9-]+)"', self.codice))  # ico("nome")
        nomi |= set(re.findall(r'icona: "([a-z0-9-]+)"', self.codice))  # i riquadri di Oggi
        nomi |= set(re.findall(r'tessera\([^\n]*?, "([a-z0-9-]+)"\)\}', self.codice))  # l'ultimo argomento delle tessere
        nomi |= set(re.findall(r'(?:critico|attenzione|info): "([a-z0-9-]+)"', self.codice))  # i consigli
        nomi |= set(re.findall(r'(?:su|giu|stabile): \["([a-z]+)"', self.codice))  # le frecce dei voti
        usate |= {f"i-{n}" for n in nomi}
        self.assertGreater(len(usate), 30)
        self.assertEqual(sorted(u for u in usate if u not in self.simboli), [])

    def test_icone_delle_materie(self):
        """Ogni icona delle materie (e quella di riserva) è nello sprite."""
        nomi = {n for _, n in re.findall(r'\[/(.*?)/, "([a-z-]+)"\]', self.codice)} | {"m-libro"}
        self.assertTrue(nomi)
        self.assertEqual(sorted(n for n in nomi if f"i-{n}" not in self.simboli), [])

    def test_pose_della_mascotte(self):
        pose = set(re.findall(r'\b(?:vuoto|vuotoBox|mascotte)\(\s*"([a-z]+)"', self.codice))
        self.assertTrue({"felice", "festa", "pensa", "saluta"} <= pose)
        self.assertEqual(sorted(p for p in pose if f"z-{p}" not in self.simboli), [])

    def test_cartella_web_piatta(self):
        """L'app Android copia solo i file in cima a web/ (App.kt): una sottocartella le impedirebbe di partire."""
        self.assertEqual([p.name for p in WEB.iterdir() if p.is_dir()], [])


class Carattere(base.ServerProfili):
    def grezza(self, percorso):
        connessione = http.client.HTTPConnection("127.0.0.1", self.PORTA, timeout=20)
        connessione.request("GET", percorso, headers={"Host": f"127.0.0.1:{self.PORTA}"})
        risposta = connessione.getresponse()
        corpo = risposta.read()
        connessione.close()
        return risposta.status, risposta.msg.get("Content-Type"), corpo

    def test_il_carattere_arriva_come_font(self):
        """Con «nosniff» il browser scarta un font col tipo sbagliato: deve essere font/woff2, senza charset."""
        stato, tipo, corpo = self.grezza("/nunito.woff2")
        self.assertEqual(stato, 200)
        self.assertEqual(tipo, "font/woff2")
        self.assertEqual(corpo[:4], b"wOF2")

    def test_testi_con_charset(self):
        for percorso, atteso in (("/", "text/html"), ("/app.js", "text/javascript"), ("/style.css", "text/css")):
            stato, tipo, _ = self.grezza(percorso)
            self.assertEqual(stato, 200, percorso)
            self.assertEqual(tipo, f"{atteso}; charset=utf-8", percorso)


if __name__ == "__main__":
    unittest.main()
