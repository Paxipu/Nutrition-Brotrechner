"""Fachlogik ohne Oberflächen- oder Dateiabhängigkeiten.

Alles in diesem Paket ist rein funktional bzw. auf unveränderlichen
Datenklassen aufgebaut und damit direkt testbar.
"""

from __future__ import annotations

from brotrechner.core.analysis import (
    IngredientLine,
    RecipeAnalysis,
    ResolvedItem,
    analyze,
    resolve_items,
)
from brotrechner.core.models import (
    CATEGORY_LABELS,
    Category,
    Ingredient,
    PriceEntry,
    Recipe,
    RecipeItem,
    Source,
)
from brotrechner.core.nutrients import Nutrients, energy_from_macros
from brotrechner.core.reference import AmpelLevel, reference_intake_percent, traffic_light
from brotrechner.core.tolerances import ValueRange, nutrient_ranges, tolerance_for
from brotrechner.core.validation import Finding, Severity, validate_database, validate_ingredient

__all__ = [
    "CATEGORY_LABELS",
    "AmpelLevel",
    "Category",
    "Finding",
    "Ingredient",
    "IngredientLine",
    "Nutrients",
    "PriceEntry",
    "Recipe",
    "RecipeAnalysis",
    "RecipeItem",
    "ResolvedItem",
    "Severity",
    "Source",
    "ValueRange",
    "analyze",
    "energy_from_macros",
    "nutrient_ranges",
    "reference_intake_percent",
    "resolve_items",
    "tolerance_for",
    "traffic_light",
    "validate_database",
    "validate_ingredient",
]
