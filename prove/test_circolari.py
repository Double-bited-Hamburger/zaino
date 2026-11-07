"""Le circolari della scuola da trasparenza-pa.net: lettura della pagina, cartella dell'anno, profilo, «Aggiorna».

prove/dati/circolari.html è l'inizio di una pagina vera dell'elenco (pubblica), tagliata dopo le prime 4 circolari.
"""

import unittest
from pathlib import Path
from unittest import mock

import circolari
import dati
import profili
from prove import aiuti
from prove.aiuti import ARGO, NUVOLA, Base, Risposta

PAGINA = (Path(__file__).parent / "dati" / "circolari.html").read_text(encoding="utf-8")
CARTELLE = """<ol class="breadcrumb"></ol>
<a href="/?codcli=SC1&amp;node=1">Disposizioni Generali</a>
<a href="/?codcli=SC1&amp;node=700">Circolari_2025-26</a>
<a href="/?codcli=SC1&amp;node=900">Circolari_2026-27</a>
<a href="/?codcli=SC1&amp;node=50">Circolari 2024/25</a>
<a href="/?codcli=SC1&amp;node=60">Regolamento viaggi</a>"""


def circolare(id_, data, titolo="Circ_1 Prova"):
    return {"id": id_, "numero": id_, "titolo": titolo, "descrizione": "", "data": data, "allegati": [], "link": "x", "classi": [], "etichette": []}


class Lettura(unittest.TestCase):
    def test_pagina_vera(self):
        lette = circolari.leggi_circolari(PAGINA, "SG28889")
        circolari.controlla_lettura(PAGINA, lette)
        self.assertEqual([c["numero"] for c in lette], [101, 100, 99, 98])
        uscita = lette[2]
        self.assertEqual(uscita["titolo"], "Uscita presso Fondazione Dalmine classe 5Aa")
        self.assertEqual((uscita["data"], uscita["classi"], uscita["etichette"]), ("2026-10-07T14:16", ["5Aa"], ["uscite"]))
        self.assertEqual(uscita["link"], f"https://trasparenza-pa.net/?codcli=SG28889&opc={uscita['id']}")
        self.assertTrue(all(a["url"].startswith("https://trasparenza-pa.net/action/download.php?file_id=") for c in lette for a in c["allegati"]))
        self.assertIn("convocazioni", lette[0]["etichette"])

    def test_sito_cambiato_o_in_manutenzione(self):
        with self.assertRaises(circolari.ErroreCircolari) as errore:
            circolari.controlla_lettura("<html>Manutenzione</html>", [])
        self.assertTrue(errore.exception.temporaneo)
        lette = circolari.leggi_circolari(PAGINA, "SG28889")
        with self.assertRaisesRegex(circolari.ErroreCircolari, "lette 3 circolari su 4"):
            circolari.controlla_lettura(PAGINA, lette[:3])

    def test_cartella_dell_anno_piu_recente(self):
        self.assertEqual(circolari.cartella_piu_recente(CARTELLE), "900")
        self.assertIsNone(circolari.cartella_piu_recente("<a href='/?node=1'>Altro</a>"))

    def test_etichette_e_classi(self):
        self.assertEqual(circolari.etichette("Sciopero del personale ATA e MATURITÀ"), ["personale", "sciopero", "esami"])
        self.assertEqual(circolari.classi_citate("Uscita 5AA e 3B, non 2026 né A3"), ["5Aa", "3B"])

    def test_indirizzo_incollato(self):
        self.assertEqual(circolari.da_indirizzo(" https://trasparenza-pa.net/?codcli=sg28889&node=5942145 "), ("SG28889", "5942145"))
        self.assertEqual(circolari.da_indirizzo("https://www.trasparenza-pa.net/?codcli=SC1"), ("SC1", ""))
        for sbagliato in ("https://example.com/?codcli=SC1", "trasparenza-pa.net/?codcli=SC1", "https://trasparenza-pa.net/?node=3",
                          "https://trasparenza-pa.net/?codcli=SC1&node=abc", "javascript:alert(1)"):
            self.assertIsNone(circolari.da_indirizzo(sbagliato), sbagliato)

    def test_scarica_trova_la_cartella_e_legge_due_pagine(self):
        chiamate = []

        def get(url, params=None, **k):
            chiamate.append(params)
            if params["node"] == circolari.CARTELLA_PADRE:
                return Risposta(url, testo=CARTELLE)
            return Risposta(url, testo=PAGINA)  # due volte la stessa pagina: le doppie si scartano

        with mock.patch.object(circolari.requests, "get", get):
            node, lette = circolari.scarica("SC1")
        self.assertEqual((node, len(lette)), ("900", 4))
        self.assertEqual([c["node"] for c in chiamate], ["3", "900", "900"])
        self.assertEqual(chiamate[2]["contentsPage"], 2)

        with mock.patch.object(circolari.requests, "get", return_value=Risposta(testo="<ol class='breadcrumb'></ol>")):
            with self.assertRaisesRegex(circolari.ErroreCircolari, "incolla nel profilo"):
                circolari.scarica("SC1")
        with mock.patch.object(circolari.requests, "get", return_value=Risposta(stato=503)):
            with self.assertRaises(circolari.ErroreCircolari) as errore:
                circolari.scarica("SC1", "900")
            self.assertTrue(errore.exception.temporaneo)


