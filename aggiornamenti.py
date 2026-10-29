"""Aggiornamenti dell'app: controlla le Release su GitHub e, per zaino.exe, si sostituisce con la versione nuova.

Non scarica mai niente da solo: il controllo (una volta al giorno, se attivo) dice solo se c'è una versione nuova,
e l'installazione parte quando l'utente la chiede dalla pagina.
"""

import hashlib
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import requests

import archivio
import config

REPOSITORY = "Double-bited-Hamburger/zaino"
ULTIMA = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
TIMEOUT = 20
UN_GIORNO = 86400
RIPROVA = 3600  # se GitHub non risponde, il controllo automatico riprova dopo un'ora
MASSIMO = 300 * 1024 * 1024  # un eseguibile più grande di così non è il nostro
FILE = (Path(config.DATI_DIR) if config.DATI_DIR else Path(__file__).parent) / "cache" / "aggiornamenti.json"


class ErroreAggiornamento(Exception):
    pass


def numeri(versione):
    """«0.5.1», «v0.2.1-beta» -> (0, 5, 1): per confrontare due versioni."""
    return tuple(int(n) for n in re.findall(r"\d+", str(versione or "").split("-")[0])[:3])


def eseguibile():
    """Il file zaino.exe in uso; None se l'app gira da Python (avvia.bat, avvia.sh) o sul telefono."""
    return Path(sys.executable) if config.EXE else None


def _ultima_release():
    risposta = requests.get(ULTIMA, headers={"Accept": "application/vnd.github+json"}, timeout=TIMEOUT)
    risposta.raise_for_status()
    dati = risposta.json()
    versione = str(dati.get("tag_name") or "")
    if not numeri(versione):
        raise ValueError("versione illeggibile")
    file = {a.get("name"): a.get("browser_download_url") for a in dati.get("assets") or [] if isinstance(a, dict)}
    exe = "zaino.exe"  # senza versione nel nome: il file sul PC resta lo stesso da un aggiornamento all'altro
    return {"versione": versione, "pagina": str(dati.get("html_url") or f"https://github.com/{REPOSITORY}/releases"),
            "exe": file.get(exe), "impronta": file.get(f"{exe}.sha256")}


def stato(forza=False):
    """Versione in uso, versione nuova (se c'è) e impostazioni. Con forza=True chiede a GitHub anche se l'ha fatto da poco."""
    if config.ANDROID:
        return {"disponibile": False}  # sul telefono l'APK si aggiorna dalla pagina delle Release
    salvato = archivio.leggi(FILE) or {}
    automatico = salvato.get("automatico", True) is not False
    adesso = time.time()
    errore = None
    scaduto = adesso - (salvato.get("controllato") or 0) > UN_GIORNO and adesso - (salvato.get("tentato") or 0) > RIPROVA
    if forza or (automatico and scaduto):
        salvato["tentato"] = adesso
        try:
            salvato["ultima"] = _ultima_release()
            salvato["controllato"] = adesso
        except (requests.RequestException, ValueError):
            errore = "GitHub non è raggiungibile: riprova più tardi."
        archivio.scrivi(FILE, salvato)
    ultima = salvato.get("ultima") if isinstance(salvato.get("ultima"), dict) else None
    nuova = ultima if ultima and numeri(ultima.get("versione")) > numeri(config.VERSIONE) else None
    controllato = salvato.get("controllato")
    return {
        "disponibile": True,
        "versione": config.VERSIONE,
        "automatico": automatico,
        "controllato": datetime.fromtimestamp(controllato).isoformat(timespec="minutes") if controllato else None,
        "nuova": {"versione": nuova["versione"], "pagina": nuova["pagina"]} if nuova else None,
        # Sostituirsi da solo lo sa fare solo zaino.exe; da Python si scarica a mano la versione nuova.
        "installabile": bool(nuova and nuova.get("exe") and nuova.get("impronta") and eseguibile()),
        "exe": bool(eseguibile()),
        "errore": errore,
    }


