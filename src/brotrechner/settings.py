"""Programmeinstellungen als kleine JSON-Datei.

Bewusst kein ``QSettings``: Die Einstellungen sollen im selben Verzeichnis
liegen wie die Daten, damit sich das ganze Programm samt Zustand kopieren
lässt - und damit sie unter Linux nicht in der Registry-Nachbildung
verschwinden.
"""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final

from brotrechner.core.analysis import DEFAULT_ENERGY_PRICE_EUR_PER_KWH

__all__ = ["THEMES", "Settings", "load_settings", "save_settings"]

log = logging.getLogger(__name__)

#: Gültige Farbmodi - dieselben Werte wie ``ThemeMode`` der Oberfläche, die
#: hier nicht importiert wird, damit Einstellungen ohne Qt lesbar bleiben.
THEMES: Final = ("system", "light", "dark")

#: Spanne des Strompreises in Euro je kWh - dieselbe wie im Rechner.
_ENERGY_PRICE_RANGE: Final = (0.0, 10.0)


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
        """Liest Einstellungen; Unbekanntes wird ignoriert, Ungültiges ersetzt.

        Die Datei lässt sich von Hand bearbeiten, und ein Tippfehler darf den
        Start nicht verhindern. Früher wurde jeder Wert ungeprüft übernommen -
        ``"theme": "blau"`` ließ das Programm beim Start abstürzen. Jetzt gilt
        für einen ungültigen Wert die Vorgabe, und das Protokoll nennt ihn.
        """
        values: dict[str, Any] = {}
        for name, value in data.items():
            check = _CHECKS.get(name)
            if check is None:
                continue
            cleaned = check(value)
            if cleaned is None:
                log.warning("Einstellung %s=%r ist ungültig - es gilt die Vorgabe", name, value)
                continue
            values[name] = cleaned
        return cls(**values)


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _flag(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _theme(value: object) -> str | None:
    return value if isinstance(value, str) and value in THEMES else None


def _energy_price(value: object) -> float | None:
    # bool ist in Python eine Zahl - "true" als Preis ist trotzdem ein Fehler.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    low, high = _ENERGY_PRICE_RANGE
    number = float(value)
    return number if math.isfinite(number) and low <= number <= high else None


#: Prüfung je Einstellung: liefert den bereinigten Wert oder ``None``.
_CHECKS: Final[dict[str, Callable[[object], Any]]] = {
    "theme": _theme,
    "energy_price": _energy_price,
    "export_dir": _text,
    "window_geometry": _text,
    "show_tolerances": _flag,
    "last_label_theme": _text,
    "last_label_size": _text,
}


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
