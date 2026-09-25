"""Notizen eines gespeicherten Rezepts gehören in seinen PDF-Bericht.

Der Bericht konnte Notizen schon immer drucken - das Hauptfenster reichte sie
aber nie weiter. Erfahrungen wie „Ofen 10 Minuten länger“ fehlten deshalb in
jedem Bericht, der aus der Oberfläche entstand.
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


@pytest.fixture
def reports(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[dict[str, Any]]:
    """Fängt den Bericht ab und merkt sich, womit er geschrieben würde."""
    from PySide6.QtWidgets import QFileDialog

    from brotrechner.export import report

    written: list[dict[str, Any]] = []

    def fake_write(path: Path, analysis: object, **kwargs: Any) -> Path:
        del analysis
        written.append(kwargs)
        return path

    monkeypatch.setattr(report, "write_report", fake_write)
    target = str(tmp_path / "bericht.pdf")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *_a, **_k: (target, ""))
    return written


def test_the_notes_of_the_recipe_are_in_the_report(
    window: Any, reports: list[dict[str, Any]]
) -> None:
    flour = next(i for i in window._ingredients if i.is_flour)
    recipe = Recipe(
        name="Roggenbrot",
        items=[RecipeItem(flour.key, flour.name, flour.manufacturer, 500.0)],
        baked_weight_g=400.0,
        notes="Ofen 10 Minuten länger",
    )
    window._recipes.add(recipe)
    window.page_calculator.load_recipe(recipe)
    window._on_report()
    assert reports == [{"recipe_name": "Roggenbrot", "notes": "Ofen 10 Minuten länger"}]


def test_an_unsaved_recipe_has_no_notes(window: Any, reports: list[dict[str, Any]]) -> None:
    flour = next(i for i in window._ingredients if i.is_flour)
    page = window.page_calculator
    page._items_model.add_item(flour, 500.0)
    page.spin_baked.setValue(400.0)
    page._recalculate()
    window._on_report()
    assert reports == [{"recipe_name": "Unbenanntes Rezept", "notes": ""}]
