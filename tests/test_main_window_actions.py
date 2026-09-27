"""Aktionen des Hauptfensters: Zutaten pflegen, Import und Export, Skalieren, Aussehen.

Die Dialoge selbst sind an anderer Stelle geprüft. Hier geht es darum, was das
Hauptfenster mit ihrem Ergebnis macht - ob es gespeichert, angezeigt und bei
einem Fehler gemeldet wird.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from brotrechner.core.models import Category, Ingredient, Recipe, RecipeItem
from brotrechner.core.nutrients import Nutrients
from brotrechner.data import portable
from brotrechner.data.portable import ConflictPolicy
from brotrechner.data.repository import RepositoryError, load_ingredients, load_recipes

pytestmark = pytest.mark.gui


@pytest.fixture
def window(qapp: object, data_dir: Path, dialogs: dict[str, object]) -> Iterator[Any]:
    del qapp, dialogs
    from brotrechner.gui.main_window import MainWindow

    widget = MainWindow(data_dir=data_dir)
    yield widget
    widget.page_calculator.clear()
    widget.close()


@dataclass
class _Shown:
    """Was an Meldungen und Rückfragen erschien."""

    boxes: list[tuple[str, str, str]] = field(default_factory=list)
    """(Art, Titel, Text)"""

    def titles(self, kind: str | None = None) -> list[str]:
        return [title for shown, title, _ in self.boxes if kind in (None, shown)]

    def text(self, title: str) -> str:
        return next(text for _, shown_title, text in self.boxes if shown_title == title)


@pytest.fixture
def shown(monkeypatch: pytest.MonkeyPatch, dialogs: dict[str, object]) -> _Shown:
    from PySide6.QtWidgets import QMessageBox

    record = _Shown()

    def recorder(kind: str) -> Any:
        def show(_parent: object, title: str, text: str = "", *_args: object) -> object:
            record.boxes.append((kind, title, text))
            return dialogs["button"]

        return show

    for kind in ("information", "warning", "critical", "question"):
        monkeypatch.setattr(QMessageBox, kind, recorder(kind))
    return record


def _stub_dialog(
    monkeypatch: pytest.MonkeyPatch, name: str, *, accept: bool, **results: Any
) -> list[dict[str, Any]]:
    """Ersetzt einen Dialog des Hauptfensters; liefert die Aufrufe mit ihren Argumenten."""
    from PySide6.QtWidgets import QDialog

    calls: list[dict[str, Any]] = []

    class _Stub:
        DialogCode = QDialog.DialogCode

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            calls.append({"args": args, **kwargs})
            for key, value in results.items():
                setattr(self, key, value)

        def exec(self) -> int:
            code = QDialog.DialogCode.Accepted if accept else QDialog.DialogCode.Rejected
            return int(code)

        def result_ingredient(self) -> Ingredient:
            return results["ingredient"]  # type: ignore[no-any-return]

    monkeypatch.setattr(f"brotrechner.gui.main_window.{name}", _Stub)
    return calls


def _saved_ingredients(data_dir: Path) -> dict[str, Ingredient]:
    store, _ = load_ingredients(data_dir / "ingredients.json")
    return store.as_dict()


def _saved_recipes(data_dir: Path) -> list[str]:
    ingredients, _ = load_ingredients(data_dir / "ingredients.json")
    recipes, _ = load_recipes(data_dir / "recipes.json", ingredients)
    return [recipe.name for recipe in recipes]


EMMER = Ingredient(
    name="Emmervollkornmehl",
    manufacturer="Mühle Nord",
    category=Category.FLOUR,
    nutrients=Nutrients(energy_kcal=340, fat=2.5, carbs=64, protein=13, fiber=9, water=12),
    flour_percent=100.0,
)


class TestIngredientActions:
    def test_a_new_ingredient_is_saved_and_shown(
        self, window: Any, data_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = _stub_dialog(monkeypatch, "IngredientDialog", accept=True, ingredient=EMMER)
        window._on_create_ingredient()
        assert EMMER.key in _saved_ingredients(data_dir)
        assert window.nav.currentRow() == 1
        assert [i.key for i in window.page_ingredients.selected_ingredients()] == [EMMER.key]
        assert EMMER.key not in calls[0]["taken_keys"]

    def test_cancelling_creates_nothing(
        self, window: Any, data_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        before = len(window._ingredients)
        _stub_dialog(monkeypatch, "IngredientDialog", accept=False)
        window._on_create_ingredient()
        assert len(window._ingredients) == before

    def test_editing_replaces_the_ingredient(
        self, window: Any, data_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        original = next(iter(window._ingredients))
        changed = original.copy()
        changed.notes = "vom Bäcker nebenan"
        calls = _stub_dialog(monkeypatch, "IngredientDialog", accept=True, ingredient=changed)
        window._on_edit_ingredient(original.key)
        assert calls[0]["ingredient"] is original
        assert _saved_ingredients(data_dir)[original.key].notes == "vom Bäcker nebenan"

    def test_a_duplicate_keeps_the_original(
        self, window: Any, data_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        original = next(iter(window._ingredients))
        copy = original.copy(name=f"{original.name} hell")
        calls = _stub_dialog(monkeypatch, "IngredientDialog", accept=True, ingredient=copy)
        window._on_duplicate_ingredient(original.key)
        assert calls[0]["template"] is original
        saved = _saved_ingredients(data_dir)
        assert original.key in saved
        assert copy.key in saved

    def test_deleting_after_asking(self, window: Any, data_dir: Path, shown: _Shown) -> None:
        victim = next(iter(window._ingredients))
        window._on_delete_ingredient(victim.key)
        assert shown.titles("question") == ["Zutat löschen"]
        assert victim.key not in _saved_ingredients(data_dir)

    def test_saying_no_keeps_it(
        self, window: Any, shown: _Shown, dialogs: dict[str, object]
    ) -> None:
        from PySide6.QtWidgets import QMessageBox

        dialogs["button"] = int(QMessageBox.StandardButton.No)
        victim = next(iter(window._ingredients))
        window._on_delete_ingredient(victim.key)
        assert window._ingredients.get(victim.key) is not None

    def test_the_question_names_the_recipes_using_it(self, window: Any, shown: _Shown) -> None:
        victim = next(iter(window._ingredients))
        window._recipes.add(
            Recipe(
                name="Sonntagsbrot",
                items=[RecipeItem(victim.key, victim.name, victim.manufacturer, 100.0)],
            )
        )
        window._on_delete_ingredient(victim.key)
        text = shown.text("Zutat löschen")
        assert "in 1 Rezept(en) verwendet" in text
        assert "• Sonntagsbrot" in text


class TestImport:
    def _file(self, tmp_path: Path) -> Path:
        path = tmp_path / "tausch.json"
        portable.export_ingredients(path, [EMMER])
        return path

    def _choose(self, monkeypatch: pytest.MonkeyPatch, path: Path | None) -> None:
        from PySide6.QtWidgets import QFileDialog

        answer = (str(path), "") if path else ("", "")
        monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_a, **_k: answer)

    def test_new_ingredients_are_added(
        self, window: Any, data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._choose(monkeypatch, self._file(tmp_path))
        _stub_dialog(monkeypatch, "ImportDialog", accept=True, policy=ConflictPolicy.SKIP)
        window._on_import()
        assert EMMER.key in _saved_ingredients(data_dir)
        assert window.nav.currentRow() == 1

    def test_the_preview_can_be_declined(
        self, window: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._choose(monkeypatch, self._file(tmp_path))
        calls = _stub_dialog(monkeypatch, "ImportDialog", accept=False)
        window._on_import()
        assert calls[0]["args"][0].total == 1
        assert window._ingredients.get(EMMER.key) is None

    def test_no_file_no_import(self, window: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        self._choose(monkeypatch, None)
        calls = _stub_dialog(monkeypatch, "ImportDialog", accept=True)
        window._on_import()
        assert calls == []

    def test_a_broken_file_is_reported(
        self, window: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, shown: _Shown
    ) -> None:
        broken = tmp_path / "kaputt.json"
        broken.write_text("{ kein json", encoding="utf-8")
        self._choose(monkeypatch, broken)
        window._on_import()
        assert shown.titles("critical") == ["Import fehlgeschlagen"]


class TestExport:
    def _save_to(self, monkeypatch: pytest.MonkeyPatch, target: Path | None) -> None:
        from PySide6.QtWidgets import QFileDialog

        answer = (str(target), "") if target else ("", "")
        monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *_a, **_k: answer)

    def test_ingredients_as_json(
        self, window: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        chosen = list(window._ingredients)[:2]
        self._save_to(monkeypatch, tmp_path / "auswahl")
        window._on_export_ingredients(chosen)
        written = portable.parse_ingredient_file(tmp_path / "auswahl.json")
        assert [i.key for i in written] == [i.key for i in chosen]

    def test_a_failed_json_export_is_reported(
        self, window: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, shown: _Shown
    ) -> None:
        # Der Export legt fehlende Ordner an - also liegt dort eine Datei.
        (tmp_path / "belegt").write_text("x", encoding="utf-8")
        self._save_to(monkeypatch, tmp_path / "belegt" / "auswahl.json")
        window._on_export_ingredients(list(window._ingredients)[:1])
        assert shown.titles("critical") == ["Export fehlgeschlagen"]

    def test_no_file_no_export(
        self, window: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._save_to(monkeypatch, None)
        window._on_export_ingredients(list(window._ingredients)[:1])
        window._on_export_csv()
        assert list(tmp_path.glob("*.json")) == []
        assert list(tmp_path.glob("*.csv")) == []

    def test_the_database_as_csv(
        self, window: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from brotrechner.export.table import INGREDIENT_COLUMNS

        self._save_to(monkeypatch, tmp_path / "zutaten.csv")
        window._on_export_csv()
        with (tmp_path / "zutaten.csv").open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle, delimiter=";"))
        assert rows[0] == list(INGREDIENT_COLUMNS)
        assert len(rows) == len(window._ingredients) + 1

    def test_a_failed_csv_export_is_reported(
        self, window: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, shown: _Shown
    ) -> None:
        self._save_to(monkeypatch, tmp_path / "fehlt" / "zutaten.csv")
        window._on_export_csv()
        assert shown.titles("critical") == ["Export fehlgeschlagen"]


class TestScaling:
    def _bread(self, window: Any, *, baked: float = 800.0) -> Recipe:
        flour = next(i for i in window._ingredients if i.is_flour)
        recipe = Recipe(
            name="Brot",
            items=[RecipeItem(flour.key, flour.name, flour.manufacturer, 500.0)],
            baked_weight_g=baked,
        )
        window._recipes.add(recipe)
        return recipe

    def test_a_scaled_copy_is_saved(
        self, window: Any, data_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._bread(window)
        _stub_dialog(monkeypatch, "ScaleDialog", accept=True, factor=1.5)
        window._on_scale_recipe("Brot")
        scaled = window._recipes.get("Brot ×1,50")
        assert scaled is not None
        assert scaled.items[0].amount_g == pytest.approx(750.0)
        assert "Brot ×1,50" in _saved_recipes(data_dir)

    def test_the_new_name_is_unique(self, window: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        self._bread(window)
        window._recipes.add(Recipe(name="Brot ×1,50"))
        _stub_dialog(monkeypatch, "ScaleDialog", accept=True, factor=1.5)
        window._on_scale_recipe("Brot")
        assert window._recipes.get("Brot ×1,50 (2)") is not None

    def test_without_a_baked_weight_nothing_is_scaled(
        self, window: Any, monkeypatch: pytest.MonkeyPatch, shown: _Shown
    ) -> None:
        self._bread(window, baked=0.0)
        calls = _stub_dialog(monkeypatch, "ScaleDialog", accept=True, factor=2.0)
        window._on_scale_recipe("Brot")
        assert calls == []
        assert shown.titles("information") == ["Kein Bezugsgewicht"]

    def test_cancelling_scales_nothing(self, window: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        self._bread(window)
        count = len(list(window._recipes))
        _stub_dialog(monkeypatch, "ScaleDialog", accept=False, factor=2.0)
        window._on_scale_recipe("Brot")
        assert len(list(window._recipes)) == count


class TestLoadingARecipe:
    def test_missing_ingredients_are_named(self, window: Any, shown: _Shown) -> None:
        flour = next(i for i in window._ingredients if i.is_flour)
        window._recipes.add(
            Recipe(
                name="Alt",
                items=[
                    RecipeItem(flour.key, flour.name, flour.manufacturer, 500.0),
                    RecipeItem("weg|", "Verschollenes Mehl", "", 100.0),
                ],
                baked_weight_g=500.0,
            )
        )
        window._on_load_recipe("Alt")
        assert shown.titles("warning") == ["Zutaten fehlen"]
        assert "Verschollenes Mehl" in shown.text("Zutaten fehlen")
        assert [item.amount_g for item in window.page_calculator._items_model.items] == [500.0]

    def test_a_complete_recipe_loads_quietly(self, window: Any, shown: _Shown) -> None:
        flour = next(i for i in window._ingredients if i.is_flour)
        window._recipes.add(
            Recipe(
                name="Neu",
                items=[RecipeItem(flour.key, flour.name, flour.manufacturer, 500.0)],
                baked_weight_g=500.0,
            )
        )
        window._on_load_recipe("Neu")
        assert shown.boxes == []
        assert window.nav.currentRow() == 0
        assert "Rezept „Neu“ geladen" in window.statusBar().currentMessage()


class TestLookAndPages:
    def test_a_dark_theme(self, window: Any) -> None:
        from brotrechner.gui.theme import ThemeMode

        before = window.styleSheet()
        window._on_theme_changed(ThemeMode.DARK)
        assert window._settings.theme == ThemeMode.DARK.value
        checked = [action.text() for action in window._theme_actions if action.isChecked()]
        assert checked == [ThemeMode.DARK.label]
        assert window.styleSheet() != before

    def test_only_the_calculator_offers_recipe_actions(self, window: Any) -> None:
        window.nav.setCurrentRow(1)
        assert window.stack.currentIndex() == 1
        assert not window.btn_save_recipe.isVisibleTo(window)
        window.nav.setCurrentRow(0)
        assert window.btn_save_recipe.isVisibleTo(window)

    def test_an_unknown_page_is_ignored(self, window: Any) -> None:
        window._on_page_changed(7)
        assert window.stack.currentIndex() == 0

    def test_problems_in_the_database_are_counted(self, window: Any) -> None:
        window._ingredients.add(
            Ingredient(name="Kaputt", nutrients=Nutrients(carbs=80.0, water=30.0))
        )
        window._refresh_all()
        assert "Datenprüfung: 1 Fehler" in window.statusBar().currentMessage()

    def test_the_data_check_shows_all_findings(
        self, window: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from brotrechner.core.validation import validate_database

        calls = _stub_dialog(monkeypatch, "ValidationDialog", accept=True)
        window._on_validate()
        assert calls[0]["args"][0] == validate_database(window._ingredients)

    def test_the_about_dialog_counts(self, window: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = _stub_dialog(monkeypatch, "AboutDialog", accept=True)
        window._on_about()
        assert calls[0]["ingredient_count"] == len(window._ingredients)
        assert calls[0]["recipe_count"] == len(window._recipes)

    def test_without_a_file_manager_the_folder_is_named(
        self, window: Any, monkeypatch: pytest.MonkeyPatch, shown: _Shown, data_dir: Path
    ) -> None:
        from PySide6.QtGui import QDesktopServices

        monkeypatch.setattr(QDesktopServices, "openUrl", lambda *_a: False)
        window._on_open_data_dir()
        assert shown.text("Datenverzeichnis") == str(data_dir)


class TestFailures:
    def test_saving_ingredients(
        self, window: Any, monkeypatch: pytest.MonkeyPatch, shown: _Shown
    ) -> None:
        def broken(*_args: object) -> None:
            raise RepositoryError("Platte voll")

        monkeypatch.setattr("brotrechner.gui.main_window.save_ingredients", broken)
        assert not window._save_ingredients()
        assert shown.text("Speichern fehlgeschlagen") == "Platte voll"

    def test_saving_recipes(
        self, window: Any, monkeypatch: pytest.MonkeyPatch, shown: _Shown
    ) -> None:
        def broken(*_args: object) -> None:
            raise RepositoryError("Platte voll")

        monkeypatch.setattr("brotrechner.gui.main_window.save_recipes", broken)
        assert not window._save_recipes()
        assert shown.titles("critical") == ["Speichern fehlgeschlagen"]

    def test_creating_the_database(
        self, window: Any, monkeypatch: pytest.MonkeyPatch, shown: _Shown
    ) -> None:
        def broken(*_args: object, **_kwargs: object) -> None:
            raise RepositoryError("schreibgeschützt")

        monkeypatch.setattr("brotrechner.gui.main_window.ensure_user_database", broken)
        result = window._ensure_database()
        assert not result.created_ingredients
        assert shown.text("Daten konnten nicht angelegt werden") == "schreibgeschützt"

    def test_an_incomplete_backup(
        self, window: Any, monkeypatch: pytest.MonkeyPatch, shown: _Shown
    ) -> None:
        monkeypatch.setattr("brotrechner.gui.main_window.make_backup", lambda _path: None)
        window._on_backup()
        assert shown.titles() == ["Sicherung unvollständig"]

    def test_without_reportlab_the_report_is_switched_off(
        self,
        qapp: object,
        data_dir: Path,
        dialogs: dict[str, object],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        del qapp, dialogs
        from brotrechner.export import report
        from brotrechner.gui.main_window import MainWindow

        monkeypatch.setattr(report, "is_available", lambda: False)
        widget = MainWindow(data_dir=data_dir)
        try:
            assert not widget.btn_report.isEnabled()
            assert "reportlab" in widget.btn_report.toolTip()
        finally:
            widget.close()

    def test_legacy_data_is_announced(
        self, qapp: object, data_dir: Path, shown: _Shown, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        del qapp
        from brotrechner.data.seed import SeedResult, ensure_user_database
        from brotrechner.gui.main_window import MainWindow

        def legacy(*args: Any, **kwargs: Any) -> SeedResult:
            result = ensure_user_database(*args, **kwargs)
            result.imported_from_legacy = True
            return result

        monkeypatch.setattr("brotrechner.gui.main_window.ensure_user_database", legacy)
        widget = MainWindow(data_dir=data_dir)
        try:
            assert "Altdaten übernommen" in shown.titles("information")
        finally:
            widget.close()


def test_the_export_folder_follows_the_data_dir(
    qapp: object, tmp_path: Path, data_dir: Path, dialogs: dict[str, object]
) -> None:
    """Ohne Dokumentenordner gehören die Ausgaben in das Datenverzeichnis des Fensters.

    Bisher landeten sie im Datenverzeichnis des Systems, auch wenn der
    Brotrechner mit ``--data-dir`` auf ein anderes gerichtet war.
    """
    del qapp, dialogs
    from brotrechner.gui.main_window import MainWindow

    own = tmp_path / "eigen"
    own.mkdir()
    widget = MainWindow(data_dir=own)
    try:
        assert widget._export_dir() == own / "exports"
    finally:
        widget.close()
    assert not (data_dir / "exports").exists()
