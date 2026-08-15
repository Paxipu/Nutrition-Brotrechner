"""Plausibilitätsprüfung der Zutatendatenbank.

Die Prüfungen sind bewusst *objektiv*: Sie stützen sich auf Bilanzen und
gesetzliche Rechenregeln, nicht auf Geschmacksfragen. Damit lässt sich die
Datenbank jederzeit nachvollziehbar auditieren - über die Oberfläche
(*Zutaten → Datenprüfung*) oder auf der Kommandozeile::

    brotrechner check

Geprüft wird:

============  ==============================================================
Code          Bedeutung
============  ==============================================================
``negative``  Ein Nährwert ist negativ.
``sat_gt_fat``  Gesättigte Fettsäuren übersteigen das Gesamtfett.
``sugar_gt_carbs``  Zucker übersteigt die Kohlenhydrate.
``mass_balance``  Fett + KH + Eiweiß + Ballaststoffe + Salz + Wasser > 100 g.
``energy``    Brennwert passt nicht zu den Makronährstoffen (Anhang XIV).
``water``     Wassergehalt außerhalb des für die Kategorie plausiblen Bereichs.
``salt_range``  Salzgehalt über 100 g/100 g.
``price_missing``  Kein Preis hinterlegt.
``price_inconsistent``  Preis ohne Packungsgröße.
``name_manufacturer``  Herstellername steckt noch im Zutatennamen.
``duplicate``  Zwei Zutaten mit identischem Schlüssel.
============  ==============================================================
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Final

from brotrechner.core.models import Category, Ingredient
from brotrechner.core.nutrients import Nutrients, energy_from_macros

__all__ = [
    "KNOWN_MANUFACTURERS",
    "PLAUSIBLE_WATER_RANGES",
    "Finding",
    "Severity",
    "energy_deviation",
    "validate_database",
    "validate_ingredient",
]


class Severity(Enum):
    """Schweregrad eines Befunds."""

    ERROR = "error"
    """Der Wert ist sicher falsch - die Bilanz ist verletzt."""

    WARNING = "warning"
    """Der Wert ist unplausibel, kann aber im Einzelfall stimmen."""

    INFO = "info"
    """Hinweis ohne Fehlercharakter, z. B. ein fehlender Preis."""

    @property
    def label(self) -> str:
        return {Severity.ERROR: "Fehler", Severity.WARNING: "Warnung", Severity.INFO: "Hinweis"}[
            self
        ]

    @property
    def rank(self) -> int:
        """Sortierrang, höher = dringender."""
        return {Severity.INFO: 0, Severity.WARNING: 1, Severity.ERROR: 2}[self]


@dataclass(frozen=True, slots=True)
class Finding:
    """Ein einzelner Prüfbefund."""

    key: str
    """Schlüssel der betroffenen Zutat."""
    display_name: str
    field: str
    code: str
    severity: Severity
    message: str
    suggestion: float | None = None
    """Rechnerisch hergeleiteter Ersatzwert, sofern eindeutig bestimmbar."""

    def __str__(self) -> str:
        prefix = f"[{self.severity.label}] {self.display_name}"
        suffix = f" → Vorschlag: {self.suggestion:g}" if self.suggestion is not None else ""
        return f"{prefix}: {self.message}{suffix}"


#: Plausible Wassergehalte je Kategorie in g/100 g.
#: Hergeleitet aus dem, was das jeweilige Erzeugnis technologisch haben kann.
#: Mahlerzeugnisse liegen handelsüblich bei 12-15 %, weil sie sonst nicht
#: lagerfähig sind; die Obergrenze von 20 % lässt Stärken zu, die als
#: ausgesprochen hygroskopische Erzeugnisse regelmäßig 18-20 % halten.
PLAUSIBLE_WATER_RANGES: Final[dict[Category, tuple[float, float]]] = {
    Category.FLOUR: (9.0, 20.0),
    Category.GRAINS: (4.0, 15.0),
    Category.SEEDS_NUTS: (1.0, 12.0),
    Category.LEAVENING: (0.0, 80.0),
    Category.BASICS: (0.0, 100.0),
    Category.FATS_OILS: (0.0, 20.0),
    Category.DAIRY: (0.0, 95.0),
    Category.SPICES: (4.0, 15.0),
    Category.OTHER: (0.0, 100.0),
}

#: Hersteller/Handelsmarken, die im Namen erkannt und ins eigene Feld gehören.
KNOWN_MANUFACTURERS: Final[tuple[str, ...]] = (
    "Aldi",
    "Alnatura",
    "Bauck",
    "Bauckhof",
    "dm",
    "dm Bio",
    "Demeter",
    "Edeka",
    "Grünland",
    "Kaufland",
    "Lidl",
    "Netto",
    "Norma",
    "Penny",
    "Rapunzel",
    "Rewe",
    "Rossmann",
    "Spielberger",
)

#: Toleranz der Brennwertprüfung: relativer Anteil und absoluter Sockel.
_ENERGY_REL_TOLERANCE: Final = 0.12
_ENERGY_ABS_TOLERANCE: Final = 12.0

#: Über 100,5 g je 100 g ist die Massenbilanz sicher verletzt; der halbe Gramm
#: Spielraum fängt Rundungen auf dem Etikett ab.
_MASS_BALANCE_LIMIT: Final = 100.5

_MANUFACTURER_IN_NAME = re.compile(r"\(([^)]+)\)")


def energy_deviation(nutrients: Nutrients) -> float:
    """Absolute Abweichung zwischen deklariertem und berechnetem Brennwert."""
    return nutrients.energy_kcal - energy_from_macros(nutrients)


def validate_ingredient(ingredient: Ingredient) -> list[Finding]:
    """Prüft eine einzelne Zutat.

    Args:
        ingredient: Zu prüfende Zutat.

    Returns:
        Liste der Befunde, absteigend nach Schweregrad sortiert.
    """
    n = ingredient.nutrients
    findings: list[Finding] = []

    def add(
        field: str,
        code: str,
        severity: Severity,
        message: str,
        suggestion: float | None = None,
    ) -> None:
        findings.append(
            Finding(
                ingredient.key, ingredient.display_name, field, code, severity, message, suggestion
            )
        )

    for name in (
        "energy_kcal",
        "fat",
        "saturated_fat",
        "carbs",
        "sugar",
        "protein",
        "salt",
        "fiber",
        "water",
    ):
        value = getattr(n, name)
        if value < 0:
            add(name, "negative", Severity.ERROR, f"{name} ist negativ ({value:g})", 0.0)

    if n.saturated_fat > n.fat + 0.05:
        add(
            "saturated_fat",
            "sat_gt_fat",
            Severity.ERROR,
            f"gesättigte Fettsäuren ({n.saturated_fat:g} g) über Gesamtfett ({n.fat:g} g)",
            n.fat,
        )

    if n.sugar > n.carbs + 0.05:
        add(
            "sugar",
            "sugar_gt_carbs",
            Severity.ERROR,
            f"Zucker ({n.sugar:g} g) über Kohlenhydraten ({n.carbs:g} g)",
            n.carbs,
        )

    if n.salt > 100.0:
        add(
            "salt",
            "salt_range",
            Severity.ERROR,
            f"Salzgehalt über 100 g/100 g ({n.salt:g})",
            100.0,
        )

    if n.water > 100.0:
        add("water", "water", Severity.ERROR, f"Wassergehalt über 100 % ({n.water:g})", 100.0)

    mass = n.mass_sum
    if mass > _MASS_BALANCE_LIMIT:
        add(
            "water",
            "mass_balance",
            Severity.ERROR,
            f"Massenbilanz verletzt: Fett+KH+Eiweiß+Ballaststoffe+Salz+Wasser = {mass:.1f} g "
            f"je 100 g",
            max(0.0, n.water - (mass - 100.0)),
        )

    computed = energy_from_macros(n)
    limit = max(_ENERGY_ABS_TOLERANCE, computed * _ENERGY_REL_TOLERANCE)
    if abs(n.energy_kcal - computed) > limit:
        add(
            "energy_kcal",
            "energy",
            Severity.WARNING,
            f"Brennwert {n.energy_kcal:g} kcal passt nicht zu den Nährstoffen "
            f"(berechnet {computed:.0f} kcal nach Anhang XIV)",
            round(computed),
        )

    low, high = PLAUSIBLE_WATER_RANGES[ingredient.category]
    if not low <= n.water <= high:
        add(
            "water",
            "water",
            Severity.WARNING,
            f"Wassergehalt {n.water:g} % außerhalb des für "
            f"{ingredient.category.label} plausiblen Bereichs {low:g}-{high:g} %",
        )

    if ingredient.package_price > 0 and ingredient.package_size_g <= 0:
        add(
            "package_size_g",
            "price_inconsistent",
            Severity.ERROR,
            "Preis hinterlegt, aber keine Packungsgröße - der Preis je 100 g ist unbestimmt",
        )
    elif not ingredient.has_price:
        add("package_price", "price_missing", Severity.INFO, "kein Preis hinterlegt")

    for candidate in _MANUFACTURER_IN_NAME.findall(ingredient.name):
        text = candidate.strip()
        if any(text.casefold() == m.casefold() for m in KNOWN_MANUFACTURERS):
            add(
                "name",
                "name_manufacturer",
                Severity.WARNING,
                f"Hersteller {text!r} steckt im Namen und gehört ins Hersteller-Feld",
            )

    findings.sort(key=lambda f: -f.severity.rank)
    return findings


def validate_database(ingredients: Iterable[Ingredient]) -> list[Finding]:
    """Prüft alle Zutaten und zusätzlich datenbankweite Regeln.

    Zusätzlich zu den Einzelprüfungen erkennt diese Funktion Duplikate, also
    Zutaten mit identischem Schlüssel aus Name und Hersteller.

    Args:
        ingredients: Zutaten der Datenbank.

    Returns:
        Alle Befunde, sortiert nach Schweregrad und Anzeigename.
    """
    items = list(ingredients)
    findings: list[Finding] = []
    by_key: dict[str, list[Ingredient]] = defaultdict(list)

    for ingredient in items:
        findings.extend(validate_ingredient(ingredient))
        by_key[ingredient.key].append(ingredient)

    for key, group in by_key.items():
        if len(group) > 1:
            names = ", ".join(sorted(i.display_name for i in group))
            findings.append(
                Finding(
                    key=key,
                    display_name=group[0].display_name,
                    field="name",
                    code="duplicate",
                    severity=Severity.ERROR,
                    message=f"{len(group)} Zutaten mit identischem Schlüssel: {names}",
                )
            )

    findings.sort(key=lambda f: (-f.severity.rank, f.display_name.casefold(), f.field))
    return findings
