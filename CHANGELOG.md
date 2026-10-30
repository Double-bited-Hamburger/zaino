# Novità

## Prossima versione

- **Il tuo orario, anche senza WebUntis**: se il profilo non ha WebUntis, dalla scheda «Orario» puoi scrivere le ore della settimana a mano, con «Scrivi il tuo orario». Si aggiunge un'ora alla volta oppure si copia un giorno su quello dopo; poi l'orario si cambia con «Modifica l'orario». Sta nel profilo, quindi passa anche al telefono con la sincronizzazione.
- **Ore doppie**: quando WebUntis scrive un'ora come «Italiano-Storia», toccala nella scheda «Orario» e scegli quale materia è. La scelta vale per quel giorno della settimana e quell'ora, tutte le settimane. Se invece vuoi lasciarla com'è, c'è «Tutte e due».
- **Limite di assenze sull'orario vero**: il 25% ora si calcola sulle ore settimanali del tuo orario, di WebUntis o scritto a mano, e la scheda «Assenze» lo dice. Senza orario resta la stima di 32 ore di `config.py`.

## 0.6.0

- **Zaino per Windows è un programma vero**: nelle Release c'è `zaino.exe`, da scaricare e aprire con un doppio clic. Non serve installare Python. Profili e dati stanno in `%APPDATA%\Zaino`; se metti `zaino.exe` nella cartella di una versione precedente, al primo avvio li porta lì da solo. La prima volta Windows può dire «Windows ha protetto il PC»: *Ulteriori informazioni → Esegui comunque* (il programma non ha una firma a pagamento).
- **Aggiornamenti**: una volta al giorno Zaino controlla se c'è una versione nuova e, se c'è, te lo dice in alto con «Aggiorna ora» e «Più tardi». Non scarica niente da solo. Con `zaino.exe` «Aggiorna ora» scarica la versione nuova, ne controlla l'impronta SHA-256, si sostituisce e si riapre. Da Profili → Aggiornamenti puoi controllare subito o spegnere il controllo automatico.
- Le Release hanno due file da scaricare: `zaino.exe` per Windows e l'APK per Android. Li costruisce GitHub quando si pubblica la Release.

## 0.5.1

- **ClasseViva, compiti**: Spaggiari ha spostato i compiti nella nuova sezione «Compiti», che l'API dell'app non mette più nell'agenda: si vedevano solo quelli che alcuni prof scrivono ancora lì. Ora Zaino li legge dall'API del sito web.spaggiari.eu (un secondo accesso, con le stesse credenziali), insieme alla data in cui sono stati assegnati. Un compito presente in tutti e due i posti compare una volta sola. Se il sito non risponde il resto si aggiorna lo stesso: restano i compiti letti l'ultima volta e compare un avviso. Percorsi e campi vengono da [open-viva/endpoints](https://github.com/open-viva/endpoints).
- **Struttura dei dati per le segnalazioni**: il comando è `avvia.bat --dump` su Windows e `./avvia.sh --dump` su Linux e macOS, da un terminale aperto nella cartella del programma. `py main.py --dump`, indicato finora nel README, nella guida e nel modulo delle issue, non trova le librerie dell'app, che dalla 0.2.1 stanno in `.venv`.

## 0.5.0

Prima versione stabile: tutta l'interfaccia è stata ridisegnata, scheda per scheda.

- **Nuovo nome: Zaino** (prima «Parser Compiti», e «Registro» in cima alla pagina e sul telefono). Sul telefono l'app è firmata con una chiave nuova: chi ha la 0.2 la disinstalla una volta e installa la 0.5; profili, password e spunte tornano dal PC con la sincronizzazione.

- **Scheda «Oggi» ridisegnata**:
  - in alto quattro numeri: compiti da fare, verifiche della settimana, giorni alla prossima verifica, media generale;
  - nel riquadro «Adesso» un conto alla rovescia che scorre secondo per secondo e una barra a tacche (una ogni 5 minuti di lezione) al posto dell'anello;
  - l'orario ha il riassunto della giornata («5 ore · 1 supplenza · 1 annullata») e accanto a ogni ora se è fatta, quanto manca o cosa è cambiato;
  - barre di avanzamento per i compiti del giorno dopo e sotto ogni voto recente;
  - sul PC la scheda si divide in tre colonne.
- **Menu nuovo**: sul PC è una barra laterale con le icone; sul telefono una barra fissa in basso con tutte le sezioni, sempre a portata di pollice.
- **Scheda «Voti» ridisegnata**:
  - «Cosa fare adesso»: le materie sotto il 6, quelle in calo e le verifiche della settimana nelle materie in bilico, con il voto che serve e un collegamento al simulatore;
  - una scheda per materia al posto della tabella: media, mini-grafico degli ultimi voti, andamento, scritto/orale/pratico, minimo e massimo, quanto serve per il 6;
  - il simulatore diventa «Che voto mi serve?»: tocchi materia e voto e vedi subito come cambiano le medie; si possono ancora impilare più voti ipotetici;
  - grafici, elenco di tutti i voti e consigli completi restano, in sezioni che si aprono con un tocco.
