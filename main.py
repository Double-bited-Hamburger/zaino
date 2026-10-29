"""Avvia l'app del registro: un server locale più la pagina nel browser."""

import argparse
import os
import secrets
import sys
import time
import webbrowser
from pathlib import Path

import aggiornamenti
import config
import dati
import profili
import server
import sincronizza
from archivio import ErroreRegistro


def struttura(valore, nome="dati", livello=0, massimo=4):
    """Stampa com'è fatto un dato (nomi dei campi, tipi, quantità) senza mostrarne il contenuto."""
    rientro = "  " * livello
    if isinstance(valore, dict):
        print(f"{rientro}{nome}: oggetto con {len(valore)} campi")
        if livello < massimo:
            # Le chiavi che sono date o numeri (es. un giorno, un identificativo) si mostrano una volta sola.
            variabili = [k for k in valore if any(c.isdigit() for c in str(k))]
            for chiave in [k for k in valore if k not in variabili] + variabili[:1]:
                struttura(valore[chiave], "<chiave variabile>" if chiave in variabili else chiave, livello + 1, massimo)
    elif isinstance(valore, list):
        print(f"{rientro}{nome}: lista di {len(valore)}")
        if valore and livello < massimo:
            struttura(valore[0], "(primo elemento)", livello + 1, massimo)
    else:
        print(f"{rientro}{nome}: {type(valore).__name__}")


def dump(nome):
    """Scarica i dati del profilo indicato (o dell'ultimo usato) e ne mostra solo la struttura."""
    tutti = profili.elenco()
    scelto = next((p for p in tutti if p["nome"].lower() == nome.lower()), None) if nome else profili.trova(profili.ultimo()) or (tutti[0] if tutti else None)
    if not scelto:
        sys.exit("Profilo non trovato. Profili esistenti: " + (", ".join(p["nome"] for p in tutti) or "nessuno (creane uno dall'app)"))
    dati.attiva(scelto)
    try:
        scaricati = dati.scarica()
    except ErroreRegistro as errore:
        sys.exit(f"Errore: {errore}")
    print(f"Profilo «{scelto['nome']}», registro {profili.REGISTRI[scelto['registro']]}\n")
    # Per Nuvola e ClasseViva interessa la forma originale dei dati, prima dell'adattamento.
    struttura(scaricati.get("nuvola") or scaricati.get("classeviva") or scaricati["dashboard"])
    print(f"\nDati grezzi salvati in {dati.CACHE}")


def gettone_locale():
    """Il segreto con cui la pagina si fa riconoscere dal server (gli altri programmi del PC non lo conoscono).

    Sta in un file della cartella dei dati, così anche un secondo avvio (app già aperta) lo ritrova.
    """
    file = (Path(config.DATI_DIR) if config.DATI_DIR else Path(__file__).parent) / "cache" / "gettone_locale"
    try:
        gettone = file.read_text(encoding="utf-8").strip()
    except OSError:
        gettone = ""
    if len(gettone) < 32:
        gettone = secrets.token_urlsafe(32)
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(gettone, encoding="utf-8")
        os.chmod(file, 0o600)  # su Linux e macOS lo legge solo il tuo utente (su Windows ci pensa la cartella utente)
    return gettone


def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--dump", nargs="?", const="", metavar="PROFILO", help="scarica i dati di un profilo e mostra solo la loro struttura")
    args.add_argument("--senza-browser", action="store_true", help="avvia l'app senza aprire il browser")
    args.add_argument("--version", action="version", version=f"Zaino {config.VERSIONE}")
    args.add_argument("--dopo-aggiornamento", action="store_true", help=argparse.SUPPRESS)  # lo passa la versione precedente (aggiornamenti.installa)
    opzioni = args.parse_args()

    aggiornamenti.pulisci()
    profili.importa_cartella_del_programma()
    profili.migra_vecchia_installazione()
    if opzioni.dump is not None:
        return dump(opzioni.dump)

    if not config.GETTONE:
        config.GETTONE = gettone_locale()
    indirizzo = f"http://{server.INDIRIZZO}:{config.PORTA}/?accesso={config.GETTONE}"
    # Dopo un aggiornamento la versione precedente si sta ancora chiudendo: si aspetta che liberi la porta.
    for _ in range(40 if opzioni.dopo_aggiornamento else 1):
        try:
            app = server.avvia()
            break
        except OSError:
            if not opzioni.dopo_aggiornamento:
                # Porta occupata: l'app è già in esecuzione, basta riaprire la pagina.
                webbrowser.open(indirizzo)
                return
            time.sleep(0.5)
    else:
        sys.exit("La versione precedente non si è chiusa: chiudi questa finestra e riapri Zaino.")
    print(f"Zaino {config.VERSIONE} aperto su http://{server.INDIRIZZO}:{config.PORTA}/ (solo su questo computer)")
    print("Lascia aperta questa finestra mentre lo usi. Per chiudere: Ctrl+C oppure chiudi la finestra.")
    if not profili.portachiavi_disponibile():
        print("Attenzione: il portachiavi del sistema non è disponibile, le password dei registri restano in un file della cartella profili.")
    sincronizza.avvia_ascolto(server.BLOCCO)  # solo se la sincronizzazione col telefono è stata attivata
    if opzioni.dopo_aggiornamento:
        pass  # la pagina già aperta si ricarica da sola appena risponde la versione nuova
    elif opzioni.senza_browser:
        print(f"Collegamento per aprire la pagina (non condividerlo): {indirizzo}")
    else:
        webbrowser.open(indirizzo)
    try:
        app.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
