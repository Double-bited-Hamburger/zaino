"""Costruisce i pacchetti Linux di Zaino: .deb (Debian/Ubuntu) e .rpm (Fedora/openSUSE).

Uso: python strumenti/pacchetti_linux.py [cartella_di_destinazione]

Il pacchetto mette i sorgenti in /opt/zaino e un lanciatore in /usr/bin/zaino.
Il primo avvio crea l'ambiente Python dell'utente in ~/.local/share/zaino/venv:
non serve scrivere in /opt e l'app resta aggiornabile sostituendo il pacchetto.
Serve dpkg-deb per il .deb e rpmbuild per il .rpm (li installa la CI).
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import config  # noqa: E402

VERSIONE = config.VERSIONE
NOME = "zaino"
DEST = Path(sys.argv[1] if len(sys.argv) > 1 else "release").resolve()

FILE_SORGENTE = sorted(
    p for p in ROOT.glob("*.py") if not p.name.startswith("test_")
) + [ROOT / "requirements.txt", ROOT / "Guida.pdf", ROOT / "LICENSE", ROOT / "LICENZE-TERZE.md"]
FILE_WEB = sorted((ROOT / "web").rglob("*")) if (ROOT / "web").is_dir() else []

LANCIATORE = """#!/bin/sh
# Avvia Zaino. L'ambente Python vive nei dati dell'utente, non in /opt.
set -e
VENV="${XDG_DATA_HOME:-$HOME/.local/share}/zaino/venv"
APP=/opt/zaino
# Da sorgente DATI_DIR è vuoto: l'app scriverebbe in /opt/zaino (solo root). Dati e cache
# vanno invece nella cartella dell'utente, come per l'exe di Windows.
export DATI_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/zaino/dati"
mkdir -p "$DATI_DIR"
if ! command -v python3 >/dev/null 2>&1; then
    echo "Serve Python 3.12 o successivo." >&2; exit 1
fi
if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 12))'; then
    echo "Serve Python 3.12 o successivo, trovato: $(python3 --version 2>&1)" >&2; exit 1
fi
if [ ! -x "$VENV/bin/python" ]; then
    mkdir -p "$(dirname "$VENV")"
    python3 -m venv "$VENV"
fi
if ! cmp -s "$APP/requirements.txt" "$VENV/requisiti.txt"; then
    "$VENV/bin/python" -m pip install --disable-pip-version-check -r "$APP/requirements.txt"
    cp "$APP/requirements.txt" "$VENV/requisiti.txt"
