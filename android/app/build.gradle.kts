import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

fun proprieta(nome: String) = Properties().apply {
    rootProject.file(nome).takeIf { it.exists() }?.inputStream()?.use { load(it) }
}

val locali = proprieta("local.properties")
val firma = proprieta("keystore.properties")

// L'app è la stessa del PC: il codice Python e la pagina si prendono dalla cartella sopra, senza copiarli a mano.
// L'elenco è esplicito perché lì accanto ci sono anche .env e profili/, che nell'APK non devono mai finire.
val radice = rootProject.projectDir.parentFile
val moduli = listOf(
    // config_locale (impostazioni personali) entra nell'APK solo se esiste: non metterlo negli APK da pubblicare.
    "archivio", "argo_client", "classeviva_adatta", "classeviva_client", "config", "config_locale", "dati", "notifiche", "nuvola_adatta", "nuvola_client",
    "orario", "parser", "pdf_compiti", "pdf_settimana", "profili", "server", "sincronizza", "stats", "untis_client",
)

val copiaPython by tasks.registering(Sync::class) {
    from(radice) { include(moduli.map { "$it.py" }) }
    into(layout.buildDirectory.dir("python-app"))
}
val copiaWeb by tasks.registering(Sync::class) {
    from(radice.resolve("web"))
    into(layout.buildDirectory.dir("assets-app/web"))
}

android {
    namespace = "it.registro.app"
    compileSdk = 35
    buildToolsVersion = "36.0.0"

    defaultConfig {
        applicationId = "it.registro.app"
        minSdk = 24
        targetSdk = 35
        versionCode = 8
        versionName = "0.6.0"
        ndk { abiFilters += "arm64-v8a" }
    }

    signingConfigs {
        if (firma.getProperty("storeFile") != null) {
            create("release") {
                storeFile = rootProject.file(firma.getProperty("storeFile"))
                storePassword = firma.getProperty("storePassword")
                keyAlias = firma.getProperty("keyAlias")
                keyPassword = firma.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            // Senza keystore.properties si firma con la chiave di debug: l'APK si installa lo stesso.
            signingConfig = signingConfigs.findByName("release") ?: signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }

    sourceSets["main"].assets.srcDir(layout.buildDirectory.dir("assets-app"))
}

chaquopy {
    defaultConfig {
        version = "3.12"
        // Serve un Python 3.12 sul PC per preparare i pacchetti: il suo percorso sta in local.properties (python.build=...).
        locali.getProperty("python.build")?.let { buildPython(it) }
        // Versioni fisse: le stesse provate sul telefono (cryptography è quella compilata da Chaquopy per Android).
        pip {
            install("requests==2.34.2")
            install("python-dotenv==1.2.4")
            install("reportlab==5.0.1")
            install("cryptography==42.0.8")
        }
    }
    sourceSets {
        getByName("main") { srcDir(layout.buildDirectory.dir("python-app")) }
    }
}

// Le due copie si fanno all'inizio di ogni build, prima di qualunque passo che le legga.
tasks.named("preBuild") { dependsOn(copiaPython, copiaWeb) }
tasks.configureEach { if (name !in setOf("copiaPython", "copiaWeb", "clean")) mustRunAfter(copiaPython, copiaWeb) }

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.work:work-runtime-ktx:2.9.1") // controllo periodico per notifiche e widget
}
