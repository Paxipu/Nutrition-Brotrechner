"""Portionen: Nährwerte und Kosten je Scheibe, Brötchen oder Stück.

Pflicht ist auf dem Etikett nur die Angabe je 100 g. Artikel 33 Abs. 1 der
VO (EU) Nr. 1169/2011 erlaubt *zusätzlich* die Angabe je Portion - sofern die
Portion auf dem Etikett quantifiziert ist ("je Scheibe (50 g)") und die Anzahl
der Portionen in der Packung dasteht. Nach Abs. 4 steht die Portion in
unmittelbarer Nähe der Nährwerttabelle.

Die Werte je Portion entstehen aus den *ungerundeten* Werten je 100 g und
werden erst dann gerundet, wie jede Angabe
(:func:`brotrechner.core.rounding.declare_nutrient`). Gerundet wird dabei die
Menge je Portion selbst: 0,8 g Zucker in einer Scheibe stehen als "0,8 g" da,
auch wenn 100 g Brot nur 0,4 g enthalten.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Final

from brotrechner.core.nutrients import Nutrients

__all__ = ["DEFAULT_NAME", "MAX_WEIGHT_G", "MIN_WEIGHT_G", "SUGGESTED_NAMES", "Portion"]

#: Bezeichnung einer Portion ohne eigenen Namen.
DEFAULT_NAME: Final = "Portion"

#: Kleinstes und größtes Portionsgewicht in Gramm. Was außerhalb liegt, ist
#: ein Tippfehler oder eine kaputte Datei, keine Portion Brot.
MIN_WEIGHT_G: Final = 0.1
MAX_WEIGHT_G: Final = 100_000.0

#: Vorschläge für die Auswahlliste; jede andere Bezeichnung ist ebenso erlaubt.
SUGGESTED_NAMES: Final[tuple[str, ...]] = ("Scheibe", "Stück", "Brötchen", "Portion")

#: Mehrzahl der üblichen Bezeichnungen. Für jede andere Bezeichnung wird die
#: Mehrzahl nicht geraten - "3 × Stulle" ist richtig, "3 Stulles" nicht.
_PLURALS: Final[dict[str, str]] = {
    "brezel": "Brezeln",
    "brötchen": "Brötchen",
    "laib": "Laibe",
    "portion": "Portionen",
    "scheibe": "Scheiben",
    "schnitte": "Schnitten",
    "semmel": "Semmeln",
    "stange": "Stangen",
    "stück": "Stück",
    "waffel": "Waffeln",
}

#: So nah muss die Anzahl an einer ganzen Zahl liegen, damit sie ohne "ca."
#: dasteht: 1000 g Brot in Scheiben zu 50 g sind 20 Scheiben, 996 g "ca. 20".
_EXACT_WITHIN: Final = 0.05


@dataclass(frozen=True, slots=True)
class Portion:
    """Eine Portion des fertigen Brots.

    Attributes:
        name: Bezeichnung in der Einzahl, etwa "Scheibe". Leerraum wird
            vereinheitlicht; ohne Bezeichnung heißt sie :data:`DEFAULT_NAME`.
        weight_g: Gewicht einer Portion in Gramm, von :data:`MIN_WEIGHT_G`
            bis :data:`MAX_WEIGHT_G`.

    Raises:
        ValueError: Bei einem Gewicht außerhalb dieses Bereichs, auch bei
            ``nan`` und unendlich.
    """

    name: str
    weight_g: float

    def __post_init__(self) -> None:
        # Als Bereichsprüfung formuliert, damit auch nan durchfällt.
        if not MIN_WEIGHT_G <= self.weight_g <= MAX_WEIGHT_G:
            raise ValueError(
                f"Eine Portion muss zwischen 0,1 g und 100 kg wiegen, war {self.weight_g!r}"
            )
        # Eingefrorene Datenklasse: Die bereinigten Werte lassen sich nur so setzen.
        object.__setattr__(self, "name", _single_line(self.name) or DEFAULT_NAME)
        object.__setattr__(self, "weight_g", float(self.weight_g))

    @property
    def weight_text(self) -> str:
        """Gewicht wie auf dem Etikett: "50 g", "45,5 g"."""
        rounded = Decimal(repr(self.weight_g)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        text = str(int(rounded)) if rounded == rounded.to_integral() else str(rounded)
        return f"{text.replace('.', ',')} g"

    @property
    def title(self) -> str:
        """Bezeichnung mit Gewicht, etwa "Scheibe (50 g)"."""
        return f"{self.name} ({self.weight_text})"

    def fits_into(self, grams: float) -> bool:
        """Passt mindestens eine ganze Portion in ``grams``?"""
        return self.weight_g <= grams

    def count(self, grams: float) -> float:
        """Anzahl der Portionen in ``grams`` Brot."""
        return grams / self.weight_g

    def count_text(self, grams: float) -> str:
        """Anzahl der Portionen in Worten, etwa "20 Scheiben" oder "ca. 20 Scheiben".

        Raises:
            ValueError: Wenn die Portion schwerer ist als ``grams`` - dann
                gibt es keine sinnvolle Anzahl - oder ``grams`` nicht endlich.
        """
        if not math.isfinite(grams):
            raise ValueError(f"Brotgewicht muss endlich sein, war {grams!r}")
        if not self.fits_into(grams):
            raise ValueError(
                f"Die Portion ({self.weight_text}) ist schwerer als das Brot ({grams:.0f} g)"
            )
        exact = self.count(grams)
        number = math.floor(exact + 0.5)  # Halbe aufwärts, wie überall auf dem Etikett
        prefix = "ca. " if abs(number - exact) > _EXACT_WITHIN else ""
        plural = _PLURALS.get(self.name.casefold())
        if plural is None:
            return f"{prefix}{number} × {self.name}"
        return f"{prefix}{number} {self.name if number == 1 else plural}"

    def nutrients(self, per_100g: Nutrients) -> Nutrients:
        """Nährwerte einer Portion aus den Werten je 100 g."""
        return per_100g.scaled(self.weight_g / 100.0)

    def cost(self, cost_per_100g: float) -> float:
        """Kosten einer Portion aus den Kosten je 100 g."""
        return cost_per_100g * self.weight_g / 100.0

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "weight_g": self.weight_g}

    @classmethod
    def from_dict(cls, data: object) -> Portion | None:
        """Liest eine gespeicherte Portion.

        Ist sie unbrauchbar, gibt es eben keine: Eine kaputte Portionsangabe
        darf nicht das ganze Rezept unlesbar machen.
        """
        if not isinstance(data, dict):
            return None
        raw = data.get("weight_g")
        if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
            return None
        try:
            return cls(str(data.get("name") or ""), float(raw))
        except ValueError:
            return None


def _single_line(text: str) -> str:
    """Eine Zeile ohne Steuerzeichen und doppelten Leerraum."""
    cleaned = "".join(" " if ch.isspace() or ord(ch) < 32 else ch for ch in text)
    return " ".join(cleaned.split())