fi
cd "$APP"
exec "$VENV/bin/python" main.py "$@"
"""

DESKTOP = """[Desktop Entry]
Type=Application
Name=Zaino
Comment=Registro elettronico e orario della classe
Exec=zaino
Icon=zaino
Terminal=false
Categories=Education;
StartupWMClass=zaino
"""


def albero(base: Path):
    """Crea la struttura dei file da pacchettizzare e la restituisce."""
    radice = base / "radice"
    app = radice / "opt/zaino"
    app.mkdir(parents=True)
    for src in FILE_SORGENTE + FILE_WEB:
        if src.is_file():
            dest = app / src.relative_to(ROOT)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
    for cartella in ("strumenti", "prove"):
        if (ROOT / cartella).is_dir():
            shutil.copytree(ROOT / cartella, app / cartella, dirs_exist_ok=True)
    binario = radice / "usr/bin/zaino"
    binario.parent.mkdir(parents=True)
    binario.write_text(LANCIATORE)
    binario.chmod(0o755)
    desktop = radice / "usr/share/applications/zaino.desktop"
    desktop.parent.mkdir(parents=True)
    desktop.write_text(DESKTOP)
    icona = radice / "usr/share/icons/hicolor/scalable/apps/zaino.svg"
    icona.parent.mkdir(parents=True)
    shutil.copy2(ROOT / ".github/logo.svg", icona)
    return radice


def deb(radice: Path):
    if not shutil.which("dpkg-deb"):
        print("dpkg-deb non trovato: .deb non costruito", file=sys.stderr)
        return None
    base = radice
    controllo = base / "DEBIAN"
    controllo.mkdir()
    (controllo / "control").write_text(
        f"Package: {NOME}\n"
        f"Version: {VERSIONE}\n"
        "Section: education\n"
        "Priority: optional\n"
        "Architecture: all\n"
        "Depends: python3 (>= 3.12), python3-venv\n"
        "Recommends: xdg-utils\n"
        "Maintainer: DesktopBuddy contributors <249748203+Double-bited-Hamburger@users.noreply.github.com>\n"
        "Homepage: https://github.com/Double-bited-Hamburger/zaino\n"
        "Description: Registro elettronico e orario della classe\n"
        " Zaino legge Argo, Nuvola, ClasseViva e WebUntis in un'unica app locale.\n"
    )
    out = DEST / f"zaino_{VERSIONE}_all.deb"
    subprocess.run(["dpkg-deb", "--build", str(base), str(out)], check=True)
    return out


def rpm(radice: Path):
    if not shutil.which("rpmbuild"):
        print("rpmbuild non trovato: .rpm non costruito", file=sys.stderr)
        return None
    base = radice.parent / "rpm"
    spec = base / "SPECS/zaino.spec"
    spec.parent.mkdir(parents=True)
    spec.write_text(
        "Name: zaino\n"
        f"Version: {VERSIONE}\n"
        "Release: 1\n"
        "Summary: Registro elettronico e orario della classe\n"
        "License: MIT\n"
        "BuildArch: noarch\n"
        "Requires: python3 >= 3.12, python3-pip\n"
        "Recommends: xdg-utils\n"
        "URL: https://github.com/Double-bited-Hamburger/zaino\n"
        "%description\n"
        "Zaino legge Argo, Nuvola, ClasseViva e WebUntis in un'unica app locale.\n"
        "%install\n"
        f"cp -a {radice}/opt {radice}/usr %{{buildroot}}/\n"
        "%files\n"
        "/opt/zaino\n"
        "/usr/bin/zaino\n"
        "/usr/share/applications/zaino.desktop\n"
        "/usr/share/icons/hicolor/scalable/apps/zaino.svg\n"
        "%post\n"
        "update-desktop-database /usr/share/applications >/dev/null 2>&1 || :\n"
        "gtk-update-icon-cache -qf /usr/share/icons/hicolor >/dev/null 2>&1 || :\n"
        "%postun\n"
        "update-desktop-database /usr/share/applications >/dev/null 2>&1 || :\n"
        "gtk-update-icon-cache -qf /usr/share/icons/hicolor >/dev/null 2>&1 || :\n"
    )
    subprocess.run(
        ["rpmbuild", "-bb", "--buildroot", str(base / "BUILD"), "--define", f"_topdir {base}",
         "--define", f"_rpmdir {DEST}",
         "--define", "_rpmfilename %%{NAME}-%%{VERSION}-%%{RELEASE}.%%{ARCH}.rpm", str(spec)],
        check=True,
    )
    # rpmbuild mette l'rpm in una sottocartella a seconda dei macro di sistema: lo riportiamo
    # nella destinazione con il nome fisso che aspettano la Release e il README.
    trovati = list(DEST.rglob(f"zaino-{VERSIONE}-1.noarch.rpm"))
    if not trovati:
        print("rpmbuild non ha prodotto l'rpm previsto", file=sys.stderr)
        return None
    out = DEST / f"zaino-{VERSIONE}-1.noarch.rpm"
    if trovati[0] != out:
        shutil.move(str(trovati[0]), str(out))
    return out


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        radice = albero(Path(tmp))
        fatti = [p for p in (deb(radice), rpm(radice)) if p]
    for p in fatti:
        print(p)


if __name__ == "__main__":
    main()
