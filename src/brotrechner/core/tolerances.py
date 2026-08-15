"""Deklarationstoleranzen nach EU-Recht.

Quelle: Europäische Kommission, *Guidance document for competent authorities
for the control of compliance with EU legislation on ... the setting of
tolerances for nutrient values declared on a label*, Dezember 2012, Tabelle 1
("tolerances for foods other than food supplements including measurement
uncertainty").

Tabelle 1 im Wortlaut:

==========================================  ===========================================
Nährstoff                                   Toleranz
==========================================  ===========================================
Kohlenhydrate, Zucker, Eiweiß, Ballaststoffe  < 10 g/100 g: ±2 g
                                            10-40 g/100 g: ±20 %
                                            > 40 g/100 g: ±8 g
Fett                                        < 10 g/100 g: ±1,5 g
                                            10-40 g/100 g: ±20 %
                                            > 40 g/100 g: ±8 g
Gesättigte Fettsäuren                       < 4 g/100 g: ±0,8 g
                                            >= 4 g/100 g: ±20 %
Salz                                        < 1,25 g/100 g: ±0,375 g
                                            >= 1,25 g/100 g: ±20 %
==========================================  ===========================================

Für den **Brennwert ist keine eigene Toleranz definiert**. Er wird nach
Anhang XIV der VO (EU) Nr. 1169/2011 aus den Nährstoffen berechnet, weshalb
sich seine Bandbreite hier konsequent aus den Nährstoffbandbreiten ergibt und
nicht frei geschätzt wird.

.. note::
   Die Vorgängerversion des Programms verwendete abweichende Werte
   (±1,5 g für Kohlenhydrate unter 10 g, ±25 % oberhalb 40 g, ±20 % pauschal
   für Salz und einen frei gewählten Brennwert-Korridor von ±20 %). Diese
   Werte lassen sich in der Guidance nicht belegen und wurden korrigiert.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from brotrechner.core.nutrients import ENERGY_FACTORS_KCAL_PER_G, Nutrients

__all__ = [
    "TOLERANCE_FIELDS",
    "ValueRange",
    "nutrient_ranges",
    "tolerance_for",
]

#: Felder, für die Tabelle 1 eine Toleranz vorsieht.
TOLERANCE_FIELDS: Final[tuple[str, ...]] = (
    "fat",
    "saturated_fat",
    "carbs",
    "sugar",
    "protein",
    "fiber",
    "salt",
)


@dataclass(frozen=True, slots=True)
class ValueRange:
    """Wertebereich aus Mittelwert, unterer und oberer Grenze."""

    value: float
    minimum: float
    maximum: float

    @property
    def half_width(self) -> float:
        """Halbe Spannweite - die Zahl hinter dem ``±`` in der Anzeige."""
        return (self.maximum - self.minimum) / 2.0

    @property
    def relative_width(self) -> float:
        """Spannweite relativ zum Mittelwert in Prozent (0, falls Mittelwert 0)."""
        if self.value <= 0:
            return 0.0
        return (self.maximum - self.minimum) / self.value * 100.0


def tolerance_for(field: str, value: float) -> float:
    """Zulässige absolute Abweichung eines deklarierten Werts.

    Args:
        field: Feldname aus :data:`~brotrechner.core.nutrients.NUTRIENT_FIELDS`.
        value: Deklarierter Wert je 100 g.

    Returns:
        Absolute Toleranz (das ``±``). Für Felder ohne definierte Toleranz -
        insbesondere ``energy_kcal`` und ``water`` - ist das Ergebnis ``0.0``;
        der Brennwert wird stattdessen über :func:`nutrient_ranges` abgeleitet.

    Raises:
        ValueError: Bei negativem Wert - Nährwerte können nicht negativ sein.
    """
    if value < 0:
        raise ValueError(f"Nährwert darf nicht negativ sein: {field}={value!r}")
    if value == 0:
        # Ein deklarierter Nullwert bekommt keine Bandbreite: "enthält 0 g Fett"
        # soll in der Auswertung nicht plötzlich zu "0-2 g" werden.
        return 0.0

    if field in ("carbs", "sugar", "protein", "fiber"):
        return _banded(value, small_limit=10.0, small_abs=2.0, large_abs=8.0)
    if field == "fat":
        return _banded(value, small_limit=10.0, small_abs=1.5, large_abs=8.0)
    if field == "saturated_fat":
        return 0.8 if value < 4.0 else value * 0.20
    if field == "salt":
        return 0.375 if value < 1.25 else value * 0.20
    return 0.0


def _banded(value: float, *, small_limit: float, small_abs: float, large_abs: float) -> float:
    """Dreistufige Toleranz: fester Betrag - 20 % - fester Betrag."""
    if value < small_limit:
        return small_abs
    if value <= 40.0:
        return value * 0.20
    return large_abs


def nutrient_ranges(nutrients: Nutrients) -> dict[str, ValueRange]:
    """Bandbreiten aller Nährstoffe eines Vektors je 100 g.

    Der Brennwert wird nicht geschätzt, sondern aus den unteren bzw. oberen
    Grenzen der energieliefernden Nährstoffe berechnet (Anhang XIV). Fällt der
    deklarierte Brennwert nicht in dieses Intervall, wird das Intervall so
    erweitert, dass der deklarierte Wert enthalten bleibt - sonst stünde in der
    Anzeige ein Mittelwert außerhalb seiner eigenen Bandbreite.

    Args:
        nutrients: Nährwertvektor je 100 g.

    Returns:
        Dict von Feldname auf :class:`ValueRange`. Untere Grenzen werden bei 0
        abgeschnitten, weil negative Nährwerte physikalisch unmöglich sind.
    """
    ranges: dict[str, ValueRange] = {}
    for field in TOLERANCE_FIELDS:
        value = getattr(nutrients, field)
        tol = tolerance_for(field, value)
        ranges[field] = ValueRange(value, max(0.0, value - tol), value + tol)

    energy_min = 0.0
    energy_max = 0.0
    for field, factor in ENERGY_FACTORS_KCAL_PER_G.items():
        energy_min += ranges[field].minimum * factor
        energy_max += ranges[field].maximum * factor

    declared = nutrients.energy_kcal
    ranges["energy_kcal"] = ValueRange(
        declared,
        max(0.0, min(energy_min, declared)),
        max(energy_max, declared),
    )
    return ranges
