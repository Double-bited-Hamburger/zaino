"""Costruisce zaino.exe per Windows con PyInstaller: un file solo, con Python, librerie e pagina dentro.

    py -m pip install -r requirements.txt pyinstaller
    py strumenti/costruisci_exe.py

Il risultato è in dist/zaino.exe, con accanto dist/zaino.exe.sha256 (l'impronta che controlla l'aggiornamento).
Di solito lo costruisce GitHub quando si pubblica una Release (.github/workflows/exe.yml).
"""

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

RADICE = Path(__file__).resolve().parent.parent
LAVORO = RADICE / "build" / "exe"
DIST = RADICE / "dist"


def icona(file):
    """L'icona dell'app Android (.github/logo.svg): un foglio del registro con tre righe, la prima spuntata."""
    lato = 1024
    s = lato / 108  # il disegno originale è 108×108
    blu, bianco = (42, 120, 214, 255), (255, 255, 255, 255)
    img = Image.new("RGBA", (lato, lato), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, lato - 1, lato - 1), radius=26 * s, fill=blu)
    d.rounded_rectangle((32 * s, 30 * s, 76 * s, 78 * s), radius=5 * s, fill=bianco)
    spessore = round(4 * s)
    for tratto in ([(40, 43), (44, 47), (51, 39)], [(57, 43), (69, 43)], [(41, 56), (69, 56)], [(41, 67), (61, 67)]):
        punti = [(x * s, y * s) for x, y in tratto]
        d.line(punti, fill=blu, width=spessore, joint="curve")
        for x, y in (punti[0], punti[-1]):  # estremi arrotondati
            d.ellipse((x - spessore / 2, y - spessore / 2, x + spessore / 2, y + spessore / 2), fill=blu)
    img.save(file, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def main():
    if (RADICE / "config_locale.py").exists():
        sys.exit("C'è config_locale.py (impostazioni personali): spostalo prima di costruire un exe da pubblicare.")
    shutil.rmtree(LAVORO, ignore_errors=True)
    LAVORO.mkdir(parents=True)
    icona(LAVORO / "zaino.ico")
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--console",
        "--name", "zaino", "--icon", str(LAVORO / "zaino.ico"),
        "--add-data", f"{RADICE / 'web'}{';' if sys.platform == 'win32' else ':'}web",
        "--workpath", str(LAVORO), "--specpath", str(LAVORO), "--distpath", str(DIST),
        str(RADICE / "main.py"),
    ], check=True, cwd=RADICE)
    exe = DIST / "zaino.exe"
    impronta = hashlib.sha256(exe.read_bytes()).hexdigest()
    # A capo Unix anche su Windows: con \r\n sha256sum -c cercherebbe un file «zaino.exe\r».
    (DIST / "zaino.exe.sha256").write_text(f"{impronta}  zaino.exe\n", encoding="utf-8", newline="\n")
    print(f"{exe} ({exe.stat().st_size // 1024 // 1024} MB), SHA-256 {impronta}")


if __name__ == "__main__":
    main()
