"""Test del login Argo, con risposte finte: nessun collegamento vero."""

import unittest
from types import SimpleNamespace
from unittest import mock

from argo_client import AUTH_URL, LOGIN_URL, REDIRECT_URI, ArgoClient, ArgoError

CONTINUA = f"""<html><body><h1>Accesso completato</h1>
<a class="auth-button" href="{AUTH_URL}?client_id=x&amp;login_verifier=y" data-auth-app-redirect rel="noopener">Continua</a>
<a href="https://www.portaleargo.it">Argo</a></body></html>"""


def risposta(url, location=None, testo=""):
    return SimpleNamespace(url=url, headers={"location": location} if location else {}, text=testo)


class TestLogin(unittest.TestCase):
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
        client = self.client(risposta(LOGIN_URL, testo="<html><a href='/recupera'>Password dimenticata?</a></html>"))
        with self.assertRaisesRegex(ArgoError, "Login rifiutato"):
            client._get_code("verificatore")


if __name__ == "__main__":
    unittest.main()
