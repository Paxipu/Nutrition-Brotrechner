"""Referenzmengen und Ampelbewertung.

Zwei Dinge, die im Vorgängerprogramm vermischt bzw. falsch zugeordnet waren,
sind hier sauber getrennt:

*Referenzmengen* stammen aus Anhang XIII Teil B der VO (EU) Nr. 1169/2011
("Referenzmenge für einen durchschnittlichen Erwachsenen, 8400 kJ / 2000 kcal").
Ballaststoffe sind dort **nicht** enthalten - der übliche Vergleichswert von
30 g/Tag ist eine Empfehlung der DGE und wird hier auch so gekennzeichnet.

Die *Ampel* ist keine EU-Vorgabe. Die verwendeten Schwellen sind die Kriterien
der britischen Front-of-Pack-Kennzeichnung (FSA/DHSC), die sich als informeller
Standard etabliert haben. Sie gelten je 100 g Lebensmittel.
"""

from __future__ import annotations

from enum import Enum
from typing import Final

__all__ = [
    "DGE_FIBER_REFERENCE_G",
    "REFERENCE_INTAKES",
    "TRAFFIC_LIGHT_THRESHOLDS",
    "AmpelLevel",
    "reference_intake_percent",
    "traffic_light",
]


class AmpelLevel(Enum):
    """Bewertungsstufe der Nährwert-Ampel."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    NONE = "none"
    """Für Nährstoffe, für die keine Ampel definiert ist."""

    @property
    def label(self) -> str:
        return {
            AmpelLevel.LOW: "niedrig",
            AmpelLevel.MEDIUM: "mittel",
            AmpelLevel.HIGH: "hoch",
            AmpelLevel.NONE: "",
        }[self]


#: Referenzmengen je Tag, Anhang XIII Teil B VO (EU) Nr. 1169/2011.
REFERENCE_INTAKES: Final[dict[str, float]] = {
    "energy_kcal": 2000.0,
    "fat": 70.0,
    "saturated_fat": 20.0,
    "carbs": 260.0,
    "sugar": 90.0,
    "protein": 50.0,
    "salt": 6.0,
}

#: Ballaststoff-Richtwert der DGE (keine EU-Referenzmenge).
DGE_FIBER_REFERENCE_G: Final = 30.0

#: Ampelschwellen je 100 g: (obere Grenze "niedrig", obere Grenze "mittel").
TRAFFIC_LIGHT_THRESHOLDS: Final[dict[str, tuple[float, float]]] = {
    "fat": (3.0, 17.5),
    "saturated_fat": (1.5, 5.0),
    "sugar": (5.0, 22.5),
    "salt": (0.3, 1.5),
}


def traffic_light(field: str, value_per_100g: float) -> AmpelLevel:
    """Ampelstufe eines Nährstoffs je 100 g.

    Args:
        field: Feldname, z. B. ``"salt"``.
        value_per_100g: Gehalt je 100 g.

    Returns:
        :attr:`AmpelLevel.NONE`, wenn für das Feld keine Schwellen definiert sind.
    """
    thresholds = TRAFFIC_LIGHT_THRESHOLDS.get(field)
    if thresholds is None:
        return AmpelLevel.NONE
    low, medium = thresholds
    if value_per_100g <= low:
        return AmpelLevel.LOW
    if value_per_100g <= medium:
        return AmpelLevel.MEDIUM
    return AmpelLevel.HIGH


def reference_intake_percent(field: str, amount: float) -> float | None:
    """Anteil an der Tagesreferenzmenge in Prozent.

    Args:
        field: Feldname aus :data:`REFERENCE_INTAKES` oder ``"fiber"``.
        amount: Absolute Menge in der Portion (g bzw. kcal).

    Returns:
        Prozentwert, oder ``None`` wenn für das Feld keine Referenzmenge
        existiert. Ballaststoffe werden gegen den DGE-Richtwert gerechnet.
    """
    if field == "fiber":
        return amount / DGE_FIBER_REFERENCE_G * 100.0
    reference = REFERENCE_INTAKES.get(field)
    if not reference:
        return None
    return amount / reference * 100.0