class NelProfilo(Base):
    def test_argo_le_trova_dal_codice_scuola(self):
        p = profili.salva({**ARGO, "scuola": "sc 12345"})
        dati.attiva(p)
        self.circolari.return_value = ("900", [circolare(2, "2026-11-02"), circolare(1, "2026-11-01")])
        dati.scarica_circolari()
        self.circolari.assert_called_once_with("SC12345", "")
        # Al giro dopo si aggiungono le nuove e restano le vecchie che il sito non mostra più in prima pagina.
        self.circolari.return_value = ("900", [circolare(3, "2026-11-05")])
        salvate = dati.scarica_circolari()
        self.assertEqual([c["id"] for c in salvate["circolari"]], [3, 2, 1])
        self.assertEqual([c["id"] for c in dati._circolari()["elenco"]], [3, 2, 1])

    def test_altri_registri_solo_con_l_indirizzo(self):
        n = profili.salva(dict(NUVOLA))
        dati.attiva(n)
        self.assertIsNone(dati.scarica_circolari())
        self.assertIsNone(dati._circolari())
        self.circolari.assert_not_called()
        n = profili.salva({**NUVOLA, "password": "", "circolari": "https://trasparenza-pa.net/?codcli=SC9&node=77"}, n["id"])
        dati.attiva(n)
        dati.scarica_circolari()
        self.circolari.assert_called_once_with("SC9", "77")
        with self.assertRaisesRegex(profili.ProfiloNonValido, "trasparenza-pa.net"):
            profili.salva({**NUVOLA, "circolari": "https://example.com/circolari"})

    def test_cambiando_scuola_si_ricomincia(self):
        p = profili.salva(dict(ARGO))
        dati.attiva(p)
        self.circolari.return_value = ("900", [circolare(1, "2026-11-01")])
        dati.scarica_circolari()
        p = profili.salva({**ARGO, "scuola": "SC99999", "password": ""}, p["id"])
        self.assertFalse(dati.CACHE_CIRCOLARI.exists())


class ConAggiorna(aiuti.ServerProfili):
    def test_sito_delle_circolari_giu_non_ferma_il_registro(self):
        id_ = self.chiama("POST", "/api/profili", {"profilo": ARGO})[1]["salvato"]
        self.chiama("POST", "/api/profili/attiva", {"id": id_})
        self.circolari.side_effect = circolari.ErroreCircolari("il sito delle circolari ha risposto HTTP 503")
        with mock.patch.object(dati, "scarica", return_value={}):
            stato, risposta = self.chiama("POST", "/api/aggiorna", {})
        self.assertEqual(stato, 200)
        self.assertIn("Circolari non aggiornate: il sito delle circolari ha risposto HTTP 503.", risposta["avviso"])


if __name__ == "__main__":
    unittest.main()
