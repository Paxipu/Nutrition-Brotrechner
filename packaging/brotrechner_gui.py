"""Startdatei des Fensterprogramms im Windows-Paket (``Brotrechner.exe``).

PyInstaller baut daraus ein Programm ohne Konsolenfenster; siehe
``brotrechner.spec``.
"""

from __future__ import annotations

from brotrechner.cli import main_gui

if __name__ == "__main__":
    raise SystemExit(main_gui())
