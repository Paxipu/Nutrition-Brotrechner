"""Die Auswertung eines Rezepts lässt sich als CSV speichern - auch aus der Oberfläche.

``write_analysis_csv`` gab es schon, erreichbar war aus dem Programm aber nur
„Zutaten als CSV“ - die Datenbank, nicht das Rezept.
"""

from __future__ import annotations

import csv
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
    widget.page_calculator.clear()
    widget.close()


def _save_to(monkeypatch: pytest.MonkeyPatch, target: Path) -> list[str]:
    from PySide6.QtWidgets import QFileDialog

    suggested: list[str] = []

    def answer(_parent: object, _title: str, proposal: str, *_rest: object) -> tuple[str, str]:
        suggested.append(proposal)
        return str(target), ""

    monkeypatch.setattr(QFileDialog, "getSaveFileName", answer)
    return suggested


def test_the_menu_offers_it(window: Any) -> None:
    texts = [
        action.text() for menu in window.menuBar().actions() for action in menu.menu().actions()
    ]
    assert "Auswertung als CSV …" in texts


def test_the_recipe_rows_are_written(
    window: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    flour = next(i for i in window._ingredients if i.is_flour)
    page = window.page_calculator
    page.txt_name.setText("Roggen/Brot")
    page._items_model.add_item(flour, 500.0)
    page.spin_baked.setValue(400.0)
    page._recalculate()
    suggested = _save_to(monkeypatch, tmp_path / "auswertung")
    window._on_export_analysis_csv()
    with (tmp_path / "auswertung.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle, delimiter=";"))
    assert rows[0] == ["Rezept: Roggen/Brot"]
    assert rows[2][0] == flour.name
    assert Path(suggested[0]).name == "Roggen_Brot.csv"


def test_without_a_recipe_nothing_is_asked(
    window: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    suggested = _save_to(monkeypatch, tmp_path / "leer.csv")
    window._on_export_analysis_csv()
    assert suggested == []
    assert not (tmp_path / "leer.csv").exists()


def _fill(window: Any) -> None:
    flour = next(i for i in window._ingredients if i.is_flour)
    page = window.page_calculator
    page._items_model.add_item(flour, 500.0)
    page.spin_baked.setValue(400.0)
    page._recalculate()


def test_cancelling_writes_nothing(window: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from PySide6.QtWidgets import QFileDialog

    from brotrechner.export import table

    _fill(window)
    written: list[object] = []
    monkeypatch.setattr(table, "write_analysis_csv", lambda *args, **_k: written.append(args))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *_a, **_k: ("", ""))
    window._on_export_analysis_csv()
    assert written == []


def test_a_failed_write_is_reported(
    window: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Ein Ordner, den es nicht gibt, endet in einer Meldung statt im Absturz."""
    from PySide6.QtWidgets import QMessageBox

    _fill(window)
    _save_to(monkeypatch, tmp_path / "fehlt" / "auswertung.csv")
    titles: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "critical", lambda _parent, title, *_rest: titles.append(title)
    )
    window._on_export_analysis_csv()
    assert titles == ["Export fehlgeschlagen"]
