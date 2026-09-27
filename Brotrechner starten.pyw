#!/usr/bin/env python3
"""Startet den Brotrechner per Doppelklick, ohne Installation.

Die Endung ``.pyw`` ist unter Windows mit ``pythonw.exe`` verknüpft: Das
Programm startet damit ohne schwarzes Konsolenfenster im Hintergrund. Unter
Linux und macOS erfüllt ``python3 "Brotrechner starten.pyw"`` denselben Zweck,
dort ist die Endung aber ohne Bedeutung.

Diese Datei ist bewusst so gebaut, dass sie **ohne** ``pip install`` auskommt:
Sie legt das Verzeichnis ``src`` in den Suchpfad und ruft dann die Oberfläche
auf. Wer das Paket regulär installiert hat, kann stattdessen einfach
``brotrechner`` aufrufen.

Fehlt eine Voraussetzung, erscheint eine verständliche Meldung statt eines
Fensters, das sich wortlos wieder schließt - der schlimmste Fall bei einem
Programm, das per Doppelklick gestartet wird.
"""

from __future__ import annotations

import sys
from pathlib import Path

#: Wurzel des Projektverzeichnisses; diese Datei liegt direkt darin.
ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "src"

#: Mindestens erforderliche Python-Fassung, wie in pyproject.toml deklariert.
MINIMUM_PYTHON = (3, 10)


def _report(title: str, message: str) -> None:
    """Zeigt eine Fehlermeldung - als Fenster, sonst auf der Konsole.

    Beim Start per Doppelklick gibt es keine Konsole, auf der man etwas lesen
    könnte. Deshalb wird zuerst ein Fenster versucht; erst wenn selbst das
    scheitert, bleibt die Textausgabe.
    """
    text = f"{title}\n\n{message}"
    try:
        import tkinter
        from tkinter import messagebox

        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()
    except Exception:
        # Hier zählt nur, dass die Meldung irgendwie ankommt.
        pass
    else:
        return
    print(text, file=sys.stderr)


def main() -> int:
    """Prüft die Voraussetzungen und startet die Oberfläche."""
    if sys.version_info < MINIMUM_PYTHON:
        _report(
            "Python ist zu alt",
            f"Der Brotrechner benötigt mindestens Python "
            f"{MINIMUM_PYTHON[0]}.{MINIMUM_PYTHON[1]}.\n"
            f"Gefunden wurde {sys.version.split()[0]} unter:\n{sys.executable}",
        )
        return 1

    if not SOURCE.is_dir():
        _report(
            "Programmdateien nicht gefunden",
            f"Im Ordner\n{ROOT}\nfehlt das Verzeichnis 'src'.\n\n"
            "Diese Startdatei muss im Hauptordner des Projekts liegen. "
            "Eine Verknüpfung auf dem Schreibtisch ist in Ordnung, "
            "die Datei selbst darf aber nicht verschoben werden.",
        )
        return 1

    # Nur einhängen, wenn das Paket nicht ohnehin schon installiert ist.
    if str(SOURCE) not in sys.path:
        sys.path.insert(0, str(SOURCE))

    try:
        from brotrechner.gui.app import run
    except ImportError as exc:
        missing = getattr(exc, "name", "") or str(exc)
        hint = (
            "pip install PySide6 Pillow"
            if missing.split(".")[0] in {"PySide6", "PIL", "shiboken6"}
            else "pip install -e ."
        )
        _report(
            "Ein benötigtes Paket fehlt",
            f"Nicht gefunden: {missing}\n\n"
            f"Zum Nachinstallieren in der Eingabeaufforderung:\n\n    {hint}\n\n"
            f"Verwendetes Python:\n{sys.executable}",
        )
        return 1

    # Die Oberfläche fängt ihre Fehler selbst ab und zeigt sie an. Was davor
    # oder danach scheitert - etwa schon das Anlegen des Fensters durch Qt -,
    # soll trotzdem nicht in einem Programm enden, das sich wortlos schließt.
    try:
        return run()
    except Exception as exc:
        _report(
            "Der Brotrechner wurde unerwartet beendet",
            f"{type(exc).__name__}: {exc}\n\n"
            "Einzelheiten stehen - sofern sie sich schreiben ließen - in der Datei "
            "brotrechner.log im Datenverzeichnis.",
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
