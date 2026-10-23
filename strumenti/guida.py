"""Crea Guida.pdf, la guida di Zaino per chi lo usa: py strumenti/guida.py

Serve ReportLab (pip install reportlab), che non fa parte delle librerie dell'app.
Il testo è tutto qui sotto: per aggiornare la guida si cambia questo file e si rilancia.
Usa i caratteri standard dei PDF (Helvetica), quindi niente simboli fuori dall'alfabeto latino.
"""
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

USCITA = Path(__file__).resolve().parent.parent / "Guida.pdf"
ACCENTO, TESTO, GRIGIO, LINEA, TENUE = (colors.HexColor(c) for c in ("#2A78D6", "#1C2330", "#677084", "#E3E6EC", "#E6F0FC"))
VERSIONE = config.VERSIONE.rsplit(".0", 1)[0] if config.VERSIONE.endswith(".0") else config.VERSIONE

stile = {
    "titolo": ParagraphStyle("titolo", fontName="Helvetica-Bold", fontSize=30, leading=34, textColor=TESTO),
    "sotto": ParagraphStyle("sotto", fontName="Helvetica", fontSize=12, leading=16, textColor=GRIGIO, spaceBefore=4),
    "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=TESTO, spaceBefore=16, spaceAfter=6),
    "testo": ParagraphStyle("testo", fontName="Helvetica", fontSize=10, leading=14.5, textColor=TESTO, alignment=TA_LEFT),
    "cella": ParagraphStyle("cella", fontName="Helvetica", fontSize=9, leading=12.5, textColor=TESTO),
    "cella-b": ParagraphStyle("cella-b", fontName="Helvetica-Bold", fontSize=9, leading=12.5, textColor=TESTO),
    "testa": ParagraphStyle("testa", fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=GRIGIO),
}

flusso = []
P = lambda testo, s="testo": Paragraph(testo, stile[s])  # noqa: E731


def titolo(testo):
    flusso.append(P(testo, "h2"))


def paragrafo(testo):
    flusso.append(P(testo))
    flusso.append(Spacer(0, 4))


def elenco(voci):
    flusso.append(ListFlowable([ListItem(P(v), leftIndent=12, value="circle") for v in voci], bulletType="bullet", start="•",
                               bulletFontSize=9, leftIndent=12, bulletColor=ACCENTO))
    flusso.append(Spacer(0, 4))


def tabella(intestazione, righe, larghezze):
    dati = [[P(t, "testa") for t in intestazione]] + [[P(c, "cella-b" if i == 0 else "cella") for i, c in enumerate(r)] for r in righe]
    t = Table(dati, colWidths=[w * mm for w in larghezze], repeatRows=1)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINEA),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    flusso.append(t)
    flusso.append(Spacer(0, 6))


def passi(voci):
    """La fila di riquadri numerati di «Come funziona»."""
    celle = [[P(f'<font color="#2A78D6" size="15"><b>{i}</b></font><br/><b>{t}</b><br/><font color="#677084">{s}</font>', "cella") for i, (t, s) in enumerate(voci, 1)]]
    t = Table(celle, colWidths=[34 * mm] * len(voci))
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), TENUE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEAFTER", (0, 0), (-2, -1), 3, colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8), ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    flusso.append(t)
    flusso.append(Spacer(0, 8))


# ---------------------------------------------------------------- testo della guida

flusso.append(P("Zaino", "titolo"))
flusso.append(P(f"Guida alla versione {VERSIONE}: come si usa e come funziona l'app che mette insieme registro elettronico e orario WebUntis.", "sotto"))
flusso.append(Spacer(0, 8))

titolo("In breve")
paragrafo("Zaino è un'app per studenti. Legge il registro elettronico con il tuo account (Argo didUP, Nuvola oppure, in prova, "
          "ClasseViva) e l'orario della classe da WebUntis, e mette tutto in un'unica pagina divisa in sette schede: Oggi, Agenda, "
          "Compiti, Orario, Voti, Carico di lavoro e Assenze. Gira sul PC (Windows, Linux, macOS) e come app Android; le due copie "
          "si sincronizzano in Wi-Fi.")
paragrafo("<b>Legge soltanto</b>: sul registro e su WebUntis non modifica nulla. <b>È tutto locale</b>: non c'è un server del progetto, "
          "né account, pubblicità o statistiche d'uso. Prima si chiamava «Parser Compiti».")

