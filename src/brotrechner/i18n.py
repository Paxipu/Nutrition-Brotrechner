"""Deutsche Beschriftungen und Zahlenformatierung.

Alle anzeigbaren Texte für Fachbegriffe stehen hier zentral, damit Oberfläche,
PDF-Bericht, CSV und Kommandozeile dieselben Bezeichnungen verwenden. Die
Programmlogik nutzt durchgehend englische Feldnamen; erst hier werden sie
übersetzt.
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "NUTRIENT_LABELS",
    "NUTRIENT_ORDER",
    "NUTRIENT_UNITS",
    "format_currency",
    "format_number",
    "parse_number",
]

#: Reihenfolge der Nährstoffe wie in Anhang XV der VO (EU) Nr. 1169/2011.
NUTRIENT_ORDER: Final[tuple[str, ...]] = (
    "energy_kcal",
    "fat",
    "saturated_fat",
    "carbs",
    "sugar",
    "fiber",
    "protein",
    "salt",
)

NUTRIENT_LABELS: Final[dict[str, str]] = {
    "energy_kcal": "Energie",
    "fat": "Fett",
    "saturated_fat": "davon gesättigte Fettsäuren",
    "carbs": "Kohlenhydrate",
    "sugar": "davon Zucker",
    "protein": "Eiweiß",
    "salt": "Salz",
    "fiber": "Ballaststoffe",
    "water": "Wassergehalt",
}

NUTRIENT_UNITS: Final[dict[str, str]] = {
    "energy_kcal": "kcal",
    "fat": "g",
    "saturated_fat": "g",
    "carbs": "g",
    "sugar": "g",
    "protein": "g",
    "salt": "g",
    "fiber": "g",
    "water": "%",
}

#: Nachkommastellen je Nährstoff in der Anzeige.
NUTRIENT_DECIMALS: Final[dict[str, int]] = {
    "energy_kcal": 0,
    "salt": 2,
}


def decimals_for(field: str) -> int:
    """Übliche Nachkommastellen eines Nährstoffs."""
    return NUTRIENT_DECIMALS.get(field, 1)


def format_number(value: float, decimals: int = 1) -> str:
    """Formatiert eine Zahl mit deutschem Dezimalkomma.

    Examples:
        >>> format_number(1234.5)
        '1234,5'
        >>> format_number(0.005, 2)
        '0,01'
    """
    return f"{value:.{decimals}f}".replace(".", ",")


def format_currency(value: float, decimals: int = 2) -> str:
    """Formatiert einen Eurobetrag mit Komma und Währungszeichen."""
    return f"{format_number(value, decimals)} €"


def parse_number(text: str) -> float:
    """Liest eine Zahl mit Komma *oder* Punkt als Dezimaltrenner.

    Tausenderpunkte werden nicht unterstützt - in einem Eingabefeld für
    Grammangaben wären sie mehrdeutig.

    Args:
        text: Eingabetext, Leerzeichen werden ignoriert.

    Returns:
        Der Zahlenwert; leerer Text ergibt ``0.0``.

    Raises:
        ValueError: Wenn der Text keine Zahl ist.
    """
    cleaned = text.strip().replace(" ", "").replace(" ", "")
    if not cleaned:
        return 0.0
    return float(cleaned.replace(",", "."))
