"""Controllo di Zaino su questo computer: avvia.bat --diagnosi (oppure ./avvia.sh --diagnosi, zaino.exe --diagnosi).

Serve quando l'app rifiuta dati che sono giusti, o dice «dati non validi» a caso: controlla una cosa alla volta
(cartella dei dati, portachiavi, orologio, rete, accesso di ogni profilo) e dice cosa sistemare.
Non mostra mai password né dati del registro, e copre nomi, scuola e utente: il risultato si può copiare in una issue su GitHub.
"""

import os
import platform
import sys
import tempfile
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

import config
import dati
import profili
from archivio import CredenzialiRifiutate, ErroreRegistro

# Pagine che il server prepara sul momento: la sua intestazione Date dice l'ora vera (la homepage di Argo arriva da una cache).
SITI = {"Argo didUP": "https://www.portaleargo.it/auth/sso/login", "Nuvola": "https://nuvola.madisoft.it/", "ClasseViva": "https://web.spaggiari.eu/",
        "WebUntis (orario)": "https://mobile.webuntis.com/"}
OK, NO, INFO = "  ok ", "  !! ", "  -- "


def _coperto(testo):
    """mario.rossi → ma•••••••••: abbastanza per riconoscere il profilo, non per leggere il nome utente."""
    return testo[:2] + "•" * max(len(testo) - 2, 0)


def _sito(url):
    """(tempo del server o None, problema o "")."""
    try:
        risposta = requests.get(url, timeout=15, allow_redirects=False)
    except requests.exceptions.SSLError:
        return None, ("connessione sicura rifiutata: controlla data e ora, o l'antivirus che controlla le connessioni HTTPS "
                      "(se il browser apre il sito e Zaino no, è quasi sempre lui)")
    except requests.Timeout:
        return None, "nessuna risposta entro 15 secondi"
    except requests.RequestException as errore:
        return None, f"non raggiungibile ({type(errore).__name__}): controlla la connessione, o un firewall che blocca Python"
    if "Age" in risposta.headers:
        return None, ""  # copia in cache: la sua ora è quella di quando è stata salvata
    try:
        return parsedate_to_datetime(risposta.headers["Date"]), ""
    except (KeyError, TypeError, ValueError):
        return None, ""


def esegui(prova_accesso=True, stampa=print):
    """Stampa il controllo e restituisce quanti problemi ha trovato."""
    problemi = 0
    try:
        sys.stdout.reconfigure(errors="replace")  # una console che non conosce un carattere non deve fermare il controllo
    except (AttributeError, ValueError):
        pass

    def riga(esito, testo):
        nonlocal problemi
        problemi += esito == NO
        stampa(esito + testo)

    stampa(f"Zaino {config.VERSIONE} · Python {platform.python_version()} · {platform.platform()}"
           + (" · zaino.exe" if config.EXE else "") + (" · Android" if config.ANDROID else ""))

    stampa("\nCartella dei dati")
    cartella = profili.CARTELLA
    try:
        cartella.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=cartella):
            pass
        riga(OK, f"{cartella} (si può scrivere)")
    except OSError as errore:
        riga(NO, f"{cartella}: non si può scrivere ({errore.strerror or errore}). Sposta il programma in una cartella tua, "
                 "per esempio Documenti, invece che in Programmi o in una chiavetta protetta.")

    stampa("\nPassword")
    if config.CHIAVE_CREDENZIALI:
        riga(OK, "cifrate con la chiave del telefono")
    elif profili.portachiavi_disponibile():
        portachiavi = profili._portachiavi()
        nome = type(portachiavi.get_keyring()).__name__ if portachiavi else "?"
        riga(OK, f"nel portachiavi del sistema ({nome})")
    else:
        riga(INFO, "portachiavi del sistema non disponibile: le password stanno in un file della cartella dei dati, "
                   "leggibile solo dal tuo utente. Su Linux si può installare gnome-keyring o KWallet.")

    stampa("\nOrologio e rete")
    locale = datetime.now().astimezone()
    stampa(f"{INFO}ora di questo dispositivo: {locale:%d/%m/%Y %H:%M} (fuso {locale.tzname() or '?'})")
    scarti = []
    for nome, url in SITI.items():
        ora_server, problema = _sito(url)
        if problema:
            riga(NO, f"{nome}: {problema}")
            continue
        riga(OK, f"{nome}: raggiungibile")
        if ora_server:
            scarti.append(abs((datetime.now(timezone.utc) - ora_server).total_seconds()))
    if scarti and min(scarti) > 300:
        riga(NO, f"l'orologio è sbagliato di circa {round(min(scarti) / 60)} minuti: correggi data, ora e fuso orario "
                 "(con l'ora sbagliata le connessioni sicure e gli accessi possono fallire)")
    elif scarti:
        riga(OK, "orologio giusto")

    stampa("\nProfili")
    elenco = profili.elenco()
    if not elenco:
        stampa(f"{INFO}nessun profilo: crealo dall'app")
    for profilo in elenco:
        registro = profili.REGISTRI.get(profilo.get("registro"), profilo.get("registro"))
        # Nome, scuola e utente coperti: il risultato finisce in una issue pubblica.
        scuola = f", scuola {_coperto(profili.codice_scuola(profilo.get('scuola')))}" if profilo.get("registro") == "argo" else ""
        stampa(f"  «{_coperto(profilo['nome'])}» ({registro}{scuola}, utente {_coperto(profili.nome_utente(profilo.get('registro'), profilo.get('utente')))})")
        password = profili.password(profilo["id"])
        if not password:
            riga(NO, profili.perche_manca_password(profilo["id"]))
            continue
        if password != profili.password_pulita(password):
            stampa(f"{INFO}la password salvata ha spazi all'inizio o alla fine (o caratteri invisibili): se viene rifiutata, Zaino la riprova senza")
        if not prova_accesso:
            continue
        try:
            dati.accedi(profilo, password)
            riga(OK, "accesso al registro riuscito")
        except CredenzialiRifiutate as errore:
            riga(NO, f"{errore} Correggi i dati modificando il profilo.")
        except ErroreRegistro as errore:
            riga(NO, f"accesso non riuscito: {errore}")
        except requests.RequestException as errore:
            riga(NO, f"registro non raggiungibile ({type(errore).__name__})")

    stampa("\n" + ("Nessun problema trovato." if not problemi else
                   f"Problemi trovati: {problemi}. Se non sai come sistemarli, copia tutto questo in una issue: "
                   "https://github.com/Double-bited-Hamburger/zaino/issues (password e dati del registro qui non ci sono)."))
    return problemi


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    sys.exit(1 if esegui() else 0)
