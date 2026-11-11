"""L'APK contiene solo i moduli elencati in android/app/build.gradle.kts: se ne manca uno importato, l'app non parte."""

import ast
import re
import unittest
from pathlib import Path

RADICE = Path(__file__).parent.parent
GRADLE = RADICE / "android" / "app" / "build.gradle.kts"
# Il modulo che l'app Android importa per prima (android/app/src/main/python/avvio_android.py).
PARTENZA = ("config", "server")
# Facoltativi: config li importa solo se ci sono.
FACOLTATIVI = {"config_locale"}


def elenco_apk():
    testo = GRADLE.read_text(encoding="utf-8")
    blocco = re.search(r"val moduli = listOf\((.*?)\n\)", testo, re.S).group(1)
    return set(re.findall(r'"(\w+)"', blocco))


def importati(nome):
    """I moduli dell'app (file .py nella cartella principale) importati da nome.py, anche dentro le funzioni."""
    albero = ast.parse((RADICE / f"{nome}.py").read_text(encoding="utf-8"))
    nomi = set()
    for nodo in ast.walk(albero):
        if isinstance(nodo, ast.Import):
            nomi.update(a.name.split(".")[0] for a in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.module and not nodo.level:
            nomi.add(nodo.module.split(".")[0])
    return {n for n in nomi if (RADICE / f"{n}.py").exists()}


class ModuliApk(unittest.TestCase):
    def test_ogni_modulo_importato_e_nell_apk(self):
        apk = elenco_apk()
        da_vedere, visti = list(PARTENZA), set()
        while da_vedere:
            nome = da_vedere.pop()
            if nome in visti:
                continue
            visti.add(nome)
            da_vedere.extend(importati(nome) - FACOLTATIVI)
        mancanti = sorted(visti - apk)
        self.assertEqual(mancanti, [], f"Da aggiungere a «moduli» in {GRADLE.relative_to(RADICE)}: l'app Android non partirebbe")


if __name__ == "__main__":
    unittest.main()