titolo("Come funziona")
passi([("Avvio", "avvia.bat o avvia.sh apre la pagina nel browser"), ("Download", "registro e orario, con le tue credenziali"),
       ("Estrazione", "verifiche, compiti, voti, assenze, lezioni"), ("Calcoli", "medie, carico di lavoro, ore perse"),
       ("Pagina", "le sette schede, con spunte e grafici")])
paragrafo("Entrando in un profilo (se i dati hanno più di mezz'ora) e ogni volta che premi «Aggiorna», l'app riscarica il registro e "
          "l'orario di questa settimana e della prossima. Le copie restano nella cartella del profilo, così la pagina si apre anche "
          "senza Internet.")

titolo("Installazione")
tabella(["Dove", "Come"], [
    ["PC", "Serve Python 3.12 o successivo. Scarica il codice dalla pagina della versione su GitHub («Source code (zip)»), "
           "scompattalo e avvia <b>avvia.bat</b> (Windows) oppure <b>./avvia.sh</b> (Linux e macOS). La prima volta prepara da solo "
           "la sottocartella .venv con le librerie: ci vuole qualche minuto. La finestra del terminale deve restare aperta mentre "
           "usi l'app."],
    ["Telefono", "Scarica l'APK dalle Release del progetto su GitHub, aprilo e consenti l'installazione. Serve Android 7 o "
                 "successivo. Installa l'APK solo da lì: uno preso altrove potrebbe essere stato modificato."],
    ["Aggiornare", "Sul PC scarica la versione nuova in una cartella nuova e copiaci la sottocartella <b>profili</b> (e il tuo "
                   "config_locale.py, se l'hai creato). Sul telefono installa il nuovo APK sopra quello vecchio: i dati restano."],
], [28, 142])

titolo("Le schede")
tabella(["Scheda", "Cosa trovi"], [
    ["Oggi", "Quattro numeri (compiti da fare, verifiche della settimana, giorni alla prossima verifica, media generale), "
             "il riquadro «Adesso» con il conto alla rovescia alla fine dell'ora, l'orario del giorno con lo stato di ogni ora, "
             "i compiti per il giorno dopo da spuntare, le verifiche in arrivo e gli ultimi voti."],
    ["Agenda", "Il calendario del mese con un puntino per ogni impegno: verifiche, compiti, variazioni d'orario, promemoria. "
               "Tocchi un giorno e accanto vedi cosa c'è. Sotto, gli elenchi completi e il testo da copiare in Google Calendar."],
    ["Compiti", "La settimana come un planner: sul PC una colonna per giorno, sul telefono una striscia di giorni da toccare. "
                "Spunti i compiti fatti, li puoi nascondere, cerchi per parola, scarichi il PDF. Gli scaduti restano in vista per "
                f"{config.GIORNI_SCADUTI} giorni."],
    ["Orario", "La griglia della settimana, che sta nello schermo anche sul telefono (sigle delle materie, nomi interi sul PC). "
               "Ogni materia ha il suo colore; l'ora in corso è evidenziata, le variazioni hanno un bordo e un puntino. Tocchi "
               "un'ora per vedere aula, docente e cosa è cambiato. «Cosa cambia» elenca supplenze, ore annullate e cambi d'aula. "
               "C'è anche il PDF della settimana."],
    ["Voti", "«Cosa fare adesso» (materie sotto il 6, in calo, verifiche vicine), una scheda per materia con mini-grafico, "
             "andamento, scritto/orale/pratico e voto minimo per restare al 6. Il simulatore «Che voto mi serve?» mostra subito "
             "come cambiano le medie. Grafici ed elenco completo in sezioni che si aprono."],
    ["Carico di lavoro", "Quanto lavoro c'è questa settimana rispetto alla media, i prossimi 14 giorni con un pallino per ogni "
                         "compito e verifica (in rosso i giorni pieni), i giorni pieni in arrivo con un consiglio e da quali "
                         "materie o docenti arriva il lavoro."],
    ["Assenze", "Quante ore puoi ancora perdere, con la barra che diventa rossa dall'80% del limite e la previsione a fine "
                "anno al ritmo di adesso. Poi assenze e ritardi da giustificare, ultimi eventi e ore perse per materia."],
], [32, 138])
paragrafo("In alto a destra scegli il tema: Automatico (chiaro o scuro come il sistema), Scuro, Quaderno, Terminale, Nothing e Ultra.")

