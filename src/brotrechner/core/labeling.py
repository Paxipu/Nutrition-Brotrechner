"""Bezeichnungen im Zutatenverzeichnis und ihre Hervorhebung.

Allergene müssen im Zutatenverzeichnis so hervorgehoben sein, dass sie sich
vom übrigen Text abheben (Artikel 21 VO (EU) Nr. 1169/2011) - auf dem Etikett
durch Fettdruck. Welcher Teil einer Bezeichnung das Allergen ist, steht in
``*Sternchen*``: ``*Weizen*mehl Type 550`` oder, bei einer zusammengesetzten
Zutat, ``Roggensauerteig (*Roggen*vollkornmehl, Wasser)``.

Ein einzelnes, nicht geschlossenes Sternchen bleibt als Zeichen stehen; die
Datenprüfung meldet es als Fehler.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from brotrechner.core.allergens import Allergen

if TYPE_CHECKING:
    from brotrechner.core.analysis import IngredientLine
    from brotrechner.core.models import Ingredient

__all__ = [
    "IngredientList",
    "ListEntry",
    "Run",
    "build_ingredient_list",
    "contains_statement",
    "has_emphasis",
    "has_unmatched_mark",
    "list_runs",
    "parse_emphasis",
    "plain_text",
]

_MARK = "*"


@dataclass(frozen=True, slots=True)
class Run:
    """Ein Textstück in einheitlicher Auszeichnung."""

    text: str
    bold: bool = False


def parse_emphasis(text: str) -> tuple[Run, ...]:
    """Zerlegt eine Bezeichnung in normale und hervorgehobene Stücke.

    Args:
        text: Bezeichnung mit ``*Hervorhebung*``.

    Returns:
        Nicht leere Stücke; benachbarte gleicher Auszeichnung zusammengefasst.
    """
    parts = text.split(_MARK)
    if len(parts) % 2 == 0:
        # Ungerade Zahl von Sternchen: Das letzte bleibt als Zeichen stehen.
        parts[-2:] = [parts[-2] + _MARK + parts[-1]]

    runs: list[Run] = []
    for index, part in enumerate(parts):
        if not part:
            continue
        bold = index % 2 == 1
        if runs and runs[-1].bold == bold:
            runs[-1] = Run(runs[-1].text + part, bold)
        else:
            runs.append(Run(part, bold))
    return tuple(runs)


def plain_text(text: str) -> str:
    """Bezeichnung ohne Markierung, etwa für Listen und die CSV-Ausgabe."""
    return "".join(run.text for run in parse_emphasis(text))


def has_emphasis(text: str) -> bool:
    """True, wenn mindestens ein Teil hervorgehoben ist."""
    return any(run.bold for run in parse_emphasis(text))


def has_unmatched_mark(text: str) -> bool:
    """True bei einer ungeraden Zahl von Sternchen."""
    return text.count(_MARK) % 2 == 1


def list_runs(label: str, allergens: Collection[object] | None) -> tuple[Run, ...]:
    """Die Bezeichnung einer Zutat, wie sie im Zutatenverzeichnis steht.

    Enthält die Zutat Allergene, ohne dass etwas hervorgehoben ist, wird die
    ganze Bezeichnung fett gesetzt - das Allergen darf im Verzeichnis nicht
    unauffällig bleiben. Die Datenprüfung meldet diesen Fall, damit er bewusst
    so gewollt ist.

    Args:
        label: Bezeichnung mit ``*Hervorhebung*``.
        allergens: Enthaltene Allergene; ``None`` oder leer heißt: nichts
            zusätzlich hervorheben.
    """
    runs = parse_emphasis(label)
    if allergens and runs and not any(run.bold for run in runs):
        return (Run(plain_text(label), bold=True),)
    return runs


# ── Zutatenverzeichnis ─────────────────────────────────────────────────────

#: Ab diesem Wassergehalt gilt eine Zutat als zugefügtes Wasser, dessen
#: Menge sich nach dem fertigen Erzeugnis richtet (Anhang VII Teil A Nr. 1).
_ADDED_WATER_MIN_PERCENT: Final = 99.5


@dataclass(frozen=True, slots=True)
class ListEntry:
    """Eine Zutat im Zutatenverzeichnis."""

    markup: str
    """Bezeichnung mit ``*Hervorhebung*``, so wie sie gedruckt wird."""
    weight_g: float
    """Gewicht, nach dem sortiert wird."""


@dataclass(frozen=True, slots=True)
class IngredientList:
    """Das fertige Zutatenverzeichnis eines Rezepts."""

    entries: tuple[ListEntry, ...] = ()
    allergens: frozenset[Allergen] = frozenset()
    """Alle erfassten Allergene des Rezepts."""
    unknown: tuple[str, ...] = ()
    """Zutaten, deren Allergene nicht erfasst sind (Anzeigenamen)."""

    def plain_text(self) -> str:
        """Das Verzeichnis ohne Markierung, durch Komma getrennt."""
        return ", ".join(plain_text(entry.markup) for entry in self.entries)


def build_ingredient_list(
    lines: Sequence[IngredientLine], *, baked_weight_g: float
) -> IngredientList:
    """Stellt das Zutatenverzeichnis nach Artikel 18 LMIV zusammen.

    * Zutaten mit derselben Bezeichnung - etwa dasselbe Mehl von zwei
      Herstellern - werden zu einem Eintrag zusammengefasst.
    * Sortiert wird absteigend nach dem Gewicht beim Herstellen. Zugefügtes
      Wasser zählt dagegen mit dem, was davon im fertigen Brot bleibt: Brot
      abzüglich aller anderen Zutaten (Anhang VII Teil A Nr. 1). Ist davon
      nichts übrig, fehlt es im Verzeichnis.
    * Allergene sind hervorgehoben; ohne Markierung in der Bezeichnung wird
      die ganze Bezeichnung hervorgehoben (:func:`list_runs`).

    Args:
        lines: Zeilen einer Auswertung (Mengen nach Teigverlust-Skalierung).
        baked_weight_g: Gewicht des fertigen Brots.

    Returns:
        Das Verzeichnis samt Allergenen und nicht erfassten Zutaten.
    """
    water_lines = [line for line in lines if _is_added_water(line.ingredient)]
    others = sum(line.amount_g for line in lines if not _is_added_water(line.ingredient))
    water_in_product = max(0.0, baked_weight_g - others)
    water_in_dough = sum(line.amount_g for line in water_lines)

    merged: dict[str, tuple[str, float, set[Allergen]]] = {}
    allergens: set[Allergen] = set()
    unknown: list[str] = []
    for line in lines:
        ingredient = line.ingredient
        if ingredient.allergens is None:
            unknown.append(ingredient.display_name)
        else:
            allergens |= ingredient.allergens

        if _is_added_water(ingredient):
            if water_in_dough <= 0:
                continue
            weight = water_in_product * line.amount_g / water_in_dough
        else:
            weight = line.amount_g
        if weight <= 0:
            continue

        label = ingredient.list_name
        key = " ".join(plain_text(label).casefold().split())
        previous_label, previous_weight, previous_allergens = merged.get(key, (label, 0.0, set()))
        merged[key] = (
            previous_label,
            previous_weight + weight,
            previous_allergens | set(ingredient.allergens or ()),
        )

    entries = [
        ListEntry(_markup(label, entry_allergens), weight)
        for label, weight, entry_allergens in merged.values()
    ]
    entries.sort(key=lambda entry: entry.weight_g, reverse=True)
    return IngredientList(tuple(entries), frozenset(allergens), tuple(unknown))


def contains_statement(allergens: frozenset[Allergen]) -> str:
    """Angabe für ein Etikett ohne Zutatenverzeichnis (Artikel 21 Abs. 1).

    Returns:
        Etwa ``"Enthält: Weizen, Milch"``; leer, wenn nichts anzugeben ist.
    """
    if not allergens:
        return ""
    order = list(Allergen)
    return "Enthält: " + ", ".join(a.label for a in sorted(allergens, key=order.index))


def _is_added_water(ingredient: Ingredient) -> bool:
    """Reines Wasser, dessen Menge sich nach dem fertigen Brot richtet."""
    return ingredient.nutrients.water >= _ADDED_WATER_MIN_PERCENT


def _markup(label: str, allergens: set[Allergen]) -> str:
    """Bezeichnung mit der Hervorhebung, die tatsächlich gedruckt wird."""
    runs = list_runs(label, allergens)
    return "".join(f"{_MARK}{run.text}{_MARK}" if run.bold else run.text for run in runs)
