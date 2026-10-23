# App Android e sincronizzazione con il PC

L'app Android è la stessa app del PC: dentro c'è lo stesso codice Python (incorporato con Chaquopy) e la stessa pagina. Funziona da sola, anche fuori casa: scarica dai registri con le credenziali del profilo.

## Scaricare l'APK già pronto
1. Dal telefono apri **[zaino-0.5.1.apk](https://github.com/Double-bited-Hamburger/zaino/releases/download/0.5.1/zaino-0.5.1.apk)** (o scegli una versione nelle [Release](../../releases)).
2. Apri il file scaricato; Android chiede di consentire l'installazione dal browser: consentila.
3. Fatto. Per aggiornare, scarica il nuovo APK e installalo sopra: i dati restano.

Non serve costruire nulla: le istruzioni qui sotto servono solo a chi vuole farselo da sé.

## Costruire l'APK
Serve una volta sola avere installato Android Studio (porta con sé l'SDK Android e il Java giusto) e un Python 3.12.

1. In `android/local.properties` indica dove sono SDK e Python 3.12 (usa le barre `/`, anche su Windows):
   ```
   sdk.dir=C:/Users/<utente>/AppData/Local/Android/Sdk
   python.build=C:/percorso/di/python3.12/python.exe
   ```
2. Doppio clic su `android\costruisci.bat`. La prima volta scarica i componenti e ci mette qualche minuto.
3. L'APK è in `output\zaino.apk`.

Dopo ogni modifica al codice Python o alla pagina basta rilanciare `costruisci.bat` e reinstallare: i dati sul telefono restano.

**Firma.** Senza altro l'APK è firmato con la chiave di debug di Android Studio. Per firmarlo con una chiave tua crea `android/keystore.properties`:
```
storeFile=registro.jks
storePassword=...
keyAlias=...
keyPassword=...
```
(la chiave si crea con `keytool -genkeypair -keystore android/registro.jks -alias registro -keyalg RSA -validity 10000`). Chiave e password sono file solo tuoi, esclusi dal repository: **non pubblicarli mai** e conservane una copia, perché un APK firmato con un'altra chiave non si installa sopra quello vecchio (andrebbe disinstallata l'app, perdendo i dati del telefono, che però tornano dal PC con la sincronizzazione). È anche la protezione contro gli APK contraffatti: Android rifiuta un aggiornamento firmato da qualcun altro.

**APK già pronto.** Chi non vuole costruirlo lo trova nelle [Release](../../releases) del progetto, con la sua impronta SHA-256 per controllare che sia quello originale. Non installare APK di questa app presi da altre parti.

**Su GitHub.** L'APK delle Release lo costruisce GitHub da solo (`.github/workflows/apk.yml`): quando si pubblica una Release, firma l'app con la chiave del progetto e allega `zaino-<versione>.apk` con la sua impronta. La chiave sta nei Secrets del repository (`ANDROID_KEYSTORE`, il file `.jks` in base64, e `ANDROID_KEYSTORE_PASSWORD`). Dalla 0.5.0 la chiave è nuova (impronta SHA-256 del certificato `B2:A3:20:83:39:D4:82:A2:76:29:71:50:2E:F1:7F:40:A3:9E:65:E5:B0:5B:0B:C0:56:9E:41:75:66:8E:5C:AB`): chi ha la 0.2 deve disinstallarla una volta prima di installare la 0.5 (i dati tornano dal PC con la sincronizzazione).

## Installare sul telefono
- **Con il cavo**: attiva «Debug USB» nelle Opzioni sviluppatore, collega il telefono e lancia
  `%LOCALAPPDATA%\Android\Sdk\platform-tools\adb install -r output\zaino.apk`
- **Senza cavo**: copia `output\zaino.apk` sul telefono (anche da Telegram o Drive), aprilo e consenti l'installazione da quella app.

Serve Android 7 o successivo, su un telefono a 64 bit (tutti quelli degli ultimi anni).

## Notifiche e widget
- **Notifiche**: al primo avvio l'app chiede il permesso. Ogni due ore circa (dalle 7 alle 22, con la rete) riscarica i registri di tutti i profili e avvisa di nuovi voti, verifiche, compiti e cambi d'orario; nel tardo pomeriggio ricorda i compiti per domani non ancora spuntati. Il primo controllo prende solo nota di cosa c'è già, senza avvisare. I due tipi di avviso si accendono e spengono da Impostazioni → App → Zaino → Notifiche.
- **Widget** (in stile Nothing, chiari o scuri come il telefono): tieni premuto sulla schermata home → Widget → Zaino. «Compiti» (4×2) mostra quanti compiti restano per il prossimo giorno di scuola; «Prossima verifica» (2×2) i giorni che mancano, in rosso all'ultimo; «Adesso» (4×1) la lezione in corso con il conto alla rovescia alla campanella (dopo l'ultima ora, la prima di domani). Usano l'ultimo profilo aperto e si aggiornano col controllo periodico e ogni volta che esci dall'app. Seguono il tema scelto nell'app: col tema «Ultra» diventano la lattina bianca (rose e alloro, graffi argentati, numeri neri), con gli altri temi restano in stile Nothing. Le forme del tema Ultra si rigenerano con `py strumenti/forme_ultra.py web android/app/src/main/res/drawable`.