titolo("Profili e registri")
elenco([
    "Un profilo contiene il registro usato, le credenziali, la scuola e la classe WebUntis (facoltative), i dati scaricati e i "
    "compiti spuntati. I profili non si mescolano mai: puoi averne uno per ogni fratello.",
    "Registri: <b>Argo didUP</b> e <b>Nuvola</b> (studenti e tutori) sono stabili; <b>ClasseViva</b> è in prova. Con un account "
    "genitore con più figli, dopo il primo «Aggiorna» nel profilo compare «Studente da mostrare».",
    "Orario: <b>WebUntis</b>, letto in accesso anonimo come dal sito della scuola, senza credenziali. I docenti compaiono come "
    "sigle: l'app le abbina ai nomi del registro; una sigla rimasta è un supplente che non compare nel registro.",
    "Su Argo le verifiche sono promemoria scritti a mano: l'app le riconosce dalle parole nel testo (verifica, interrogazione, "
    "compito in classe, prova, test...) e capisce la materia dal docente o dal nome scritto nel testo.",
])

titolo("Telefono: sincronizzazione, notifiche e widget")
elenco([
    "<b>Sincronizzazione</b>: sul PC apri Profili, riquadro «Sincronizzazione con il telefono», «Attiva»: compare un codice di "
    "20 caratteri. Sul telefono scrivilo in «Sincronizzazione con il PC» e premi «Abbina e sincronizza». Da lì in poi il "
    "telefono si allinea da solo quando è sullo stesso Wi-Fi e l'app del PC è aperta. Passa solo testo cifrato, mai da Internet.",
    "<b>Notifiche</b>: ogni due ore circa (dalle 7 alle 22) l'app controlla il registro e avvisa di nuovi voti, verifiche, compiti "
    "e cambi d'orario; nel tardo pomeriggio ricorda i compiti per domani non ancora spuntati.",
    "<b>Widget</b>: «Compiti», «Prossima verifica» e «Adesso» (la lezione in corso con il conto alla rovescia). Tieni premuto "
    "sulla schermata home, poi Widget, poi Zaino.",
])

titolo("Come fa i calcoli")
tabella(["Voce", "Come si calcola", "Esempio"], [
    ["Media", "Somma dei voti che fanno media divisa per il loro numero. La media generale è la media delle medie di materia.",
     "5, 6, 7: media 6"],
    ["Andamento", f"Media degli ultimi {config.VOTI_RECENTI} voti contro quella dei precedenti: sale o scende se la differenza "
                  f"supera {str(config.SOGLIA_ANDAMENTO).replace('.', ',')}. Servono almeno 4 voti.", "prima 5, ultimi tre 6,5: in salita"],
    ["Voto minimo per il 6", "Il voto più basso che puoi prendere alla prossima prova restando (o tornando) al 6, arrotondato "
                             "al quarto di voto.", "7 e 8: basta un 3"],
    ["Simulatore", "Aggiunge voti ipotetici e ricalcola media di materia e media generale.", "7,5 più un 4: 5,75"],
    ["Giorno pieno", "Due verifiche, oppure quattro cose in tutto tra compiti e verifiche, nello stesso giorno.", "1 verifica + 3 compiti"],
    ["Ore perse", "Assenza: le ore firmate quel giorno. Ritardo: le ore prima dell'ingresso. Uscita: da quell'ora in poi.",
     "ingresso alla 3a ora: 2 ore"],
    ["Limite", f"Il {round(config.LIMITE_ASSENZE * 100)}% del monte ore annuale, stimato in {config.ORE_SETTIMANALI} ore per "
               f"{config.SETTIMANE_SCUOLA} settimane.", f"{round(config.ORE_SETTIMANALI * config.SETTIMANE_SCUOLA * config.LIMITE_ASSENZE)} ore"],
    ["Previsione", "Le ore perse finora divise per quelle svolte, moltiplicate per il monte ore dell'anno.", "6 su 9: due terzi"],
], [32, 98, 40])

