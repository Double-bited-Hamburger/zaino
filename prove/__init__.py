"""Le prove di Zaino. Si lanciano dalla cartella del progetto, tutte insieme o un file alla volta:

    python -m unittest                      (tutte)
    python -m unittest prove.test_accesso   (un file solo)

Qualunque prova si lanci, prima di tutto passa da qui, che rende l'ambiente sicuro:
- i dati stanno in una cartella temporanea, cancellata alla fine: i tuoi profili, il .env e la cache non si toccano;
- il portachiavi del sistema (Gestione credenziali di Windows) non si usa: le prove che lo riguardano ne usano uno finto;
- niente Internet: una prova che prova a collegarsi a un sito vero riceve un errore di rete e fallisce
  (vedi aiuti.Base). Si possono usare solo gli indirizzi di questo computer e della rete di casa.
"""

import atexit
import ipaddress
import os
import shutil
import socket
import tempfile
from pathlib import Path

# Prima di importare l'app: config legge queste variabili una volta sola.
CARTELLA = Path(tempfile.mkdtemp(prefix="zaino-prove-"))
os.environ["DATI_DIR"] = str(CARTELLA)
for _nome in ("CHIAVE_CREDENZIALI", "GETTONE_LOCALE", "ANDROID_APP", "WEB_DIR", "PORT", "PORTA_SYNC"):
    os.environ.pop(_nome, None)
atexit.register(shutil.rmtree, CARTELLA, ignore_errors=True)

# ---------- niente Internet ----------

TENTATIVI_RETE = []  # i nomi dei siti che una prova ha cercato di raggiungere
_getaddrinfo = socket.getaddrinfo


def _di_casa(host):
    if host in ("localhost", ""):
        return True
    try:
        ip = ipaddress.ip_address(host.split("%")[0])
    except ValueError:
        return False  # un nome (portaleargo.it, …): andrebbe cercato su Internet
    return ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_unspecified


def _solo_indirizzi_di_casa(host, *argomenti, **opzioni):
    nome = host.decode() if isinstance(host, bytes) else host
    if nome is None or _di_casa(nome):
        return _getaddrinfo(host, *argomenti, **opzioni)
    TENTATIVI_RETE.append(nome)
    raise socket.gaierror(socket.EAI_NONAME, f"Le prove non usano Internet (richiesta a {nome})")


socket.getaddrinfo = _solo_indirizzi_di_casa

# ---------- niente portachiavi vero, niente .env vero ----------

import profili  # noqa: E402  (dopo DATI_DIR)

PORTACHIAVI_VERO = profili._portachiavi
profili._portachiavi = lambda: None
profili.BASE = CARTELLA / "programma"  # qui la migrazione cercherebbe il vecchio .env: non c'è
