"""Start der Qt-Anwendung."""

from __future__ import annotations

import logging
import sys
import traceback
from importlib import resources
from pathlib import Path

from PySide6.QtCore import QLocale
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from brotrechner import __version__, paths
from brotrechner.gui.errors import install_exception_hook, show_error
from brotrechner.logfile import configure_logging

__all__ = ["application_icon", "create_app", "icon_path", "run"]

log = logging.getLogger(__name__)


def icon_path(suffix: str = "png") -> Path:
    """Pfad des mitgelieferten Programmsymbols.

    Args:
        suffix: ``"png"`` für Fenster und Taskleiste, ``"ico"`` für
            Windows-Verknüpfungen.
    """
    return Path(str(resources.files("brotrechner.gui") / "icons" / f"brotrechner.{suffix}"))


def application_icon() -> QIcon:
    """Programmsymbol; leer, falls die Ressource fehlt.

    Ein fehlendes Symbol ist ein Schönheitsfehler und darf den Start nicht
    verhindern - deshalb wird hier nichts ausgelöst.
    """
    path = icon_path()
    return QIcon(str(path)) if path.exists() else QIcon()


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
    app.setApplicationVersion(__version__)
    # Bewusst kein setApplicationDisplayName: Qt hängt diesen Namen an jeden
    # Fenstertitel an, wodurch in der Titelleiste "Brotrechner 5.0.0 -
    # Brotrechner" stünde.
    app.setOrganizationName("Brotrechner")
    # "Fusion" sieht auf allen Plattformen gleich aus und trägt das eigene
    # Stylesheet zuverlässig - native Stile ignorieren Teile davon.
    app.setStyle("Fusion")
    app.setWindowIcon(application_icon())
    QLocale.setDefault(QLocale(QLocale.Language.German, QLocale.Country.Germany))
    return app


def run(
    argv: list[str] | None = None, *, data_dir: Path | None = None, verbose: bool = False
) -> int:
    """Startet die Oberfläche und gibt den Exit-Code zurück.

    Vorher wird das Protokoll eingerichtet und jede unerwartete Ausnahme auf
    eine Meldung umgeleitet (:mod:`brotrechner.gui.errors`). Scheitert schon
    der Aufbau des Hauptfensters - etwa an einer beschädigten Einstellung -,
    erscheint eine Meldung statt eines Fensters, das sich wortlos schließt.
    """
    from brotrechner.gui.main_window import MainWindow  # noqa: PLC0415 - Qt erst nach QApplication

    log_file = configure_logging(_data_dir_or_none(data_dir), verbose=verbose)
    app = create_app(argv)
    install_exception_hook(log_file)
    log.info("Brotrechner %s startet", __version__)
    try:
        window = MainWindow(data_dir=data_dir)
    except Exception as exc:
        log.exception("Start fehlgeschlagen")
        show_error(
            "Der Brotrechner konnte nicht starten",
            f"{type(exc).__name__}: {exc}",
            details=traceback.format_exc(),
            log_file=log_file,
        )
        return 1
    window.show()
    return app.exec()


def _data_dir_or_none(data_dir: Path | None) -> Path | None:
    """Das Datenverzeichnis - oder ``None``, wenn es sich nicht anlegen lässt."""
    try:
        return data_dir or paths.data_dir()
    except OSError as exc:
        log.warning("Datenverzeichnis nicht verfügbar, Protokoll nur auf der Konsole: %s", exc)
        return None
