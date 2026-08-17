"""Regressionstests für Fehler, die nur an der Oberfläche sichtbar wurden.

Diese Tests brauchen als einzige eine Qt-Anwendung. Sie prüfen keine Optik,
sondern nachrechenbare Geometrie und Stilregeln - genau die Größen, deren
Auseinanderlaufen die hier festgehaltenen Fehler verursacht hat.
"""

from __future__ import annotations

import pytest

from brotrechner.core.models import Category, Ingredient
from brotrechner.gui.theme import ThemeMode, build_stylesheet, resolve_tokens

pytestmark = pytest.mark.gui


@pytest.fixture
def picker(qapp: object):
    """Zutatenauswahl mit einer Handvoll Einträgen."""
    del qapp
    from brotrechner.gui.widgets.ingredient_picker import IngredientPicker

    widget = IngredientPicker()
    widget.set_ingredients(
        [
            Ingredient(name="Flohsamenschalen", category=Category.SEEDS_NUTS),
            Ingredient(name="Roggenmehl Type 1150", category=Category.FLOUR),
            Ingredient(name="Roggenmehl Type 1370", category=Category.FLOUR),
            Ingredient(name="Roggenvollkornmehl", manufacturer="Bauck", category=Category.FLOUR),
        ]
    )
    return widget


class TestCompleterPopup:
    """Die Klappliste schnitt bei genau einem Treffer die Unterlängen ab.

    Ursache war, dass QCompleter die Höhe aus ``sizeHintForRow`` berechnet,
    gezeichnet aber mit der Zeilenhöhe des Kopfbereichs wurde. Diese Tests
    halten fest, dass beide Zahlen aus derselben Quelle kommen.
    """

    def test_row_height_matches_the_size_hint(self, picker: object) -> None:
        popup = picker.completer().popup()  # type: ignore[attr-defined]
        assert popup.sizeHintForRow(0) == popup.verticalHeader().defaultSectionSize()

    def test_row_is_taller_than_the_font(self, picker: object) -> None:
        """Sonst fehlt der Platz für Unterlängen wie in "g" und "ß"."""
        popup = picker.completer().popup()  # type: ignore[attr-defined]
        assert popup.sizeHintForRow(0) >= picker.fontMetrics().height() + 8  # type: ignore[attr-defined]

    def test_single_match_fits_without_scrolling(self, picker: object) -> None:
        completer = picker.completer()  # type: ignore[attr-defined]
        completer.setCompletionPrefix("Flohsamen")
        completer.complete()
        popup = completer.popup()
        assert completer.completionCount() == 1
        assert popup.viewport().height() >= popup.rowHeight(0)

    def test_several_matches_fit_without_scrolling(self, picker: object) -> None:
        completer = picker.completer()  # type: ignore[attr-defined]
        completer.setCompletionPrefix("Roggenmehl")
        completer.complete()
        popup = completer.popup()
        rows = completer.completionCount()
        assert rows == 2
        assert popup.viewport().height() >= rows * popup.rowHeight(0)

    def test_rows_stay_on_one_line(self, picker: object) -> None:
        """Mit Zeilenumbruch würde ein langer Name die Liste zerreißen."""
        assert not picker.completer().popup().wordWrap()  # type: ignore[attr-defined]


class TestCalendarStyling:
    """Zweistellige Tage erschienen im Kalender als "…".

    Die allgemeine Tabellenregel des Stylesheets gab jeder Zelle 6 Pixel
    Polsterung links und rechts. Bei rund 31 Pixel Spaltenbreite blieb für
    "27" kein Platz mehr.
    """

    @pytest.mark.parametrize("mode", [ThemeMode.LIGHT, ThemeMode.DARK])
    def test_calendar_cells_have_no_padding(self, mode: ThemeMode) -> None:
        sheet = build_stylesheet(resolve_tokens(mode))
        assert "QCalendarWidget QTableView::item { padding: 0; }" in sheet

    @pytest.mark.parametrize("mode", [ThemeMode.LIGHT, ThemeMode.DARK])
    def test_navigation_bar_is_styled(self, mode: ThemeMode) -> None:
        sheet = build_stylesheet(resolve_tokens(mode))
        assert "qt_calendar_navigationbar" in sheet

    def test_two_digit_days_are_not_elided(self, qapp: object) -> None:
        """Der eigentliche Beweis: Passt "27" in eine Zelle des Kalenders?"""
        del qapp
        from PySide6.QtWidgets import QCalendarWidget, QTableView

        calendar = QCalendarWidget()
        calendar.setStyleSheet(build_stylesheet(resolve_tokens(ThemeMode.LIGHT)))
        calendar.show()
        view = calendar.findChild(QTableView, "qt_calendar_calendarview")
        assert view is not None
        needed = calendar.fontMetrics().horizontalAdvance("27")
        assert view.columnWidth(1) >= needed, (
            f"Spalte {view.columnWidth(1)} px, benötigt {needed} px"
        )