- **Scheda «Agenda» ridisegnata**: un calendario del mese con un puntino colorato per ogni impegno (verifica, compito, variazione d'orario, promemoria; sul PC i nomi delle materie). Tocchi un giorno e accanto vedi cosa c'è, con i compiti da spuntare. Si può andare ai mesi successivi e tornare a oggi. Gli elenchi completi e il testo per Google Calendar restano, in sezioni che si aprono con un tocco.
- **Scheda «Compiti» ridisegnata**: la settimana come un planner. Sul PC una colonna per giorno con i compiti da spuntare («Libero 🎉» se non c'è niente); sul telefono una striscia di giorni da toccare, con i puntini per i compiti, e sotto l'elenco del giorno scelto. Le frecce cambiano settimana; la domenica compare solo se c'è qualcosa da consegnare. Restano la ricerca, «Nascondi i fatti», il PDF, gli scaduti, la mappa dell'andamento e l'elenco completo (in una sezione che si apre con un tocco).
- **Scheda «Orario» ridisegnata**: la settimana sta tutta nello schermo anche sul telefono, senza scorrere di lato (sigle delle materie sul telefono, nomi interi sul PC). Ogni materia ha il suo colore; oggi e l'ora in corso sono evidenziati, le ore passate sbiadite, le variazioni hanno un bordo e un puntino. Tocchi un'ora e sotto vedi aula, docente e cosa è cambiato. Le variazioni della settimana diventano schede «Cosa cambia» (accanto alla griglia sul PC). Restano la scelta della settimana e il PDF.
- **Scheda «Carico di lavoro» ridisegnata**: in alto quanto lavoro c'è questa settimana rispetto alla media; i prossimi 14 giorni a colpo d'occhio, con un pallino per ogni compito e verifica e in rosso i giorni pieni (tocchi un giorno e vedi cosa c'è, con i compiti da spuntare); i giorni pieni in arrivo con le materie e un consiglio; da quali materie o docenti arriva il lavoro. I grafici restano, in sezioni che si aprono con un tocco.
- **Scheda «Assenze» ridisegnata**: in cima quante ore puoi ancora perdere (anche in giorni di scuola), con una barra a tacche che diventa rossa dall'80% del limite e la previsione a fine anno al ritmo di adesso. Poi i numeri, le assenze e i ritardi da giustificare, gli ultimi eventi e le ore perse per materia. Il grafico per mese e la tabella completa restano, in sezioni che si aprono con un tocco.
- **Tolta la scheda «Studio»** (il piano di studio in 4 passi prima delle verifiche), con «Da studiare oggi» nella scheda Oggi e l'opzione nel testo per Google Calendar: il menu passa da 8 a 7 sezioni. Le verifiche restano in Oggi, Agenda e Voti.
- Tutti i temi vestono il nuovo disegno.
- **Guida.pdf rifatta** da capo per la 0.5: schede nuove, telefono, ClasseViva, temi. Si rigenera con `py strumenti/guida.py`.

## 0.2.1-beta

- **Linux e macOS**: nuovo `avvia.sh`. Su tutti e tre i sistemi lo script di avvio (`avvia.bat` su Windows) prepara da solo, al primo avvio, un ambiente Python nella cartella `.venv` con le librerie giuste: niente più `pip install` a mano, e su Debian e Ubuntu recenti non si scontra con il Python del sistema. Controlla anche che ci sia Python 3.12 o successivo.
- **Sincronizzazione col telefono**:
  - su Linux, dopo averla disattivata non si riusciva a riattivarla senza riavviare l'app;
  - su macOS «Attiva» restava bloccato per più di un minuto.
- I test automatici ora girano su Windows, Linux e macOS.

## 0.2.0-beta

- **ClasseViva, account con più studenti** (per esempio un genitore con due figli): dopo il primo «Aggiorna», nel profilo compare «Studente da mostrare» per scegliere quale figlio vedere. La scelta passa anche al telefono con la sincronizzazione. Da provare su account veri ([#6](https://github.com/Double-bited-Hamburger/parser-compiti/issues/6)).
- **Nuvola**: le date dei voti si calcolano sempre nell'ora italiana, anche se il computer o il telefono è impostato su un altro fuso orario (prima un voto di mezzanotte poteva finire al giorno prima).
- APK Android scaricabile direttamente dal README e dalle Release, con impronta SHA-256.

## 0.1.0-beta

Prima versione pubblica.

- Registri: Argo didUP, Nuvola e, sperimentale, **ClasseViva** (Spaggiari). Orario da WebUntis.
- Schede: oggi, agenda, compiti da spuntare, studio, orario con variazioni, voti con grafici e simulatore, carico di lavoro, assenze. PDF della settimana e dei compiti.
- Più profili, con la panoramica di tutti insieme.
- App Android con notifiche e widget, sincronizzata con il PC in Wi‑Fi.
- **100% locale**: rimossa la vecchia modalità «sito» online. Il programma gira solo sul PC o sul telefono.
- Sicurezza:
  - la pagina sul PC risponde solo con il gettone segreto dato all'avvio, così gli altri programmi non leggono dati né codice di abbinamento;
  - i messaggi della sincronizzazione valgono una volta sola e per 15 minuti;
  - al massimo due sincronizzazioni contemporanee;
  - portachiavi del sistema anche su Linux e macOS;
  - dipendenze con versioni fisse.
