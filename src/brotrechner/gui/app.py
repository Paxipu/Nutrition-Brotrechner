"""Start der Qt-Anwendung."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtCore import QLocale
from PySide6.QtWidgets import QApplication

from brotrechner import __version__

__all__ = ["create_app", "run"]

log = logging.getLogger(__name__)


def create_app(argv: list[str] | None = None) -> QApplication:
    """Erzeugt die Anwendung mit deutscher Zahlenformatierung.

    Die Locale wird ausdrücklich gesetzt, damit Eingabefelder Komma als
    Dezimaltrenner akzeptieren - unabhängig davon, wie das System eingestellt
    ist. Ein Rezept mit "1,5 g" darf nicht daran scheitern.
    """
    app = QApplication.instance()
    if isinstance(app, QApplication):
        return app

    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("Brotrechner")
    app.setApplicationDisplayName("Brotrechner")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("Brotrechner")
    # "Fusion" sieht auf allen Plattformen gleich aus und trägt das eigene
    # Stylesheet zuverlässig - native Stile ignorieren Teile davon.
    app.setStyle("Fusion")
    QLocale.setDefault(QLocale(QLocale.Language.German, QLocale.Country.Germany))
    return app


def run(argv: list[str] | None = None, *, data_dir: Path | None = None) -> int:
    """Startet die Oberfläche und gibt den Exit-Code zurück."""
    from brotrechner.gui.main_window import MainWindow  # noqa: PLC0415 - Qt erst nach QApplication

    app = create_app(argv)
    window = MainWindow(data_dir=data_dir)
    window.show()
    return app.exec()