class TestConfirmationDialogs:
    """Bestätigungsdialoge blieben wirkungslos: Ja tat dasselbe wie Nein.

    PySide6 reicht die geklickte Schaltfläche von ``QMessageBox.question`` als
    einfache Zahl zurück, nicht als Enum-Mitglied (nachgemessen mit 6.11:
    ``type(antwort) is int``). Der Code verglich sie mit ``is`` gegen
    ``StandardButton.Yes`` - und das ist bei zwei verschiedenen Objekten immer
    falsch. Überschreiben, Löschen und alle anderen Rückfragen brachen deshalb
    stumm ab; sichtbar war nur der Systemton des Dialogs.

    Die Attrappen hier geben bewusst ``int`` zurück. Genau das taten die
    früheren Tests nicht - sie lieferten das Enum-Mitglied und liefen deshalb
    grün, während das Programm nicht funktionierte.
    """

    @pytest.fixture
    def window(self, qapp: object, data_dir, dialogs: dict[str, object]):
        """Hauptfenster auf einem leeren, isolierten Datenverzeichnis."""
        del qapp, dialogs
        from brotrechner.gui.main_window import MainWindow

        widget = MainWindow(data_dir=data_dir)
        yield widget
        widget.close()

    @staticmethod
    def _stored(data_dir) -> dict[str, float]:
        """Rezeptnamen und Gesamteinwaage - frisch von der Platte gelesen."""
        from brotrechner.data.repository import load_ingredients, load_recipes

        ingredients, _ = load_ingredients(data_dir / "ingredients.json")
        recipes, _ = load_recipes(data_dir / "recipes.json", ingredients)
        return {r.name: sum(i.amount_g for i in r.items) for r in recipes}

    @staticmethod
    def _fill(window: object, grams: float) -> None:
        """Legt eine Zutat mit vorgegebener Menge in den Rechner."""
        page = window.page_calculator  # type: ignore[attr-defined]
        flour = next(i for i in window._ingredients if i.is_flour)  # type: ignore[attr-defined]
        page.clear()
        page._items_model.add_item(flour, grams)
        page.spin_baked.setValue(grams * 0.8)
        page._recalculate()

    def test_overwriting_actually_replaces_the_stored_recipe(
        self, window: object, data_dir
    ) -> None:
        """Der gemeldete Fehler: Nachfrage kommt, alte Werte bleiben stehen."""
        self._fill(window, 1000.0)
        window.btn_save_recipe.click()  # type: ignore[attr-defined]
        assert self._stored(data_dir)["Testbrot"] == pytest.approx(1000.0)

        self._fill(window, 2500.0)
        window.btn_save_recipe.click()  # type: ignore[attr-defined]
        assert self._stored(data_dir)["Testbrot"] == pytest.approx(2500.0)

    def test_deleting_actually_removes_the_recipe(self, window: object, data_dir) -> None:
        """Der zweite gemeldete Fehler: Löschen ohne Wirkung."""
        self._fill(window, 1000.0)
        window.btn_save_recipe.click()  # type: ignore[attr-defined]
        assert "Testbrot" in self._stored(data_dir)

        window._on_delete_recipe("Testbrot")  # type: ignore[attr-defined]
        assert "Testbrot" not in self._stored(data_dir)

    def test_qt_returns_a_plain_number_for_the_clicked_button(self, qapp: object) -> None:
        """Hält die Ursache fest - schlägt an, falls PySide6 das je ändert."""
        del qapp
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication, QMessageBox

        def klick() -> None:
            dialog = QApplication.activeModalWidget()
            if isinstance(dialog, QMessageBox):
                dialog.button(QMessageBox.StandardButton.Yes).click()

        QTimer.singleShot(0, klick)
        answer = QMessageBox.question(
            None,
            "Test",
            "Ja?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        assert answer == QMessageBox.StandardButton.Yes, "Gleichheit muss gelten"
        assert answer is not QMessageBox.StandardButton.Yes, (
            "Identität gilt nicht - deshalb ist 'is' hier verboten"
        )


def test_no_identity_comparison_against_qt_enums() -> None:
    """Wache gegen den ganzen Fehlertyp, nicht nur gegen die vier Fundstellen.

    Qt reicht Enum-Werte je nach Version mal als Mitglied, mal als blanke Zahl
    heraus - die Rolle in ``headerData`` ist schon heute ein ``int``. Ein
    Identitätsvergleich ist deshalb an keiner Qt-Grenze zulässig; ``==``
    funktioniert in beiden Fällen.
    """
    import re
    from pathlib import Path

    quelle = Path(__file__).resolve().parents[1] / "src" / "brotrechner"
    muster = re.compile(r"\bis\s+(?:not\s+)?Q[A-Za-z]+\.")
    treffer = [
        f"{datei.relative_to(quelle)}:{nr}: {zeile.strip()}"
        for datei in sorted(quelle.rglob("*.py"))
        for nr, zeile in enumerate(datei.read_text(encoding="utf-8").splitlines(), 1)
        if muster.search(zeile)
    ]
    assert not treffer, "Identitätsvergleich gegen Qt-Enum:\n" + "\n".join(treffer)
