"""Rundung der Nährwertangabe nach der Leitlinie der EU-Kommission.

Quelle: Europäische Kommission, *Guidance document for competent authorities
for the control of compliance with EU legislation on ... the setting of
tolerances for nutrient values declared on a label*, Dezember 2012, Abschnitt
"Rounding guidelines for nutrition declaration":

==========================================  ==============  ======================
Nährstoff                                   Menge je 100 g  Angabe
==========================================  ==============  ======================
Brennwert                                                   ganze kJ und kcal
Fett, Kohlenhydrate, Zucker, Eiweiß,        ≥ 10 g          ganze Gramm
Ballaststoffe                               > 0,5 bis 10 g  auf 0,1 g
                                            ≤ 0,5 g         "0 g" oder "< 0,5 g"
Gesättigte Fettsäuren                       ≥ 10 g          ganze Gramm
                                            > 0,1 bis 10 g  auf 0,1 g
                                            ≤ 0,1 g         "0 g" oder "< 0,1 g"
Salz                                        ≥ 1 g           auf 0,1 g
                                            > 0,0125 bis 1  auf 0,01 g
                                            ≤ 0,0125 g      "0 g" oder "< 0,01 g"
==========================================  ==============  ======================

Wo die Leitlinie "0 g" *oder* "< x g" zulässt, steht "0 g" nur für echte null
und sonst "< x g": Es ist die ehrlichere Angabe für eine kleine, aber
vorhandene Menge.

Gerundet wird kaufmännisch (Halbe aufwärts), nicht mit Pythons ``round``, das
Halbe zur geraden Zahl rundet: 2,45 g werden 2,5 g, nicht 2,4 g.

Liegt ein Wert knapp unter einer Bandgrenze und rundet auf sie (9,96 g auf
10,0 g), steht er in der Schreibweise des höheren Bandes da ("10 g"). Der
Zahlenwert ist derselbe; "10,0 g" neben "12 g" sähe nur unordentlich aus.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Final

from brotrechner.core.nutrients import KCAL_TO_KJ

__all__ = ["DECLARED_FIELDS", "Declared", "as_declarable", "declare_energy", "declare_nutrient"]


@dataclass(frozen=True, slots=True)
class _Bands:
    """Rundungsbänder eines Nährstoffs, alle Angaben in Gramm je 100 g."""

    limit: float
    """Bis hierher (einschließlich) lautet die Angabe "< shown_limit g"."""
    shown_limit: str
    """Die Schranke, wie sie in der Angabe steht. Beim Salz ist sie kleiner als
    ``limit``: 0,0125 g Salz entsprechen den 0,005 g Natrium der Leitlinie,
    angegeben werden sie als "< 0,01 g"."""
    coarse_from: float
    """Ab hier gilt der grobe Rundungsschritt."""
    fine_step: str
    coarse_step: str


_MAIN = _Bands(limit=0.5, shown_limit="0.5", coarse_from=10.0, fine_step="0.1", coarse_step="1")
_SATURATES = _Bands(
    limit=0.1, shown_limit="0.1", coarse_from=10.0, fine_step="0.1", coarse_step="1"
)
_SALT = _Bands(
    limit=0.0125, shown_limit="0.01", coarse_from=1.0, fine_step="0.01", coarse_step="0.1"
)

_BANDS: Final[dict[str, _Bands]] = {
    "fat": _MAIN,
    "saturated_fat": _SATURATES,
    "carbs": _MAIN,
    "sugar": _MAIN,
    "protein": _MAIN,
    "fiber": _MAIN,
    "salt": _SALT,
}

#: Nährstoffe, deren Angabe hier gerundet wird (ohne Brennwert).
DECLARED_FIELDS: Final[tuple[str, ...]] = tuple(_BANDS)


@dataclass(frozen=True, slots=True)
class Declared:
    """Eine gerundete Nährwertangabe."""

    amount: float
    """Gerundete Menge in Gramm; bei "< x g" die angegebene Schranke x."""
    text: str
    """Fertige Angabe mit deutschem Dezimalkomma und Einheit, etwa "4,4 g"."""
    below: bool = False
    """True, wenn die Angabe "< x g" lautet."""


def declare_nutrient(field: str, grams: float) -> Declared:
    """Rundet einen Nährstoff für die Nährwertangabe.

    Args:
        field: Feldname, z. B. ``"salt"``; siehe :data:`DECLARED_FIELDS`.
        grams: Gehalt in Gramm (je 100 g oder je Portion).

    Returns:
        Die gerundete Angabe.

    Raises:
        ValueError: Für Felder ohne Rundungsregel oder bei negativem oder
            nicht endlichem Gehalt - ein solcher Wert darf nie auf ein Etikett.
    """
    bands = _BANDS.get(field)
    if bands is None:
        raise ValueError(f"Für {field!r} gibt es keine Nährwertangabe")
    if not math.isfinite(grams) or grams < 0:
        raise ValueError(f"Ungültiger Gehalt für {field!r}: {grams!r}")

    if grams == 0:
        return Declared(0.0, "0 g")
    if grams <= bands.limit:
        shown = Decimal(bands.shown_limit)
        return Declared(float(shown), f"< {_german(shown)} g", below=True)

    fine = _round_half_up(grams, bands.fine_step)
    if grams >= bands.coarse_from or fine >= Decimal(str(bands.coarse_from)):
        rounded = _round_half_up(grams, bands.coarse_step)
    else:
        rounded = fine
    return Declared(float(rounded), f"{_german(rounded)} g")


def declare_energy(kcal: float) -> str:
    """Brennwertangabe in ganzen kJ und kcal, etwa ``"951 kJ / 227 kcal"``.

    Die Kilojoule werden aus dem ungerundeten kcal-Wert berechnet und erst
    dann gerundet - sonst verschöbe die Rundung der kcal die kJ mit.

    Raises:
        ValueError: Bei negativem oder nicht endlichem Brennwert.
    """
    if not math.isfinite(kcal) or kcal < 0:
        raise ValueError(f"Ungültiger Brennwert: {kcal!r}")
    kj = _round_half_up(kcal * KCAL_TO_KJ, "1")
    return f"{kj} kJ / {_round_half_up(kcal, '1')} kcal"


def as_declarable(value: float) -> float:
    """Macht einen berechneten Wert angebbar, statt die Ausgabe abstürzen zu lassen.

    Negative oder nicht endliche Werte entstehen nur aus Zutaten, die die
    Datenprüfung bereits als fehlerhaft meldet. Etikett und Bericht zeigen
    dann 0 - die Warnung dazu kommt aus der Prüfung, nicht aus einem Absturz.
    """
    return value if math.isfinite(value) and value > 0 else 0.0


def _round_half_up(value: float, step: str) -> Decimal:
    """Kaufmännisch gerundet auf ``step`` (etwa ``"0.1"``).

    Über ``repr`` statt über den exakten Binärwert: 2.45 ist als float
    2.4500000000000001776..., soll aber so gerundet werden, wie es dasteht.
    """
    return Decimal(repr(value)).quantize(Decimal(step), rounding=ROUND_HALF_UP)


def _german(value: Decimal) -> str:
    """Dezimalzahl mit Komma, Stellen wie im Rundungsschritt."""
    return str(value).replace(".", ",")
