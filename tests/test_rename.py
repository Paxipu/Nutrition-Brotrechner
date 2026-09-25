"""Rezepte umbenennen.

Namen gelten ohne Rücksicht auf Groß- und Kleinschreibung als gleich. Wer
„roggenbrot“ in „Roggenbrot“ umbenennen wollte, bekam deshalb „Es gibt bereits
ein Rezept namens …“ - gemeint war das Rezept selbst.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from brotrechner.core.models import Recipe, RecipeItem

pytestmark = pytest.mark.gui


@pytest.fixture
def window(qapp: object, data_dir: Path, dialogs: dict[str, object]):  # type: ignore[no-untyped-def]
    del qapp, dialogs
    from brotrechner.gui.main_window import MainWindow

    widget = MainWindow(data_dir=data_dir)
    yield widget
    widget.page_calculator.clear()
    widget.close()


def _recipe(window: Any, name: str) -> Recipe:
    flour = next(i for i in window._ingredients if i.is_flour)
    recipe = Recipe(
        name=name,
        items=[RecipeItem(flour.key, flour.name, flour.manufacturer, 500.0)],
        baked_weight_g=400.0,
    )
    window._recipes.add(recipe)
    window._save_recipes()
    return recipe


def _names_on_disk(data_dir: Path) -> list[str]:
    from brotrechner.data.repository import load_ingredients, load_recipes

    ingredients, _ = load_ingredients(data_dir / "ingredients.json")
    recipes, _ = load_recipes(data_dir / "recipes.json", ingredients)
    return sorted(r.name for r in recipes)


def test_only_the_capitals_change(window: Any, dialogs: dict[str, object], data_dir: Path) -> None:
    _recipe(window, "roggenbrot")
    dialogs["name"] = "Roggenbrot"
    window._on_rename_recipe("roggenbrot")
    assert _names_on_disk(data_dir) == ["Roggenbrot"]


def test_another_recipe_of_that_name_is_still_protected(
    window: Any, dialogs: dict[str, object], data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PySide6.QtWidgets import QMessageBox

    warned: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, title, *_a: warned.append(title))
    _recipe(window, "Roggenbrot")
    _recipe(window, "Weizenbrot")
    dialogs["name"] = "roggenbrot"
    window._on_rename_recipe("Weizenbrot")
    assert warned == ["Name vergeben"]
    assert _names_on_disk(data_dir) == ["Roggenbrot", "Weizenbrot"]


def test_the_calculator_follows_the_new_name(window: Any, dialogs: dict[str, object]) -> None:
    """Sonst legte das nächste Speichern ein Duplikat unter dem alten Namen an."""
    recipe = _recipe(window, "Roggenbrot")
    window.page_calculator.load_recipe(recipe)
    dialogs["name"] = "Roggenmischbrot"
    window._on_rename_recipe("Roggenbrot")
    assert window.page_calculator.txt_name.text() == "Roggenmischbrot"
    assert not window.page_calculator.has_unsaved_changes


def test_changes_in_the_calculator_stay_unsaved(window: Any, dialogs: dict[str, object]) -> None:
    recipe = _recipe(window, "Roggenbrot")
    window.page_calculator.load_recipe(recipe)
    window.page_calculator.spin_baked.setValue(410.0)
    dialogs["name"] = "Roggenmischbrot"
    window._on_rename_recipe("Roggenbrot")
    assert window.page_calculator.has_unsaved_changes


def test_another_recipe_in_the_calculator_is_left_alone(
    window: Any, dialogs: dict[str, object]
) -> None:
    _recipe(window, "Roggenbrot")
    other = _recipe(window, "Weizenbrot")
    window.page_calculator.load_recipe(other)
    dialogs["name"] = "Roggenmischbrot"
    window._on_rename_recipe("Roggenbrot")
    assert window.page_calculator.txt_name.text() == "Weizenbrot"
