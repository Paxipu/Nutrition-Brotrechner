"""Protokolldatei im Datenverzeichnis.

Beim Start per Doppelklick gibt es keine Konsole: Unter Windows läuft das
Programm mit ``pythonw``, und ``sys.stderr`` ist dort schlicht ``None``. Bisher
verschwand jede Warnung und jeder Fehler damit spurlos. Jetzt steht beides in
``brotrechner.log`` neben den Daten - wenige hundert Kilobyte, rotierend.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Final

__all__ = ["LOG_FILE", "configure_logging", "log_path"]

LOG_FILE: Final = "brotrechner.log"

#: Größe, ab der die Datei rotiert, und Zahl der aufbewahrten alten Dateien.
_MAX_BYTES: Final = 512_000
_BACKUP_COUNT: Final = 2

_FORMAT: Final = "%(asctime)s %(levelname)s %(name)s: %(message)s"

#: Kennzeichen der Handler, die dieses Modul anlegt - so ersetzt ein zweiter
#: Aufruf sie, statt jede Meldung doppelt zu schreiben.
_MARK: Final = "_brotrechner_handler"


def log_path(data_dir: Path) -> Path:
    """Pfad der Protokolldatei im Datenverzeichnis."""
    return data_dir / LOG_FILE


def configure_logging(data_dir: Path | None, *, verbose: bool = False) -> Path | None:
    """Schreibt das Protokoll in die Datei und, falls vorhanden, auf die Konsole.

    Args:
        data_dir: Datenverzeichnis; ``None`` schreibt nur auf die Konsole.
        verbose: Auch Einzelheiten der Fehlersuche protokollieren.

    Returns:
        Pfad der Protokolldatei - oder ``None``, wenn sie sich nicht anlegen
        ließ. Ein fehlendes Protokoll darf den Start nicht verhindern.
    """
    root = logging.getLogger()
    for handler in [h for h in root.handlers if getattr(h, _MARK, False)]:
        root.removeHandler(handler)
        handler.close()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    formatter = logging.Formatter(_FORMAT)

    if sys.stderr is not None:
        console = logging.StreamHandler(sys.stderr)
        console.setLevel(logging.DEBUG if verbose else logging.WARNING)
        console.setFormatter(formatter)
        _mark(console)
        root.addHandler(console)

    if data_dir is None:
        return None
    path = log_path(data_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            path, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
        )
    except OSError as exc:
        logging.getLogger(__name__).warning("Protokolldatei %s nicht nutzbar: %s", path, exc)
        return None
    handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    handler.setFormatter(formatter)
    _mark(handler)
    root.addHandler(handler)
    return path


def _mark(handler: logging.Handler) -> None:
    setattr(handler, _MARK, True)
