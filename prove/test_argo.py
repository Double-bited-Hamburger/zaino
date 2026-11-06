"""Il login di Argo didUP, con risposte finte: nessun collegamento vero."""

import unittest
from unittest import mock

from archivio import CredenzialiRifiutate
from argo_client import AUTH_URL, LOGIN_URL, REDIRECT_URI, ArgoClient, ArgoError
from prove.aiuti import Risposta

CONTINUA = f"""<html><body><h1>Accesso completato</h1>
<a class="auth-button" href="{AUTH_URL}?client_id=x&amp;login_verifier=y" data-auth-app-redirect rel="noopener">Continua</a>
<a href="https://www.portaleargo.it">Argo</a></body></html>"""

# Com'è fatta la pagina vera quando i dati sono sbagliati (novembre 2026): un avviso nascosto sull'orologio,
# che la pagina mostra solo se serve, e quello visibile con il motivo.
RIFIUTO = """<html><body><div class="auth-card__body card-body pt-0">
  <div class="alert alert-danger" id="clockScrewWarning" role="alert" style="display:none;">
    <div class="container">Attenzione l'orologio del tuo sistema non &egrave; sincronizzato.<ul><li>Server Argo: <span></span></li></ul></div>
  </div>
  <div class="alert alert-danger" role="alert">
    <div class="container">
      Username e/o password non validi
    </div>
  </div>
  <form id="loginForm" method="POST" action="/auth/sso/login"><input type="hidden" name="challenge" value="x"/>
  <input id="password" name="password" type="password"></form></div></body></html>"""


def risposta(url, location=None, testo="", stato=200):
    return Risposta(url, stato=stato, testo=testo, intestazioni={"location": location} if location else {})


class Login(unittest.TestCase):
    def client(self, dopo_il_login, *altre_get):
        client = ArgoClient("SCUOLA", "utente", "password")
        client.session = mock.Mock()
        client.session.get.side_effect = [risposta(AUTH_URL, "https://www.portaleargo.it/auth/sso/login/?login_challenge=abc"), *altre_get]
        client.session.post.return_value = dopo_il_login
        return client

    def test_pagina_accesso_completato_al_posto_del_redirect(self):
        client = self.client(
            risposta(LOGIN_URL, "/auth/sso/consent/"),
            risposta("https://www.portaleargo.it/auth/sso/consent/", testo=CONTINUA),
            risposta(AUTH_URL, f"{REDIRECT_URI}?code=il-codice"),
        )
        self.assertEqual(client._get_code("verificatore"), "il-codice")
        self.assertEqual(client.session.get.call_args.args[0], f"{AUTH_URL}?client_id=x&login_verifier=y")

    def test_senza_pagina_intermedia(self):
        client = self.client(risposta(LOGIN_URL, f"{REDIRECT_URI}?code=il-codice"))
        self.assertEqual(client._get_code("verificatore"), "il-codice")

    def test_credenziali_sbagliate(self):
        """Solo quando Argo lo dice si parla di dati sbagliati, con le sue parole; l'avviso nascosto non conta."""
        client = self.client(risposta(LOGIN_URL, testo=RIFIUTO))
        with self.assertRaisesRegex(CredenzialiRifiutate, "Username e/o password non validi") as errore:
            client._get_code("verificatore")
        self.assertNotIn("orologio", str(errore.exception))
        self.assertFalse(errore.exception.temporaneo)

    def test_argo_in_difficolta_non_sono_credenziali_sbagliate(self):
        """Manutenzione, errori del server, troppi tentativi, pagine nuove: «riprova», mai «controlla la password»."""
        casi = [
            (risposta(LOGIN_URL, testo="<h1>Service Unavailable</h1>", stato=503), "non risponde", True),
            (risposta(LOGIN_URL, testo="", stato=429), "troppi tentativi", True),
            (risposta(LOGIN_URL, testo="<html><a href='/recupera'>Password dimenticata?</a></html>"), "pagina inattesa", True),
            (risposta(LOGIN_URL, testo='<div class="alert alert-warning">Sistema in manutenzione fino alle 14</div>'), "manutenzione", False),
        ]
        for pagina, messaggio, temporaneo in casi:
            with self.subTest(messaggio):
                with self.assertRaisesRegex(ArgoError, messaggio) as errore:
                    self.client(pagina)._get_code("verificatore")
                self.assertNotIsInstance(errore.exception, CredenzialiRifiutate)
                self.assertEqual(errore.exception.temporaneo, temporaneo)

    def test_pagina_di_login_che_non_arriva(self):
        client = ArgoClient("SCUOLA", "utente", "password")
        client.session = mock.Mock()
        client.session.get.return_value = risposta(AUTH_URL, testo="errore", stato=502)
        with self.assertRaisesRegex(ArgoError, "non risponde") as errore:
            client._get_code("verificatore")
        self.assertTrue(errore.exception.temporaneo)

    def test_pagina_rovinata(self):
        """Un HTML spezzato non deve diventare un errore incomprensibile."""
        client = self.client(risposta(LOGIN_URL, testo="<div class='alert'><b>Username e/o password non validi</div></div></b><<<"))
        with self.assertRaises(CredenzialiRifiutate):
            client._get_code("verificatore")


if __name__ == "__main__":
    unittest.main()
