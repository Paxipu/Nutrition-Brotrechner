"""Plattformabhängige Verzeichnisse.

Nutzerdaten liegen bewusst **nicht** neben dem Programm, sondern im dafür
vorgesehenen Verzeichnis des Betriebssystems. Das macht das Paket unter Linux,
Windows und macOS gleichermaßen installierbar und verhindert, dass ein Update
die eigene Zutatendatenbank überschreibt.

=========  =================================================================
System     Verzeichnis
=========  =================================================================
Windows    ``%APPDATA%\\Brotrechner``
macOS      ``~/Library/Application Support/Brotrechner``
Linux/BSD  ``$XDG_DATA_HOME/brotrechner`` bzw. ``~/.local/share/brotrechner``
=========  =================================================================

Zwei Auswege für Sonderfälle:

* Die Umgebungsvariable ``BROTRECHNER_DATA_DIR`` setzt das Verzeichnis
  unabhängig vom System (nützlich für Tests und für den Betrieb vom USB-Stick).
* Liegt neben dem Projektverzeichnis ein Ordner ``data``, wird dieser im
  *portablen Modus* verwendet.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Final

__all__ = [
    "DATA_DIR_ENV_VAR",
    "INGREDIENTS_FILE",
    "RECIPES_FILE",
    "SETTINGS_FILE",
    "backup_dir",
    "data_dir",
    "default_export_dir",
    "ingredients_path",
    "recipes_path",
    "settings_path",
]

DATA_DIR_ENV_VAR: Final = "BROTRECHNER_DATA_DIR"
APP_NAME: Final = "Brotrechner"
APP_NAME_POSIX: Final = "brotrechner"

INGREDIENTS_FILE: Final = "ingredients.json"
RECIPES_FILE: Final = "recipes.json"
SETTINGS_FILE: Final = "settings.json"


def _portable_dir() -> Path | None:
    """Ordner ``data`` neben dem Projektverzeichnis, falls vorhanden."""
    project_root = Path(__file__).resolve().parents[2]
    candidate = project_root / "data"
    return candidate if candidate.is_dir() else None


def data_dir(*, create: bool = True) -> Path:
    """Verzeichnis für Nutzerdaten.

    Args:
        create: Verzeichnis anlegen, falls es fehlt.

    Returns:
        Pfad zum Datenverzeichnis.
    """
    override = os.environ.get(DATA_DIR_ENV_VAR)
    if override:
        path = Path(override).expanduser()
    elif (portable := _portable_dir()) is not None:
        path = portable
    elif sys.platform == "win32":
        base = os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming"
        path = Path(base) / APP_NAME
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
        path = Path(base) / APP_NAME_POSIX

    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def ingredients_path() -> Path:
    """Pfad der Zutatendatenbank."""
    return data_dir() / INGREDIENTS_FILE


def recipes_path() -> Path:
    """Pfad der Rezeptdatenbank."""
    return data_dir() / RECIPES_FILE


def settings_path() -> Path:
    """Pfad der Programmeinstellungen."""
    return data_dir() / SETTINGS_FILE


def backup_dir(base: Path | None = None, *, create: bool = True) -> Path:
    """Verzeichnis für automatische Sicherungen.

    Args:
        base: Datenverzeichnis, zu dem die Sicherungen gehören. ``None``
            verwendet das Standardverzeichnis des Systems.
        create: Verzeichnis anlegen, falls es fehlt.
    """
    path = (base or data_dir()) / "backups"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def default_export_dir(*, create: bool = False) -> Path:
    """Standardordner für Etiketten, Berichte und CSV-Dateien.

    Bevorzugt wird ein Unterordner im Dokumentenverzeichnis, weil Anwender ihre
    Etiketten dort suchen. Existiert kein Dokumentenordner, fällt die Funktion
    auf ``<Datenverzeichnis>/exports`` zurück.
    """
    documents = Path.home() / "Documents"
    path = documents / APP_NAME if documents.is_dir() else data_dir() / "exports"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path
