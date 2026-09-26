"""Rezeptstufen im Rechner: Die Stufe einer Zutat geht nirgends verloren."""

from __future__ import annotations

from typing import Any

import pytest

from brotrechner.core.models import Ingredient, Recipe, RecipeItem, Stage

pytestmark = pytest.mark.gui


@pytest.fixture
def page(qapp: object, flour: Ingredient, water: Ingredient, salt: Ingredient):  # type: ignore[no-untyped-def]
    del qapp
    from brotrechner.gui.pages.calculator import CalculatorPage
    from brotrechner.gui.theme import ThemeMode, resolve_tokens

    widget = CalculatorPage(resolve_tokens(ThemeMode.LIGHT))
    widget.set_ingredients([flour, water, salt])
    return widget


@pytest.fixture
def staged(flour: Ingredient, water: Ingredient, salt: Ingredient) -> Recipe:
    """Roggenbrot mit Sauerteig: Mehl und Wasser stehen in beiden Stufen."""
    return Recipe(
        name="Roggenbrot",
        items=[
            RecipeItem(flour.key, flour.name, flour.manufacturer, 200.0, Stage.SOURDOUGH),
            RecipeItem(water.key, water.name, water.manufacturer, 200.0, Stage.SOURDOUGH),
            RecipeItem(flour.key, flour.name, flour.manufacturer, 300.0),
            RecipeItem(water.key, water.name, water.manufacturer, 150.0),
            RecipeItem(salt.key, salt.name, salt.manufacturer, 10.0),
        ],
        baked_weight_g=750.0,
    )


def _stages(page: Any) -> list[Stage]:
    return [item.stage for item in page._items_model.items]


class TestKeepingTheStage:
    def test_loading_and_saving(self, page: Any, staged: Recipe) -> None:
        page.load_recipe(staged)
        assert _stages(page) == [item.stage for item in staged.items]
        assert page.to_recipe().items == staged.items

    def test_a_new_price_keeps_the_stage(
        self, page: Any, staged: Recipe, flour: Ingredient, water: Ingredient, salt: Ingredient
    ) -> None:
        page.load_recipe(staged)
        page.set_ingredients([flour, water, salt])
        assert _stages(page) == [item.stage for item in staged.items]

    def test_a_new_amount_keeps_the_stage(self, page: Any, staged: Recipe) -> None:
        page.load_recipe(staged)
        model = page._items_model
        assert model.setData(model.index(0, _amount_column()), 250.0)
        assert model.items[0].stage is Stage.SOURDOUGH
        assert model.items[0].amount_g == 250.0

    def test_the_analysis_knows_the_stages(self, page: Any, staged: Recipe) -> None:
        page.load_recipe(staged)
        assert [summary.stage for summary in page.analysis.stages] == [
            Stage.SOURDOUGH,
            Stage.MAIN,
        ]


class TestAdding:
    def test_the_same_ingredient_in_another_stage_is_a_new_line(
        self, page: Any, flour: Ingredient
    ) -> None:
        model = page._items_model
        model.add_item(flour, 300.0)
        model.add_item(flour, 200.0, Stage.SOURDOUGH)
        assert [(item.amount_g, item.stage) for item in model.items] == [
            (200.0, Stage.SOURDOUGH),
            (300.0, Stage.MAIN),
        ], "Vorstufen stehen vor dem Hauptteig"

    def test_the_same_ingredient_in_the_same_stage_is_added_up(
        self, page: Any, flour: Ingredient
    ) -> None:
        model = page._items_model
        model.add_item(flour, 200.0, Stage.SOURDOUGH)
        model.add_item(flour, 50.0, Stage.SOURDOUGH)
        assert [(item.amount_g, item.stage) for item in model.items] == [(250.0, Stage.SOURDOUGH)]


def _amount_column() -> int:
    from brotrechner.gui.models.recipe_model import RECIPE_COLUMNS

    return [title for title, *_ in RECIPE_COLUMNS].index("Menge (g)")