def imposta(automatico):
    salvato = archivio.leggi(FILE) or {}
    salvato["automatico"] = bool(automatico)
    archivio.scrivi(FILE, salvato)
    return stato()


def _scarica(url, destinazione):
    """Scarica url in destinazione e restituisce l'impronta SHA-256 di ciò che è arrivato."""
    impronta, scaricati = hashlib.sha256(), 0
    with requests.get(url, stream=True, timeout=TIMEOUT) as risposta, open(destinazione, "wb") as file:
        risposta.raise_for_status()
        for pezzo in risposta.iter_content(1024 * 256):
            scaricati += len(pezzo)
            if scaricati > MASSIMO:
                raise ErroreAggiornamento("Il file scaricato è troppo grande: aggiornamento annullato.")
            impronta.update(pezzo)
            file.write(pezzo)
    return impronta.hexdigest()


def installa():
    """Scarica zaino.exe nuovo, ne controlla l'impronta, prende il posto di quello in uso e lo avvia.

    Il file in uso non si può sovrascrivere ma si può rinominare: diventa zaino.vecchio.exe e lo cancella
    la versione nuova all'avvio (vedi pulisci). Restituisce la versione installata; chi chiama poi chiude l'app.
    """
    exe = eseguibile()
    ultima = (archivio.leggi(FILE) or {}).get("ultima") or {}
    if not exe or not ultima.get("exe") or not ultima.get("impronta") or numeri(ultima.get("versione")) <= numeri(config.VERSIONE):
        raise ErroreAggiornamento("Non c'è un aggiornamento da installare.")
    nuovo, vecchio = exe.with_name(f"{exe.stem}.nuovo.exe"), exe.with_name(f"{exe.stem}.vecchio.exe")
    try:
        attesa = requests.get(ultima["impronta"], timeout=TIMEOUT)
        attesa.raise_for_status()
        attesa = attesa.text.split()[0].strip().lower() if attesa.text.split() else ""
        if not re.fullmatch(r"[0-9a-f]{64}", attesa):
            raise ErroreAggiornamento("L'impronta della versione nuova è illeggibile: aggiornamento annullato.")
        if _scarica(ultima["exe"], nuovo) != attesa:
            raise ErroreAggiornamento("Il file scaricato non corrisponde alla sua impronta: aggiornamento annullato.")
    except requests.RequestException:
        nuovo.unlink(missing_ok=True)
        raise ErroreAggiornamento("Download non riuscito: controlla la connessione e riprova.") from None
    except ErroreAggiornamento:
        nuovo.unlink(missing_ok=True)
        raise
    except OSError:
        nuovo.unlink(missing_ok=True)
        raise ErroreAggiornamento(f"Non riesco a scrivere nella cartella di {exe.name}: scarica la versione nuova dalla pagina delle Release.") from None
    try:
        vecchio.unlink(missing_ok=True)
        exe.rename(vecchio)
    except OSError:
        nuovo.unlink(missing_ok=True)
        raise ErroreAggiornamento(f"Non riesco a sostituire {exe.name}: scarica la versione nuova dalla pagina delle Release.") from None
    try:
        nuovo.rename(exe)
    except OSError:
        vecchio.rename(exe)  # si torna come prima
        nuovo.unlink(missing_ok=True)
        raise ErroreAggiornamento(f"Non riesco a sostituire {exe.name}: scarica la versione nuova dalla pagina delle Release.") from None
    subprocess.Popen([str(exe), "--dopo-aggiornamento"], creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0), close_fds=True)
    return ultima["versione"]


def pulisci():
    """All'avvio di zaino.exe: cancella il file della versione precedente, appena quella ha finito di chiudersi."""
    exe = eseguibile()
    if not exe:
        return

    def cancella():
        for _ in range(30):
            try:
                exe.with_name(f"{exe.stem}.vecchio.exe").unlink(missing_ok=True)
                exe.with_name(f"{exe.stem}.nuovo.exe").unlink(missing_ok=True)
                return
            except OSError:
                time.sleep(1)

    threading.Thread(target=cancella, daemon=True).start()
