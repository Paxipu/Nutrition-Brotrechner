"""Stoffe, die Allergien oder Unverträglichkeiten auslösen (Anhang II LMIV).

Anhang II der VO (EU) Nr. 1169/2011 nennt 14 Gruppen. Zwei davon fassen
mehrere Lebensmittel zusammen - glutenhaltiges Getreide und Schalenfrüchte.
Hier sind deren Mitglieder einzeln erfasst, weil eine Angabe ohne
Zutatenverzeichnis ("Enthält: ...") nach Artikel 21 das konkrete Getreide bzw.
die konkrete Nuss nennen muss, nicht bloß "Gluten".

Dinkel steht als eigenes Mitglied neben Weizen: Anhang II nennt ihn
ausdrücklich ("Weizen (wie Dinkel und Khorasan-Weizen)"), und auf einem
Dinkelbrot wäre "Enthält: Weizen" für die meisten Käufer irreführend. Emmer,
Einkorn und Khorasan-Weizen zählen als Weizen.

Ob eine Zutat überhaupt geprüft wurde, ist eine eigene Information: ``None``
heißt "nicht erfasst", eine leere Menge "enthält keines". Eine nie geprüfte
Zutat gilt nicht als allergenfrei.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum
from typing import Final

__all__ = ["ALLERGEN_GROUPS", "Allergen", "allergen_keys", "describe_allergens", "parse_allergens"]


class Allergen(Enum):
    """Ein Allergen nach Anhang II; der Wert ist der stabile JSON-Schlüssel.

    Bewusst keine Ableitung von ``str`` - aus demselben Grund wie bei
    :class:`~brotrechner.core.models.Category`.
    """

    # 1 Glutenhaltiges Getreide
    WHEAT = "wheat"
    SPELT = "spelt"
    RYE = "rye"
    BARLEY = "barley"
    OATS = "oats"
    # 2-7
    CRUSTACEANS = "crustaceans"
    EGGS = "eggs"
    FISH = "fish"
    PEANUTS = "peanuts"
    SOY = "soy"
    MILK = "milk"
    # 8 Schalenfrüchte
    ALMONDS = "almonds"
    HAZELNUTS = "hazelnuts"
    WALNUTS = "walnuts"
    CASHEWS = "cashews"
    PECANS = "pecans"
    BRAZIL_NUTS = "brazil_nuts"
    PISTACHIOS = "pistachios"
    MACADAMIA = "macadamia"
    # 9-14
    CELERY = "celery"
    MUSTARD = "mustard"
    SESAME = "sesame"
    SULPHITES = "sulphites"
    LUPIN = "lupin"
    MOLLUSCS = "molluscs"

    @property
    def label(self) -> str:
        """Name, wie er in einer Angabe "Enthält: ..." steht."""
        return _LABELS[self]

    @property
    def group(self) -> str:
        """Gruppe nach Anhang II, etwa "Glutenhaltiges Getreide"."""
        return _GROUP_OF[self]


_LABELS: Final[dict[Allergen, str]] = {
    Allergen.WHEAT: "Weizen",
    Allergen.SPELT: "Dinkel",
    Allergen.RYE: "Roggen",
    Allergen.BARLEY: "Gerste",
    Allergen.OATS: "Hafer",
    Allergen.CRUSTACEANS: "Krebstiere",
    Allergen.EGGS: "Eier",
    Allergen.FISH: "Fisch",
    Allergen.PEANUTS: "Erdnüsse",
    Allergen.SOY: "Soja",
    Allergen.MILK: "Milch",
    Allergen.ALMONDS: "Mandeln",
    Allergen.HAZELNUTS: "Haselnüsse",
    Allergen.WALNUTS: "Walnüsse",
    Allergen.CASHEWS: "Kaschunüsse",
    Allergen.PECANS: "Pecannüsse",
    Allergen.BRAZIL_NUTS: "Paranüsse",
    Allergen.PISTACHIOS: "Pistazien",
    Allergen.MACADAMIA: "Macadamianüsse",
    Allergen.CELERY: "Sellerie",
    Allergen.MUSTARD: "Senf",
    Allergen.SESAME: "Sesam",
    Allergen.SULPHITES: "Schwefeldioxid und Sulfite",
    Allergen.LUPIN: "Lupinen",
    Allergen.MOLLUSCS: "Weichtiere",
}

#: Die 14 Gruppen in der Reihenfolge von Anhang II, je mit ihren Mitgliedern.
ALLERGEN_GROUPS: Final[tuple[tuple[str, tuple[Allergen, ...]], ...]] = (
    (
        "Glutenhaltiges Getreide",
        (Allergen.WHEAT, Allergen.SPELT, Allergen.RYE, Allergen.BARLEY, Allergen.OATS),
    ),
    ("Krebstiere", (Allergen.CRUSTACEANS,)),
    ("Eier", (Allergen.EGGS,)),
    ("Fisch", (Allergen.FISH,)),
    ("Erdnüsse", (Allergen.PEANUTS,)),
    ("Sojabohnen", (Allergen.SOY,)),
    ("Milch", (Allergen.MILK,)),
    (
        "Schalenfrüchte",
        (
            Allergen.ALMONDS,
            Allergen.HAZELNUTS,
            Allergen.WALNUTS,
            Allergen.CASHEWS,
            Allergen.PECANS,
            Allergen.BRAZIL_NUTS,
            Allergen.PISTACHIOS,
            Allergen.MACADAMIA,
        ),
    ),
    ("Sellerie", (Allergen.CELERY,)),
    ("Senf", (Allergen.MUSTARD,)),
    ("Sesamsamen", (Allergen.SESAME,)),
    ("Schwefeldioxid und Sulfite", (Allergen.SULPHITES,)),
    ("Lupinen", (Allergen.LUPIN,)),
    ("Weichtiere", (Allergen.MOLLUSCS,)),
)

_GROUP_OF: Final[dict[Allergen, str]] = {
    member: name for name, members in ALLERGEN_GROUPS for member in members
}

_BY_KEY: Final[dict[str, Allergen]] = {member.value: member for member in Allergen}


def parse_allergens(raw: object) -> frozenset[Allergen] | None:
    """Liest Allergene aus JSON.

    Args:
        raw: Liste von Schlüsseln wie ``["wheat", "milk"]``.

    Returns:
        Die erkannten Allergene; unbekannte Schlüssel werden übergangen, damit
        eine spätere Programmfassung neue ergänzen kann. Alles, was keine Liste
        ist - auch ein fehlender Eintrag -, bedeutet "nicht erfasst" (``None``).
    """
    if not isinstance(raw, list):
        return None
    return frozenset(_BY_KEY[key] for key in raw if isinstance(key, str) and key in _BY_KEY)


def describe_allergens(allergens: frozenset[Allergen] | None) -> str:
    """Kurzbeschreibung für Listen: "Weizen, Milch", "keine" oder "nicht erfasst"."""
    if allergens is None:
        return "nicht erfasst"
    if not allergens:
        return "keine"
    order = list(Allergen)
    return ", ".join(a.label for a in sorted(allergens, key=order.index))


def allergen_keys(allergens: Iterable[Allergen]) -> list[str]:
    """JSON-Schlüssel in der Reihenfolge von Anhang II."""
    order = list(Allergen)
    return [a.value for a in sorted(allergens, key=order.index)]
