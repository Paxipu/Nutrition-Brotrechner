# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-Bauplan für das Windows-Programmpaket.

Baut zwei Programme in einen gemeinsamen Ordner ``dist/Brotrechner``:

* ``Brotrechner.exe`` - die Oberfläche, ohne Konsolenfenster;
* ``brotrechner-cli.exe`` - die Kommandozeile, etwa für ``selftest``.

Ein Ordner statt einer einzelnen Datei: Das Programm startet schneller, weil
nichts erst entpackt werden muss, und Virenscanner stoßen sich seltener daran.

Aufruf aus dem Projektverzeichnis, nach ``pip install ".[pdf]" pyinstaller``::

    pyinstaller packaging/brotrechner.spec --noconfirm
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

HERE = Path(SPECPATH)  # noqa: F821 - setzt PyInstaller
SOURCE = HERE.parent / "src"
ICON = SOURCE / "brotrechner" / "gui" / "icons" / "brotrechner.ico"

# Auch ohne Installation des Pakets auffindbar.
sys.path.insert(0, str(SOURCE))

#: Startdatenbank und Programmsymbol.
DATAS = collect_data_files("brotrechner")

#: Braucht das Programm nicht; ohne diese Module wird das Paket kleiner.
EXCLUDES = ["tkinter", "unittest", "pytest", "hypothesis", "IPython"]


def _analysis(script):
    return Analysis(  # noqa: F821 - setzt PyInstaller
        [str(HERE / script)],
        pathex=[str(SOURCE)],
        datas=DATAS,
        excludes=EXCLUDES,
    )


def _program(analysis, name, *, console):
    return EXE(  # noqa: F821 - setzt PyInstaller
        PYZ(analysis.pure),  # noqa: F821
        analysis.scripts,
        [],
        exclude_binaries=True,
        name=name,
        console=console,
        icon=str(ICON),
    )


gui = _analysis("brotrechner_gui.py")
cli = _analysis("brotrechner_cli.py")

COLLECT(  # noqa: F821 - setzt PyInstaller
    _program(gui, "Brotrechner", console=False),
    gui.binaries,
    gui.datas,
    _program(cli, "brotrechner-cli", console=True),
    cli.binaries,
    cli.datas,
    name="Brotrechner",
)
