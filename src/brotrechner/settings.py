"""Programmeinstellungen als kleine JSON-Datei.

Bewusst kein ``QSettings``: Die Einstellungen sollen im selben Verzeichnis
liegen wie die Daten, damit sich das ganze Programm samt Zustand kopieren
lässt - und damit sie unter Linux nicht in der Registry-Nachbildung
verschwinden.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from brotrechner.core.analysis import DEFAULT_ENERGY_PRICE_EUR_PER_KWH

__all__ = ["Settings", "load_settings", "save_settings"]

log = logging.getLogger(__name__)


@dataclass(slots=True)
class Settings:
    """Alles, was sich das Programm zwischen zwei Starts merkt."""

    theme: str = "system"
    """Farbmodus: ``system``, ``light`` oder ``dark``."""

    energy_price: float = DEFAULT_ENERGY_PRICE_EUR_PER_KWH
    export_dir: str = ""
    """Leer bedeutet: Standardordner verwenden."""
    window_geometry: str = ""
    """Fenstergeometrie als Base64-Zeichenkette von ``QWidget.saveGeometry``."""
    show_tolerances: bool = True
    last_label_theme: str = "natural"
    last_label_size: str = "medium"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Settings:
        """Liest Einstellungen; unbekannte Schlüssel werden ignoriert."""
        known = set(cls.__slots__)
        return cls(**{k: v for k, v in data.items() if k in known})


def load_settings(path: Path) -> Settings:
    """Lädt die Einstellungen.

    Ein Fehler beim Lesen ist nie kritisch - dann gelten die Vorgaben, und das
    Programm startet trotzdem.
    """
    if not path.exists():
        return Settings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return Settings.from_dict(data)
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        log.warning("Einstellungen aus %s nicht lesbar (%s), Vorgaben werden verwendet", path, exc)
    return Settings()


def save_settings(path: Path, settings: Settings) -> None:
    """Speichert die Einstellungen; Fehler werden nur protokolliert."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(settings), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except OSError as exc:  # pragma: no cover - Schreibfehler auf dem Zielsystem
        log.warning("Einstellungen konnten nicht gespeichert werden: %s", exc)
