"""Lettura e scrittura sicura dei file JSON dell'app, e l'errore comune ai registri."""

import json
import os
import threading
import time

# Su Windows un file non si può sostituire mentre un'altra richiesta lo sta leggendo.
_blocco = threading.Lock()


class ErroreRegistro(Exception):
    """Un problema con il registro elettronico da mostrare all'utente così com'è.

    temporaneo: il registro non ha risposto come doveva (sito lento, in manutenzione, pagina inattesa),
    riprovare tra poco può bastare. Le credenziali sbagliate non lo sono mai (vedi CredenzialiRifiutate)."""

    def __init__(self, messaggio, temporaneo=False):
        super().__init__(messaggio)
        self.temporaneo = temporaneo


class CredenzialiRifiutate(ErroreRegistro):
    """Il registro ha detto chiaramente che codice scuola, utente o password sono sbagliati."""


def scrivi(percorso, contenuto):
    """Scrive il file in un colpo solo: se il programma viene chiuso a metà resta la versione precedente."""
    testo = json.dumps(contenuto, ensure_ascii=False, indent=1)
    with _blocco:
        percorso.parent.mkdir(parents=True, exist_ok=True)
        provvisorio = percorso.with_name(percorso.name + ".tmp")
        provvisorio.write_text(testo, encoding="utf-8")
        for tentativo in range(5):
            try:
                os.replace(provvisorio, percorso)
                return
            except PermissionError:  # file aperto per un attimo da antivirus o sincronizzazione
                if tentativo == 4:
                    raise
                time.sleep(0.1)


def leggi(percorso):
    """Il contenuto del file se è un oggetto JSON valido, altrimenti None."""
    try:
        with _blocco:
            testo = percorso.read_text(encoding="utf-8")
        contenuto = json.loads(testo)
    except (OSError, ValueError):
        return None
    return contenuto if isinstance(contenuto, dict) else None
