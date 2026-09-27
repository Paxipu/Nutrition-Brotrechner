"""Rückfrage, bevor ungespeicherte Änderungen im Rechner verloren gehen.

„Neu / leeren“, das Laden eines anderen Rezepts und das Beenden verwarfen den
Inhalt des Rechners bisher ohne ein Wort - eine halbe Stunde Rezeptarbeit war
mit einem Klick weg.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.gui


@pytest.fixture
def window(qapp: object, data_dir: Path, dialogs: dict[str, object]):  # type: ignore[no-untyped-def]
    del qapp, dialogs
    from brotrechner.gui.main_window import MainWindow

    widget = MainWindow(data_dir=data_dir)
    yield widget
    # Aufräumen ohne Rückfrage, egal was der Test hinterlassen hat.
    widget.page_calculator.clear()
    widget.close()


def _fill(window: Any, grams: float = 1000.0) -> None:
    """Trägt Mehl ein - ungespeichert."""
    flour = next(i for i in window._ingredients if i.is_flour)
    page = window.page_calculator
    page._items_model.add_item(flour, grams)
    page.spin_baked.setValue(800.0)
    page._recalculate()


def _answer(dialogs: dict[str, object], button: str) -> None:
    from PySide6.QtWidgets import QMessageBox

    dialogs["button"] = int(getattr(QMessageBox.StandardButton, button))


def _asked(monkeypatch: pytest.MonkeyPatch, dialogs: dict[str, object]) -> list[str]:
    """Zeichnet die Titel aller Rückfragen auf und beantwortet sie wie ``dialogs``."""
    from PySide6.QtWidgets import QMessageBox

    titles: list[str] = []

    def question(_parent: object, title: str, *_args: object, **_kwargs: object) -> object:
        titles.append(title)
        return dialogs["button"]

    monkeypatch.setattr(QMessageBox, "question", question)
    return titles


class TestTheCalculatorKnowsWhatIsSaved:
    def test_an_empty_calculator_has_nothing_to_lose(self, window: Any) -> None:
        assert not window.page_calculator.has_unsaved_changes

    def test_entering_something_is_a_change(self, window: Any) -> None:
        _fill(window)
        assert window.page_calculator.has_unsaved_changes

    def test_a_loaded_recipe_is_unchanged(self, window: Any) -> None:
        from brotrechner.core.models import Recipe, RecipeItem

        flour = next(i for i in window._ingredients if i.is_flour)
        recipe = Recipe(
            name="Gespeichert",
            items=[RecipeItem(flour.key, flour.name, flour.manufacturer, 500.0)],
            baked_weight_g=400.0,
        )
        window.page_calculator.load_recipe(recipe)
        assert not window.page_calculator.has_unsaved_changes
        window.page_calculator.spin_baked.setValue(410.0)
        assert window.page_calculator.has_unsaved_changes

    def test_clearing_leaves_nothing_to_lose(self, window: Any) -> None:
        _fill(window)
        window.page_calculator.clear()
        assert not window.page_calculator.has_unsaved_changes

    def test_a_new_price_in_the_database_is_no_change(self, window: Any) -> None:
        from brotrechner.core.models import Recipe, RecipeItem

        flour = next(i for i in window._ingredients if i.is_flour)
        window.page_calculator.load_recipe(
            Recipe(
                name="R",
                items=[RecipeItem(flour.key, flour.name, flour.manufacturer, 500.0)],
                baked_weight_g=400.0,
            )
        )
        window.page_calculator.set_ingredients(list(window._ingredients))
        assert not window.page_calculator.has_unsaved_changes


class TestNewRecipe:
    def test_nothing_is_asked_without_changes(
        self, window: Any, dialogs: dict[str, object], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        asked = _asked(monkeypatch, dialogs)
        window._on_new_recipe()
        assert asked == []

    def test_cancel_keeps_the_work(
        self, window: Any, dialogs: dict[str, object], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _fill(window)
        asked = _asked(monkeypatch, dialogs)
        _answer(dialogs, "Cancel")
        window._on_new_recipe()
        assert asked == ["Ungespeicherte Änderungen"]
        assert window.page_calculator._items_model.items

    def test_discard_clears(
        self, window: Any, dialogs: dict[str, object], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _fill(window)
        _asked(monkeypatch, dialogs)
        _answer(dialogs, "Discard")
        window._on_new_recipe()
        assert not window.page_calculator._items_model.items

    def test_save_saves_first(
        self,
        window: Any,
        dialogs: dict[str, object],
        monkeypatch: pytest.MonkeyPatch,
        data_dir: Path,
    ) -> None:
        from brotrechner.data.repository import load_ingredients, load_recipes

        _fill(window)
        _asked(monkeypatch, dialogs)
        _answer(dialogs, "Save")
        dialogs["name"] = "Vor dem Leeren"
        window._on_new_recipe()
        assert not window.page_calculator._items_model.items
        ingredients, _ = load_ingredients(data_dir / "ingredients.json")
        recipes, _ = load_recipes(data_dir / "recipes.json", ingredients)
        assert "Vor dem Leeren" in recipes

    def test_a_cancelled_save_keeps_the_work(
        self,
        window: Any,
        dialogs: dict[str, object],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Wer beim Namen abbricht, will auch nicht leeren."""
        from PySide6.QtWidgets import QInputDialog

        _fill(window)
        _asked(monkeypatch, dialogs)
        _answer(dialogs, "Save")
        monkeypatch.setattr(QInputDialog, "getText", lambda *_a, **_k: ("", False))
        window._on_new_recipe()
        assert window.page_calculator._items_model.items


class TestLoadingAnotherRecipe:
    def test_cancel_keeps_the_work(
        self, window: Any, dialogs: dict[str, object], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from brotrechner.core.models import Recipe, RecipeItem

        flour = next(i for i in window._ingredients if i.is_flour)
        other = Recipe(
            name="Anderes",
            items=[RecipeItem(flour.key, flour.name, flour.manufacturer, 300.0)],
            baked_weight_g=250.0,
        )
        window._recipes.add(other)
        _fill(window, grams=1234.0)
        asked = _asked(monkeypatch, dialogs)
        _answer(dialogs, "Cancel")
        window._on_load_recipe("Anderes")
        assert asked == ["Ungespeicherte Änderungen"]
        assert [i.amount_g for i in window.page_calculator._items_model.items] == [1234.0]


class TestClosing:
    def test_cancel_keeps_the_window_open(
        self, window: Any, dialogs: dict[str, object], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _fill(window)
        _asked(monkeypatch, dialogs)
        _answer(dialogs, "Cancel")
        assert not window.close()

    def test_discard_closes(
        self, window: Any, dialogs: dict[str, object], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _fill(window)
        _asked(monkeypatch, dialogs)
        _answer(dialogs, "Discard")
        assert window.close()

    def test_without_changes_it_just_closes(
        self, window: Any, dialogs: dict[str, object], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        asked = _asked(monkeypatch, dialogs)
        assert window.close()
        assert asked == []
