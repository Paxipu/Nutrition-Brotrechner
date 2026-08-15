"""Nährwertvektor und die Energieberechnung nach EU-Recht.

Alle Werte beziehen sich auf 100 g Lebensmittel. Die Einheiten sind bewusst
festgelegt und werden nirgends im Programm umgerechnet:

===================  ========  ==================================================
Feld                 Einheit   Bedeutung
===================  ========  ==================================================
``energy_kcal``      kcal      Brennwert
``fat``              g         Fett gesamt
``saturated_fat``    g         davon gesättigte Fettsäuren
``carbs``            g         Kohlenhydrate **ohne** Ballaststoffe (EU-Konvention)
``sugar``            g         davon Zucker
``protein``          g         Eiweiß
``salt``             g         Salz (= Natrium × 2,5)
``fiber``            g         Ballaststoffe
``water``            g         Wasser (entspricht bei 100 g Bezug dem Prozentwert)
===================  ========  ==================================================

Wichtig: ``carbs`` folgt der EU-Konvention und schließt Ballaststoffe **nicht**
ein. Wer Werte aus US-Quellen (USDA) übernimmt, muss dort vorher die
Ballaststoffe abziehen, sonst wird der Brennwert deutlich zu hoch.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, fields, replace
from typing import Any, Final

__all__ = [
    "ENERGY_FACTORS_KCAL_PER_G",
    "KCAL_TO_KJ",
    "MACRO_FIELDS",
    "NUTRIENT_FIELDS",
    "Nutrients",
    "energy_from_macros",
    "energy_kj",
]

#: Umrechnungsfaktor kcal → kJ nach Anhang XIV VO (EU) Nr. 1169/2011.
KCAL_TO_KJ: Final = 4.184

#: Umrechnungsfaktoren Nährstoff → Energie, Anhang XIV VO (EU) Nr. 1169/2011.
#: Ballaststoffe zählen dort ausdrücklich mit 2 kcal/g, was in vielen
#: Nährwerttabellen schlicht vergessen wird.
ENERGY_FACTORS_KCAL_PER_G: Final[dict[str, float]] = {
    "carbs": 4.0,
    "protein": 4.0,
    "fat": 9.0,
    "fiber": 2.0,
}

#: Felder, die sich beim Mischen von Zutaten additiv verhalten (je 100 g).
NUTRIENT_FIELDS: Final[tuple[str, ...]] = (
    "energy_kcal",
    "fat",
    "saturated_fat",
    "carbs",
    "sugar",
    "protein",
    "salt",
    "fiber",
    "water",
)

#: Felder, die in der Massenbilanz eines Lebensmittels auftauchen (g je 100 g).
MACRO_FIELDS: Final[tuple[str, ...]] = (
    "fat",
    "carbs",
    "protein",
    "salt",
    "fiber",
    "water",
)


@dataclass(frozen=True, slots=True)
class Nutrients:
    """Unveränderlicher Nährwertvektor je 100 g.

    Instanzen sind bewusst *frozen*: Nährwerte werden nie in-place verändert,
    sondern über :meth:`scaled`, :meth:`__add__` oder :meth:`with_values` neu
    erzeugt. Damit kann eine Zutat gefahrlos in mehreren Rezepten stecken.
    """

    energy_kcal: float = 0.0
    fat: float = 0.0
    saturated_fat: float = 0.0
    carbs: float = 0.0
    sugar: float = 0.0
    protein: float = 0.0
    salt: float = 0.0
    fiber: float = 0.0
    water: float = 0.0

    # ── Arithmetik ────────────────────────────────────────────────────────

    def scaled(self, factor: float) -> Nutrients:
        """Skaliert alle Felder linear.

        Args:
            factor: Skalierungsfaktor, üblicherweise ``menge_g / 100``.

        Returns:
            Neuer Vektor mit skalierten Werten.

        Raises:
            ValueError: Wenn ``factor`` nicht endlich ist.
        """
        if not math.isfinite(factor):
            raise ValueError(f"Skalierungsfaktor muss endlich sein, war {factor!r}")
        return Nutrients(**{f: getattr(self, f) * factor for f in NUTRIENT_FIELDS})

    def __add__(self, other: Nutrients) -> Nutrients:
        """Addiert zwei Vektoren feldweise (für absolute Mengen, nicht je 100 g)."""
        if not isinstance(other, Nutrients):
            return NotImplemented
        return Nutrients(**{f: getattr(self, f) + getattr(other, f) for f in NUTRIENT_FIELDS})

    def with_values(self, **changes: float) -> Nutrients:
        """Gibt eine Kopie mit geänderten Einzelfeldern zurück."""
        unknown = set(changes) - set(NUTRIENT_FIELDS)
        if unknown:
            raise ValueError(f"Unbekannte Nährwertfelder: {sorted(unknown)}")
        return replace(self, **changes)

    # ── Abgeleitete Größen ────────────────────────────────────────────────

    @property
    def energy_kj(self) -> float:
        """Brennwert in kJ, gerundet auf ganze kJ wie auf dem Etikett üblich."""
        return round(self.energy_kcal * KCAL_TO_KJ)

    @property
    def computed_energy_kcal(self) -> float:
        """Aus den Makronährstoffen berechneter Brennwert (Anhang XIV)."""
        return energy_from_macros(self)

    @property
    def mass_sum(self) -> float:
        """Summe der bilanzierbaren Bestandteile je 100 g.

        Der Rest zu 100 g sind Asche/Mineralstoffe, organische Säuren,
        Polyole und Messungenauigkeit - ein Wert deutlich *über* 100 ist
        dagegen immer ein Datenfehler.
        """
        return float(sum(getattr(self, f) for f in MACRO_FIELDS))

    # ── Serialisierung ────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, float]:
        """JSON-taugliches Dict mit allen Feldern."""
        return {f: float(getattr(self, f)) for f in NUTRIENT_FIELDS}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Nutrients:
        """Liest einen Vektor aus einem Dict; unbekannte Schlüssel werden ignoriert.

        Fehlende Felder werden zu ``0.0``, nicht-numerische Werte lösen einen
        ``ValueError`` aus - stillschweigend 0 anzunehmen würde Datenfehler
        verstecken.
        """
        values: dict[str, float] = {}
        for name in NUTRIENT_FIELDS:
            raw = data.get(name, 0.0)
            if raw is None:
                values[name] = 0.0
                continue
            try:
                values[name] = float(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Nährwertfeld {name!r} ist nicht numerisch: {raw!r}") from exc
        return cls(**values)

    def __repr__(self) -> str:  # pragma: no cover - reine Diagnoseausgabe
        parts = ", ".join(
            f"{f.name}={getattr(self, f.name):g}" for f in fields(self) if getattr(self, f.name)
        )
        return f"Nutrients({parts})"


def energy_from_macros(nutrients: Nutrients) -> float:
    """Berechnet den Brennwert aus den Makronährstoffen.

    Verwendet die Umrechnungsfaktoren aus Anhang XIV der VO (EU) Nr. 1169/2011
    (Kohlenhydrate 4, Eiweiß 4, Fett 9, Ballaststoffe 2 kcal/g). Alkohol und
    Polyole kommen in Backzutaten praktisch nicht vor und werden nicht erfasst.

    Args:
        nutrients: Nährwertvektor je 100 g.

    Returns:
        Brennwert in kcal je 100 g.
    """
    total = 0.0
    for field, factor in ENERGY_FACTORS_KCAL_PER_G.items():
        total += float(getattr(nutrients, field)) * factor
    return total


def energy_kj(kcal: float) -> float:
    """Rechnet kcal in kJ um (Faktor 4,184)."""
    return kcal * KCAL_TO_KJ
