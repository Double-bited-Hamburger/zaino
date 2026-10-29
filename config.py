"""Impostazioni modificabili a mano."""

# Un promemoria che contiene una di queste parole viene considerato una verifica.
# Maiuscole e minuscole non contano; l'asterisco finale vale per qualsiasi desinenza
# ("verific*" trova verifica, verifiche, verificheremo...).
PAROLE_VERIFICA = [
    "verific*",
    "compito in classe",
    "compiti in classe",
    "interrogazion*",
    "interrog*",
    "prova",
    "prove",
    "test",
    "simulazion*",
    "esposizion*",
]

# Nomi brevi da mostrare al posto di quelli del registro (chiave in MAIUSCOLO, come su Argo).
NOMI_MATERIE = {
    "LINGUA E LETTERATURA ITALIANA": "Italiano",
    "LINGUA INGLESE": "Inglese",
    "MATEMATICA/COMPLEMENTI DI MATEMATICA": "Matematica",
    "TEC. E PROG. DI SISTEMI INFORMATICI E TELEC.": "TPSIT",
    "SCIENZE MOTORIE E SPORTIVE": "Scienze motorie",
}

# Sigle usate dai prof nei promemoria -> materia del registro. Servono quando un
# docente insegna più materie e bisogna capire a quale si riferisce la verifica.
ALIAS_MATERIE = {
    "tps": "TEC. E PROG. DI SISTEMI INFORMATICI E TELEC.",
    "tpsit": "TEC. E PROG. DI SISTEMI INFORMATICI E TELEC.",
}

import os
import sys

VERSIONE = "0.5.1"

# Porta su cui gira l'app sul tuo PC (http://127.0.0.1:PORTA). L'app ascolta solo su questo dispositivo.
PORTA = int(os.environ.get("PORT") or 8765)
INDIRIZZO = "127.0.0.1"
# zaino.exe per Windows (PyInstaller): il programma è un file solo, che un aggiornamento sostituisce.
EXE = bool(getattr(sys, "frozen", False))
# Dove stanno profili e dati scaricati (vuoto = accanto al programma; per zaino.exe in %APPDATA%\Zaino).
DATI_DIR = os.environ.get("DATI_DIR") or (os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Zaino") if EXE else "")

# App Android: le imposta l'app stessa all'avvio (vedi ANDROID.md), a mano non servono.
ANDROID = bool(os.environ.get("ANDROID_APP"))
# Il segreto con cui sul telefono si cifrano su disco le password dei registri (lo custodisce l'Android Keystore).
CHIAVE_CREDENZIALI = os.environ.get("CHIAVE_CREDENZIALI", "")
# Anche altri programmi possono chiamare 127.0.0.1: la pagina si fa riconoscere con questo cookie.
# Sul telefono lo passa l'app Android, sul PC lo crea main.py (vedi gettone_locale).
GETTONE = os.environ.get("GETTONE_LOCALE", "")
WEB_DIR = os.environ.get("WEB_DIR") or (os.path.join(sys._MEIPASS, "web") if EXE else "")

# Porta su cui il PC ascolta il telefono per la sincronizzazione in rete locale (solo se attivata dall'app).
PORTA_SYNC = int(os.environ.get("PORTA_SYNC") or 8766)

# Per quanti giorni un compito scaduto resta visibile nella scheda Compiti.
GIORNI_SCADUTI = 7

# Assenze: l'anno è valido se non superi il 25% del monte ore annuale.
ORE_SETTIMANALI = 32
SETTIMANE_SCUOLA = 33
LIMITE_ASSENZE = 0.25

# Registro, credenziali e scuola WebUntis si impostano nei profili, dall'app.

# Lezioni dell'orario di classe che non ti riguardano (basta una parte del nome della materia).
ORARIO_NASCONDI = ["Sostegno", "Religione"]

# WebUntis a volte mostra due materie come una sola (es. «Italiano-Storia»): qui si indica, per giorno
# (0 = lunedì) e ora d'inizio, quale delle due è davvero. Le ore non elencate restano com'è scritto su WebUntis.
# Dipende dalla tua classe: mettila in config_locale.py. Esempio:
#   ORARIO_DIVISIONE = {"italiano-storia": {(0, "12:00"): "Storia", (1, "12:00"): "Italiano"}}
ORARIO_DIVISIONE = {}

# Sigle da lasciare in maiuscolo nei nomi delle materie dell'orario.
SIGLE = ["TPSIT", "IRC"]

# Voto minimo per la sufficienza.
SUFFICIENZA = 6.0

# Quanti voti recenti confrontare con i precedenti per calcolare l'andamento.
VOTI_RECENTI = 3

# Differenza minima tra le due medie perché l'andamento conti come salita/discesa.
SOGLIA_ANDAMENTO = 0.25

# Le tue impostazioni personali: un file config_locale.py accanto a questo, con gli stessi nomi (per esempio
# ORARIO_DIVISIONE o NOMI_MATERIE), vale al posto dei valori qui sopra. Non viene pubblicato (è nel .gitignore).
try:
    from config_locale import *  # noqa: F401,F403
except ImportError:
    pass