## Sincronizzare PC e telefono
1. **PC**: apri l'app → «Profili» → riquadro «Sincronizzazione con il telefono» → «Attiva». Compare un codice di 20 caratteri. Se Windows chiede se consentire Python sulla rete, accetta per le **reti private**.
2. **Telefono**: apri l'app → nel riquadro «Sincronizzazione con il PC» scrivi il codice → «Abbina e sincronizza». Arrivano profili, password dei registri, dati scaricati e compiti spuntati.

Da lì in poi il telefono si allinea da solo quando è sullo stesso Wi‑Fi del PC **e l'app del PC è aperta**: all'apertura, dopo «Aggiorna» e dopo aver spuntato un compito. Se il PC non c'è, l'app funziona lo stesso e sincronizza alla prossima occasione. C'è anche il pulsante «Sincronizza ora» nella schermata «Profili».

Come vengono unite le due copie:
- profili: vale l'ultima modifica; un profilo eliminato da una parte viene eliminato anche dall'altra;
- compiti spuntati: per ogni compito vale l'ultima azione (messa o tolta la spunta);
- dati del registro e orario: vale il download più recente (per Nuvola i giorni già letti si sommano).

### Se il telefono non trova il PC
- Controlla che l'app del PC sia aperta e che sul PC la sincronizzazione risulti attiva.
- Telefono e PC devono essere sulla stessa rete, non sulla rete «ospiti» del router (che isola i dispositivi tra loro).
- Il firewall di Windows deve consentire Python sulle reti private (porta 8766, TCP e UDP). Se la rete di casa è impostata come «pubblica», Windows blocca tutto: cambiala in «privata» dalle impostazioni di rete.
- In ultima istanza: sul telefono «Scollega», poi abbina di nuovo scrivendo anche l'indirizzo del PC mostrato nel riquadro del PC (es. `192.168.1.20`).

### Sicurezza
- In rete locale passa solo testo cifrato con una chiave ricavata dal codice di abbinamento; niente passa da Internet.
- Ogni messaggio vale una volta sola e per 15 minuti: chi lo registra in rete non può rimandarlo più tardi. Per questo PC e telefono devono avere data e ora giuste (ora automatica).
- Il PC accetta al massimo due scambi alla volta, così nessuno sulla stessa rete può intasarlo di richieste.
- Chi conosce il codice ed è collegato alla tua rete può leggere i dati (password dei registri comprese): non condividerlo. «Disattiva» sul PC lo butta via; alla riattivazione ne nasce uno nuovo.
- Sul telefono le password dei registri sono salvate cifrate, con una chiave custodita dall'Android Keystore, e l'app è esclusa dai backup.
- Senza sincronizzazione attiva il PC non ascolta nessuno sulla rete, come prima.
- A decidere quale modifica è la più recente sono gli orologi dei due dispositivi: tienili sull'ora automatica.
