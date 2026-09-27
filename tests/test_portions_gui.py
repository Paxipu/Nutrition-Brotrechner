"""Portionen im Rechner: eingeben, anzeigen, speichern."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from brotrechner.core.models import Ingredient, Recipe
from brotrechner.core.portions import Portion

pytestmark = pytest.mark.gui


@pytest.fixture
def page(qapp: object, flour: Ingredient, water: Ingredient, salt: Ingredient):  # type: ignore[no-untyped-def]
    del qapp
    from brotrechner.gui.pages.calculator import CalculatorPage
    from brotrechner.gui.theme import ThemeMode, resolve_tokens

    widget = CalculatorPage(resolve_tokens(ThemeMode.LIGHT))
    widget.set_ingredients([flour, water, salt])
    return widget


def _fill(page: Any, simple_recipe: Recipe) -> None:
    page.load_recipe(simple_recipe)


def _switch_visible(page: Any) -> bool:
    return bool(page.basis_row.isVisibleTo(page))


def _set_portion(page: Any, name: str, grams: float) -> None:
    page.cmb_portion.setEditText(name)
    page.spin_portion.setValue(grams)
    page._recalculate()


class TestInput:
    def test_nothing_per_portion_by_default(self, page: Any, simple_recipe: Recipe) -> None:
        _fill(page, simple_recipe)
        assert page.portion is None
        assert page.analysis.portion is None
        assert not _switch_visible(page)

    def test_a_portion_reaches_the_analysis(self, page: Any, simple_recipe: Recipe) -> None:
        _fill(page, simple_recipe)
        _set_portion(page, "Scheibe", 50.0)
        assert page.analysis.portion == Portion("Scheibe", 50.0)

    def test_the_names_are_suggested(self, page: Any) -> None:
        names = [page.cmb_portion.itemText(i) for i in range(page.cmb_portion.count())]
        assert names[:2] == ["Scheibe", "Stück"]

    def test_the_count_is_shown(self, page: Any, simple_recipe: Recipe) -> None:
        _fill(page, simple_recipe)
        _set_portion(page, "Scheibe", 50.0)
        assert page.lbl_portion.text() == "ergibt 30 Scheiben"

    def test_without_a_baked_weight_there_is_no_count(
        self, page: Any, simple_recipe: Recipe
    ) -> None:
        _fill(page, simple_recipe)
        page.spin_baked.setValue(0.0)
        _set_portion(page, "Scheibe", 50.0)
        assert page.lbl_portion.text() == ""

    def test_a_portion_heavier_than_the_bread_is_flagged(
        self, page: Any, simple_recipe: Recipe
    ) -> None:
        _fill(page, simple_recipe)
        _set_portion(page, "Scheibe", 2000.0)
        assert page.lbl_portion.text() == ""
        assert "wiegt mehr als das ganze Brot" in page.lbl_process.text()
        assert page.lbl_process.isVisibleTo(page)


class TestDisplay:
    """Die Tafel schaltet zwischen je 100 g und je Portion um.

    Eine eigene Spalte je Portion machte die Tafel breiter als die
    Auswertungsspalte - dort war schon vorher kaum Platz.
    """

    def test_the_switch_carries_the_portion(self, page: Any, simple_recipe: Recipe) -> None:
        _fill(page, simple_recipe)
        _set_portion(page, "Scheibe", 50.0)
        assert _switch_visible(page)
        assert page.rb_per_portion.text() == "je Scheibe (50 g)"
        assert page.rb_per_100g.isChecked()

    def test_values_per_portion(self, page: Any, simple_recipe: Recipe) -> None:
        from brotrechner.core.rounding import declare_energy

        _fill(page, simple_recipe)
        _set_portion(page, "Scheibe", 50.0)
        page.rb_per_portion.setChecked(True)
        panel = page.nutrition
        per_portion = page.analysis.per_portion
        assert panel._value_header.text() == "je Scheibe (50 g)"
        assert page.nutrition_card._title.text() == "Nährwerte je Scheibe (50 g)"
        assert panel._value_labels["energy_kcal"].text() == declare_energy(per_portion.energy_kcal)
        assert "Angabe auf dem Etikett" in panel._value_labels["salt"].toolTip()

    def test_the_reference_intake_is_per_portion(self, page: Any, simple_recipe: Recipe) -> None:
        from brotrechner.core.reference import reference_intake_percent

        _fill(page, simple_recipe)
        _set_portion(page, "Scheibe", 50.0)
        page.rb_per_portion.setChecked(True)
        percent = reference_intake_percent("energy_kcal", page.analysis.per_portion.energy_kcal)
        assert page.nutrition._percent_labels["energy_kcal"].text() == f"{percent:.0f} %"

    def test_traffic_light_and_tolerances_stay_per_100g(
        self, page: Any, simple_recipe: Recipe
    ) -> None:
        """Für Ampel und Toleranzen gibt es nur den Bezug auf 100 g."""
        from brotrechner.core.reference import traffic_light

        _fill(page, simple_recipe)
        # So groß, dass die Ampel je Portion anders stünde als je 100 g.
        _set_portion(page, "Stück", 150.0)
        page.rb_per_portion.setChecked(True)
        panel = page.nutrition
        salt = page.analysis.per_100g.salt
        assert traffic_light("salt", page.analysis.per_portion.salt) is not traffic_light(
            "salt", salt
        )
        assert panel._dots["salt"]._level is traffic_light("salt", salt)
        assert not panel._range_header.isVisibleTo(panel)
        assert not page.chk_ranges.isEnabled()

    def test_back_to_100g(self, page: Any, simple_recipe: Recipe) -> None:
        _fill(page, simple_recipe)
        _set_portion(page, "Scheibe", 50.0)
        page.rb_per_portion.setChecked(True)
        page.rb_per_100g.setChecked(True)
        assert page.nutrition._value_header.text() == "je 100 g"
        assert page.nutrition._range_header.isVisibleTo(page.nutrition)
        assert page.nutrition_card._title.text() == "Nährwerte je 100 g gebacken"

    def test_removing_the_portion_returns_to_100g(self, page: Any, simple_recipe: Recipe) -> None:
        _fill(page, simple_recipe)
        _set_portion(page, "Scheibe", 50.0)
        page.rb_per_portion.setChecked(True)
        _set_portion(page, "Scheibe", 0.0)
        assert not _switch_visible(page)
        assert page.nutrition._value_header.text() == "je 100 g"

    def test_the_cost_per_portion(self, page: Any, simple_recipe: Recipe) -> None:
        from brotrechner.i18n import format_currency

        _fill(page, simple_recipe)
        _set_portion(page, "Scheibe", 50.0)
        text = page.lbl_cost.text()
        assert "Preis je Scheibe (50 g)" in text
        assert format_currency(page.analysis.cost_per_portion) in text


class TestRecipe:
    def test_it_is_part_of_the_recipe(self, page: Any, simple_recipe: Recipe) -> None:
        _fill(page, simple_recipe)
        _set_portion(page, "Brötchen", 75.0)
        assert page.to_recipe().portion == Portion("Brötchen", 75.0)

    def test_loading_restores_it(self, page: Any, simple_recipe: Recipe) -> None:
        simple_recipe.portion = Portion("Stück", 120.0)
        page.load_recipe(simple_recipe)
        assert page.cmb_portion.currentText() == "Stück"
        assert page.spin_portion.value() == 120.0
        assert page.analysis.portion == Portion("Stück", 120.0)

    def test_a_recipe_without_portion_clears_it(self, page: Any, simple_recipe: Recipe) -> None:
        _fill(page, simple_recipe)
        _set_portion(page, "Stück", 120.0)
        page.load_recipe(simple_recipe)
        assert page.portion is None

    def test_clearing_removes_it(self, page: Any, simple_recipe: Recipe) -> None:
        _fill(page, simple_recipe)
        _set_portion(page, "Stück", 120.0)
        page.clear()
        assert page.portion is None
        assert page.cmb_portion.currentText() == "Scheibe"

    def test_a_changed_portion_is_an_unsaved_change(self, page: Any, simple_recipe: Recipe) -> None:
        _fill(page, simple_recipe)
        assert not page.has_unsaved_changes
        _set_portion(page, "Scheibe", 50.0)
        assert page.has_unsaved_changes

    def test_the_name_alone_is_no_change(self, page: Any, simple_recipe: Recipe) -> None:
        """Ohne Gewicht gibt es keine Portion - ihr Name allein ändert nichts."""
        _fill(page, simple_recipe)
        page.cmb_portion.setEditText("Brötchen")
        assert not page.has_unsaved_changes


def test_a_saved_recipe_keeps_its_portion(
    qapp: object, data_dir: Path, dialogs: dict[str, object]
) -> None:
    del qapp
    from brotrechner.gui.main_window import MainWindow

    window = MainWindow(data_dir=data_dir)
    try:
        flour = next(i for i in window._ingredients if i.is_flour)
        page = window.page_calculator
        page._items_model.add_item(flour, 500.0)
        page.spin_baked.setValue(400.0)
        _set_portion(page, "Scheibe", 40.0)
        dialogs["name"] = "Mit Scheiben"
        assert window._on_save_recipe()
        saved = json.loads((data_dir / "recipes.json").read_text(encoding="utf-8"))
        (entry,) = [r for r in saved["recipes"] if r["name"] == "Mit Scheiben"]
        assert entry["portion"] == {"name": "Scheibe", "weight_g": 40.0}
    finally:
        window.page_calculator.clear()
        window.close()


def test_the_recipe_preview_names_the_portion(
    qapp: object, simple_recipe: Recipe, flour: Ingredient, water: Ingredient, salt: Ingredient
) -> None:
    del qapp
    from brotrechner.gui.pages.recipes import RecipesPage
    from brotrechner.gui.theme import ThemeMode, resolve_tokens

    simple_recipe.portion = Portion("Scheibe", 50.0)
    page = RecipesPage(resolve_tokens(ThemeMode.LIGHT))
    page.set_data([simple_recipe], [flour, water, salt])
    assert page.select_recipe(simple_recipe.name)
    text = page.lbl_preview.text()
    assert "Je Scheibe (50 g)" in text
    assert "ergibt 30 Scheiben" in text


def test_the_recipe_preview_without_portion(
    qapp: object, simple_recipe: Recipe, flour: Ingredient, water: Ingredient, salt: Ingredient
) -> None:
    del qapp
    from brotrechner.gui.pages.recipes import RecipesPage
    from brotrechner.gui.theme import ThemeMode, resolve_tokens

    page = RecipesPage(resolve_tokens(ThemeMode.LIGHT))
    page.set_data([simple_recipe], [flour, water, salt])
    assert page.select_recipe(simple_recipe.name)
    assert "Je Scheibe" not in page.lbl_preview.text()
