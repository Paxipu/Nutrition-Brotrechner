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


def _stage_column() -> int:
    from brotrechner.gui.models.recipe_model import RECIPE_COLUMNS

    return [title for title, *_ in RECIPE_COLUMNS].index("Stufe")


class TestStageColumn:
    """Die Spalte „Stufe“ erscheint erst, wenn das Rezept Stufen hat.

    Die meisten Brote haben nur einen Hauptteig - dort wäre sie nur Platz,
    der der Zutatenspalte fehlt.
    """

    def test_hidden_without_stages(self, page: Any, flour: Ingredient) -> None:
        page._items_model.add_item(flour, 500.0)
        assert page.table.isColumnHidden(_stage_column())

    def test_shown_with_stages(self, page: Any, staged: Recipe) -> None:
        page.load_recipe(staged)
        assert not page.table.isColumnHidden(_stage_column())
        model = page._items_model
        assert model.data(model.index(0, _stage_column())) == "Sauerteig"
        assert model.data(model.index(2, _stage_column())) == "Hauptteig"


class TestChooser:
    def test_every_stage_is_offered(self, page: Any) -> None:
        labels = [page.cmb_stage.itemText(i) for i in range(page.cmb_stage.count())]
        assert labels == [stage.label for stage in Stage]
        assert page.cmb_stage.currentData() is Stage.MAIN

    def test_adding_uses_the_chosen_stage(self, page: Any, flour: Ingredient) -> None:
        from brotrechner.gui.qt_compat import select_data

        select_data(page.cmb_stage, Stage.SOURDOUGH)
        assert page.picker.select_key(flour.key)
        page.spin_amount.setValue(200.0)
        page._on_add()
        assert [(item.amount_g, item.stage) for item in page._items_model.items] == [
            (200.0, Stage.SOURDOUGH)
        ]
        assert page.cmb_stage.currentData() is Stage.SOURDOUGH, "bleibt für die nächste Zutat"


class TestMovingRows:
    def test_rows_move_into_a_stage(self, page: Any, flour: Ingredient, water: Ingredient) -> None:
        model = page._items_model
        model.add_item(flour, 300.0)
        model.add_item(water, 200.0)
        model.set_stage([1], Stage.SOURDOUGH)
        assert [(item.ingredient.key, item.stage) for item in model.items] == [
            (water.key, Stage.SOURDOUGH),
            (flour.key, Stage.MAIN),
        ]

    def test_the_same_ingredient_is_added_up(self, page: Any, flour: Ingredient) -> None:
        model = page._items_model
        model.add_item(flour, 200.0, Stage.SOURDOUGH)
        model.add_item(flour, 300.0)
        model.set_stage([1], Stage.SOURDOUGH)
        assert [(item.amount_g, item.stage) for item in model.items] == [(500.0, Stage.SOURDOUGH)]

    def test_rows_outside_the_table_are_ignored(self, page: Any, flour: Ingredient) -> None:
        model = page._items_model
        model.add_item(flour, 300.0)
        model.set_stage([5, -1], Stage.SCALD)
        assert [item.stage for item in model.items] == [Stage.MAIN]

    def test_the_context_menu_moves_the_selection(
        self, page: Any, flour: Ingredient, water: Ingredient
    ) -> None:
        model = page._items_model
        model.add_item(flour, 300.0)
        model.add_item(water, 200.0)
        page.table.selectRow(0)
        menu = page._stage_menu()
        (action,) = [a for a in menu.actions() if a.text() == "Vorteig"]
        action.trigger()
        assert [item.stage for item in model.items] == [Stage.PREFERMENT, Stage.MAIN]

    def test_the_current_stage_is_marked(self, page: Any, staged: Recipe) -> None:
        page.load_recipe(staged)
        page.table.selectRow(0)
        checked = [a.text() for a in page._stage_menu().actions() if a.isChecked()]
        assert checked == ["Sauerteig"]

    def test_without_a_selection_there_is_no_menu(self, page: Any, flour: Ingredient) -> None:
        page._items_model.add_item(flour, 300.0)
        page.table.clearSelection()
        assert page._stage_menu() is None

    def test_a_new_stage_is_an_unsaved_change(self, page: Any, staged: Recipe) -> None:
        page.load_recipe(staged)
        page._items_model.set_stage([4], Stage.SOAKER)
        assert page.has_unsaved_changes


class TestBakingText:
    def test_each_stage_is_described(self, page: Any, staged: Recipe) -> None:
        page.load_recipe(staged)
        text = page.lbl_baking.text()
        assert "Sauerteig: 400 g, TA 200, 40 % des Mehls" in text
        assert "Hauptteig: 460 g, TA 150, 60 % des Mehls" in text

    def test_a_stage_without_flour(self, page: Any, water: Ingredient, flour: Ingredient) -> None:
        model = page._items_model
        model.add_item(flour, 500.0)
        model.add_item(water, 100.0, Stage.SCALD)
        page.spin_baked.setValue(500.0)
        page._recalculate()
        assert "Brühstück: 100 g, ohne Mehl" in page.lbl_baking.text()

    def test_without_stages_nothing_is_added(self, page: Any, flour: Ingredient) -> None:
        page._items_model.add_item(flour, 500.0)
        page._recalculate()
        assert "Hauptteig:" not in page.lbl_baking.text()


def _manufacturer_column() -> int:
    from brotrechner.gui.models.recipe_model import RECIPE_COLUMNS

    return [title for title, *_ in RECIPE_COLUMNS].index("Hersteller")


class TestManufacturerColumn:
    """Mit der Spalte „Stufe“ wurde es eng: „Roggen…“ statt des Mehls.

    Die Herstellerspalte zeigte dabei meist nur „—“. Sie erscheint jetzt wie
    die Stufe nur, wenn sie etwas zu sagen hat.
    """

    def test_hidden_when_no_ingredient_has_one(self, page: Any, water: Ingredient) -> None:
        assert not water.manufacturer
        page._items_model.add_item(water, 300.0)
        assert page.table.isColumnHidden(_manufacturer_column())

    def test_shown_when_one_has(self, page: Any, water: Ingredient, flour: Ingredient) -> None:
        assert flour.manufacturer
        page._items_model.add_item(water, 300.0)
        page._items_model.add_item(flour, 500.0)
        assert not page.table.isColumnHidden(_manufacturer_column())

    def test_hidden_again_when_it_is_removed(
        self, page: Any, water: Ingredient, flour: Ingredient
    ) -> None:
        page._items_model.add_item(water, 300.0)
        page._items_model.add_item(flour, 500.0)
        page._items_model.remove_rows([1])
        assert page.table.isColumnHidden(_manufacturer_column())
