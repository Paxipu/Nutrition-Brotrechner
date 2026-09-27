"""Unerwartete Fehler sichtbar machen, statt sie zu verschlucken.

Eine Ausnahme in einem Qt-Slot beendet das Programm nicht: PySide gibt sie an
``sys.excepthook`` weiter, der sie auf die Konsole schreibt - und die gibt es
beim Start per Doppelklick nicht. Für den Anwender passierte dann schlicht
nichts: Ein Knopf reagierte nicht, ein Dialog blieb leer. Jetzt erscheint eine
Meldung, und der vollständige Hergang steht im Protokoll.
"""

from __future__ import annotations

import logging
import sys
import traceback
from collections.abc import Callable
from pathlib import Path
from types import TracebackType

from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

__all__ = ["install_exception_hook", "show_error"]

log = logging.getLogger(__name__)

_Hook = Callable[[type[BaseException], BaseException, TracebackType | None], object]


def show_error(
    title: str,
    message: str,
    *,
    details: str = "",
    log_file: Path | None = None,
    parent: QWidget | None = None,
) -> None:
    """Zeigt eine Fehlermeldung mit ausklappbaren Einzelheiten.

    Args:
        title: Fenstertitel.
        message: Was passiert ist, in einem Satz.
        details: Technischer Hergang, etwa der Traceback - nur auf Wunsch sichtbar.
        log_file: Protokolldatei, auf die die Meldung verweist.
        parent: Übergeordnetes Fenster; ``None`` nimmt das aktive.
    """
    text = message
    if log_file is not None:
        text += f"\n\nDer vollständige Hergang steht im Protokoll:\n{log_file}"
    box = QMessageBox(
        QMessageBox.Icon.Critical,
        title,
        text,
        QMessageBox.StandardButton.Ok,
        parent or QApplication.activeWindow(),
    )
    if details:
        box.setDetailedText(details)
    box.exec()


def install_exception_hook(log_file: Path | None) -> _Hook:
    """Ersetzt ``sys.excepthook`` durch Protokoll und Meldung.

    Returns:
        Den bisherigen Hook - für Tests und zum Zurücksetzen.
    """
    previous: _Hook = sys.excepthook
    showing = False

    def hook(exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None) -> None:
        nonlocal showing
        if issubclass(exc_type, KeyboardInterrupt):
            previous(exc_type, exc, tb)
            return
        log.critical("Unerwarteter Fehler", exc_info=(exc_type, exc, tb))
        # Scheitert während der Meldung noch etwas, bleibt es beim Protokoll -
        # sonst stapelten sich die Fenster.
        if showing:
            return
        showing = True
        try:
            show_error(
                "Unerwarteter Fehler",
                "Die letzte Aktion wurde wegen eines Programmfehlers abgebrochen:\n\n"
                f"{exc_type.__name__}: {exc}",
                details="".join(traceback.format_exception(exc_type, exc, tb)),
                log_file=log_file,
            )
        except Exception:
            # Ohne Fenster bleibt nur der bisherige Weg; Hauptsache, der Fehler
            # geht nicht verloren.
            log.exception("Fehlermeldung ließ sich nicht anzeigen")
            previous(exc_type, exc, tb)
        finally:
            showing = False

    sys.excepthook = hook
    return previous
