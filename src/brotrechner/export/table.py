"""CSV-Ausgabe der Zutatendatenbank und der Rezeptauswertung.

Erzeugt wird bewusst das in Deutschland tabellenkalkulationsübliche Format:
Semikolon als Trennzeichen, Komma als Dezimaltrenner und UTF-8 **mit** BOM,
damit Excel die Umlaute ohne Nachfrage richtig anzeigt.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path

from brotrechner.core.allergens import describe_allergens
from brotrechner.core.analysis import RecipeAnalysis
from brotrechner.core.models import Ingredient
from brotrechner.i18n import format_number

__all__ = ["INGREDIENT_COLUMNS", "write_analysis_csv", "write_ingredients_csv"]

INGREDIENT_COLUMNS: tuple[str, ...] = (
    "Name",
    "Hersteller",
    "Kategorie",
    "Mehlanteil (%)",
    "Brennwert (kcal)",
    "Fett (g)",
    "dav. gesättigt (g)",
    "Kohlenhydrate (g)",
    "dav. Zucker (g)",
    "Ballaststoffe (g)",
    "Eiweiß (g)",
    "Salz (g)",
    "Wasser (%)",
    "Packungspreis (€)",
    "Packungsgröße (g)",
    "Preis je 100 g (€)",
    "Preisquelle",
    "Preisstand",
    "Notiz",
    "Bezeichnung im Zutatenverzeichnis",
    "Allergene",
)


def write_ingredients_csv(path: Path, ingredients: Iterable[Ingredient]) -> int:
    """Schreibt die Zutatendatenbank als CSV.

    Args:
        path: Zieldatei.
        ingredients: Zu exportierende Zutaten.

    Returns:
        Anzahl geschriebener Zeilen.

    Raises:
        OSError: Wenn die Datei nicht geschrieben werden kann.
    """
    rows = 0
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(INGREDIENT_COLUMNS)
        for ingredient in sorted(ingredients, key=lambda i: i.display_name.casefold()):
            n = ingredient.nutrients
            writer.writerow(
                [
                    ingredient.name,
                    ingredient.manufacturer,
                    ingredient.category.label,
                    format_number(ingredient.flour_percent, 1),
                    format_number(n.energy_kcal, 0),
                    format_number(n.fat),
                    format_number(n.saturated_fat),
                    format_number(n.carbs),
                    format_number(n.sugar),
                    format_number(n.fiber),
                    format_number(n.protein),
                    format_number(n.salt, 2),
                    format_number(n.water),
                    format_number(ingredient.package_price, 2),
                    format_number(ingredient.package_size_g, 0),
                    format_number(ingredient.price_per_100g, 3) if ingredient.has_price else "",
                    ingredient.price_source,
                    ingredient.price_updated.isoformat() if ingredient.price_updated else "",
                    ingredient.notes,
                    ingredient.label_name,
                    describe_allergens(ingredient.allergens),
                ]
            )
            rows += 1
    return rows


def write_analysis_csv(path: Path, analysis: RecipeAnalysis, *, recipe_name: str = "") -> int:
    """Schreibt die Zutatenzeilen einer Auswertung als CSV.

    Args:
        path: Zieldatei.
        analysis: Auswertung.
        recipe_name: Wird als erste Kommentarzeile ausgegeben.

    Returns:
        Anzahl geschriebener Zutatenzeilen.

    Raises:
        OSError: Wenn die Datei nicht geschrieben werden kann.
    """
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle, delimiter=";")
        if recipe_name:
            writer.writerow([f"Rezept: {recipe_name}"])
        writer.writerow(
            ["Zutat", "Hersteller", "Menge (g)", "Anteil (%)", "Bäcker (%)", "Kosten (€)", "Stufe"]
        )
        for line in analysis.lines:
            writer.writerow(
                [
                    line.ingredient.name,
                    line.ingredient.manufacturer,
                    format_number(line.amount_g),
                    format_number(line.share_percent),
                    format_number(line.baker_percent, 0),
                    format_number(line.cost, 2) if line.has_price else "",
                    line.stage.label,
                ]
            )
        writer.writerow([])
        writer.writerow(["Rohteig (g)", format_number(analysis.dough_weight_g, 0)])
        writer.writerow(["Gebacken (g)", format_number(analysis.baked_weight_g, 0)])
        writer.writerow(["Teigausbeute", format_number(analysis.dough_yield, 0)])
        writer.writerow(["Gesamtkosten (€)", format_number(analysis.total_cost, 2)])
    return len(analysis.lines)
