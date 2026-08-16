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