titolo("Cosa puoi personalizzare")
paragrafo("Le impostazioni stanno in <b>config.py</b>. Per cambiarle senza toccarlo crea accanto un file <b>config_locale.py</b> "
          "con le sole voci diverse (per esempio ORE_SETTIMANALI = 30): resta tuo anche quando aggiorni l'app. Dopo una modifica "
          "chiudi e riavvia.")
tabella(["Impostazione", "A cosa serve"], [
    ["PAROLE_VERIFICA", "Le parole che fanno riconoscere un promemoria come verifica."],
    ["NOMI_MATERIE, ALIAS_MATERIE", "I nomi brevi delle materie e le sigle usate dai professori (per esempio «TPS»)."],
    ["ORARIO_NASCONDI", "Le lezioni dell'orario di classe che non ti riguardano (per esempio Sostegno, Religione)."],
    ["ORARIO_DIVISIONE", "Come dividere un'ora che WebUntis segna con due materie insieme."],
    ["ORE_SETTIMANALI, SETTIMANE_SCUOLA", "La stima del monte ore annuale per il limite delle assenze."],
    ["SUFFICIENZA, VOTI_RECENTI", "Il voto della sufficienza e quanti voti recenti usare per l'andamento."],
    ["GIORNI_SCADUTI", "Per quanti giorni restano in vista i compiti scaduti."],
], [58, 112])

titolo("Se qualcosa non va")
tabella(["Problema", "Cosa fare"], [
    ["«Login rifiutato»", "Apri Profili, Modifica, e ricontrolla utente e password (per Argo anche il codice scuola)."],
    ["La pagina non si apre", "Controlla che la finestra del terminale aperta da avvia.bat o avvia.sh sia ancora aperta; "
                              "altrimenti riavvia. Aprire a mano 127.0.0.1:8765 non basta: serve lo script."],
    ["«Orario non aggiornato»", "WebUntis non ha risposto: il resto funziona, riprova più tardi con «Aggiorna»."],
    ["Una verifica non compare", "Guarda tra i promemoria dell'Agenda: se è lì, aggiungi la parola usata dal professore a PAROLE_VERIFICA."],
    ["La materia è sbagliata", "Aggiungi la sigla usata dal professore ad ALIAS_MATERIE."],
    ["Il telefono non trova il PC", "App del PC aperta con la sincronizzazione attiva, stessa rete (non quella «ospiti»), "
                                     "Python consentito dal firewall sulle reti private (porta 8766)."],
    ["Si vede ancora la grafica vecchia", "Ricarica la pagina con Ctrl+F5."],
    ["«Errore interno» o registro cambiato", "I dettagli sono in cache/errori.log. Con avvia.bat --dump (./avvia.sh --dump su Linux e "
                                             "macOS), da un terminale aperto nella cartella del programma, l'app stampa solo la struttura "
                                             "dei dati, senza contenuti: si può allegare a una segnalazione su GitHub."],
], [52, 118])

titolo("Sicurezza e dati personali")
elenco([
    "Le password stanno nel portachiavi del sistema (su Windows il Gestione credenziali); sul telefono sono cifrate con una "
    "chiave dell'Android Keystore. Vengono inviate soltanto al registro del profilo.",
    "La pagina risponde solo al collegamento aperto dallo script di avvio, che contiene un gettone segreto: gli altri programmi "
    "e gli altri utenti del computer non leggono i tuoi dati.",
    "La cartella <b>profili</b> contiene i dati scolastici: non condividerla. Nelle segnalazioni non incollare mai password, voti o nomi.",
    "Zaino non è un prodotto ufficiale di Argo, Madisoft, Spaggiari o Untis: usa le stesse interfacce delle loro app per le "
    "famiglie, solo in lettura. Se una di queste cambia, può servire un aggiornamento.",
])


def piede(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GRIGIO)
    canvas.drawString(18 * mm, 10 * mm, f"Zaino {VERSIONE} - guida")
    canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Pagina {doc.page}")
    canvas.restoreState()


doc = SimpleDocTemplate(str(USCITA), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
                        title="Zaino - guida", author="Zaino", subject=f"Guida alla versione {VERSIONE}", invariant=1)
doc.build(flusso, onFirstPage=piede, onLaterPages=piede)
print(f"Scritto {USCITA.name}")
