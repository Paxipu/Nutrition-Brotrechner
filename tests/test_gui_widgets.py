"""Seiten und Bausteine der Oberfläche: Auswahl, Anzeige, Zeichnen."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from brotrechner.core.models import Category, Ingredient, PriceEntry, Recipe
from brotrechner.core.nutrients import Nutrients
from brotrechner.core.reference import AmpelLevel

pytestmark = pytest.mark.gui

FLOUR = Ingredient(
    name="Weizenmehl 550",
    manufacturer="Aurora",
    category=Category.FLOUR,
    nutrients=Nutrients(energy_kcal=341, fat=1.2, carbs=71, protein=10, fiber=4, water=13.5),
    flour_percent=100.0,
    package_price=0.99,
    package_size_g=1000.0,
    price_source="Supermarkt",
    price_updated=date(2026, 9, 1),
    price_history=[PriceEntry(date(2026, 1, 1), 0.89, 1000.0)],
    notes="Standardmehl",
)
STARTER = Ingredient(
    name="Anstellgut",
    category=Category.LEAVENING,
    nutrients=Nutrients(energy_kcal=170, carbs=36, protein=4, water=56.5),
    flour_percent=50.0,
)
BROKEN = Ingredient(name="Kaputt", nutrients=Nutrients(carbs=80.0, water=30.0))


@pytest.fixture
def tokens() -> Any:
    from brotrechner.gui.theme import ThemeMode, resolve_tokens

    return resolve_tokens(ThemeMode.LIGHT)


@pytest.fixture
def messages(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    from PySide6.QtWidgets import QMessageBox

    titles: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "information", lambda _parent, title, *_rest: titles.append(title)
    )
    return titles


class TestIngredientsPage:
    @pytest.fixture
    def page(self, qapp: object, tokens: Any) -> Iterator[Any]:
        del qapp
        from brotrechner.gui.pages.ingredients import IngredientsPage

        widget = IngredientsPage(tokens)
        widget.set_ingredients([FLOUR, STARTER, BROKEN])
        yield widget
        widget.close()

    def _signals(self, page: Any) -> list[tuple[str, object]]:
        received: list[tuple[str, object]] = []
        for name in ("edit_requested", "duplicate_requested", "delete_requested"):
            getattr(page, name).connect(lambda value, n=name: received.append((n, value)))
        page.export_requested.connect(lambda value: received.append(("export", value)))
        return received

    def _select(self, page: Any, *ingredients: Ingredient) -> None:
        from PySide6.QtCore import QItemSelectionModel

        page.table.clearSelection()
        flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
        for ingredient in ingredients:
            source = page._model.index(page._model.row_of(ingredient.key), 0)
            page.table.selectionModel().select(page._proxy.mapFromSource(source), flags)

    def test_the_buttons_act_on_one_ingredient(self, page: Any) -> None:
        received = self._signals(page)
        self._select(page, STARTER)
        page.btn_edit.click()
        page.btn_duplicate.click()
        page.btn_delete.click()
        assert received == [
            ("edit_requested", STARTER.key),
            ("duplicate_requested", STARTER.key),
            ("delete_requested", STARTER.key),
        ]

    @pytest.mark.parametrize("button", ["btn_edit", "btn_duplicate", "btn_delete"])
    def test_without_exactly_one_they_ask(
        self, page: Any, messages: list[str], button: str
    ) -> None:
        received = self._signals(page)
        self._select(page, FLOUR, STARTER)
        getattr(page, button).click()
        page.table.clearSelection()
        getattr(page, button).click()
        assert received == []
        assert messages == ["Auswahl nötig", "Auswahl nötig"]

    def test_a_double_click_edits(self, page: Any) -> None:
        received = self._signals(page)
        self._select(page, FLOUR)
        page.table.doubleClicked.emit(page.table.currentIndex())
        assert received == [("edit_requested", FLOUR.key)]

    def test_exporting_several(self, page: Any, messages: list[str]) -> None:
        received = self._signals(page)
        page.table.clearSelection()
        page.btn_export.click()
        assert messages == ["Nichts ausgewählt"]
        self._select(page, FLOUR, STARTER)
        page.btn_export.click()
        (kind, exported) = received[0]
        assert kind == "export"
        assert {i.key for i in exported} == {FLOUR.key, STARTER.key}  # type: ignore[attr-defined]

    def test_the_detail_of_one(self, page: Any) -> None:
        self._select(page, FLOUR)
        text = page.lbl_detail.text()
        for expected in (
            "Weizenmehl 550",
            "Aurora · Mehl · zählt als Mehl",
            "0,099 € je 100 g",
            "Stand 01.09.2026",
            "Quelle: Supermarkt",
            "1 frühere Preisstände gespeichert",
            "<i>Standardmehl</i>",
        ):
            assert expected in text

    def test_the_detail_of_a_starter(self, page: Any) -> None:
        self._select(page, STARTER)
        text = page.lbl_detail.text()
        assert "ohne Herstellerangabe · Triebmittel · Mehlanteil 50,0 %" in text
        assert "Kein Preis hinterlegt" in text

    def test_the_detail_names_the_findings(self, page: Any, tokens: Any) -> None:
        self._select(page, BROKEN)
        text = page.lbl_detail.text()
        assert "<b>Datenprüfung</b>" in text
        assert tokens.danger in text

    def test_several_marked(self, page: Any) -> None:
        self._select(page, FLOUR, STARTER)
        assert "2 Zutaten markiert" in page.lbl_detail.text()
        page.table.clearSelection()
        assert page.lbl_detail.text() == "Keine Zutat ausgewählt."

    def test_many_marked(self, qapp: object, tokens: Any) -> None:
        del qapp
        from brotrechner.gui.pages.ingredients import IngredientsPage

        many = [Ingredient(name=f"Zutat {i:02d}") for i in range(15)]
        page = IngredientsPage(tokens)
        page.set_ingredients(many)
        page.table.selectAll()
        assert "… und 3 weitere" in page.lbl_detail.text()
        page.close()

    def test_the_category_filter_counts(self, page: Any) -> None:
        from brotrechner.gui.qt_compat import select_data

        assert page.lbl_count.text() == "3 Zutaten"
        assert select_data(page.cmb_category, Category.FLOUR)
        assert page.lbl_count.text() == "1 von 3 Zutaten"

    def test_the_selection_survives_new_data(self, page: Any) -> None:
        self._select(page, STARTER)
        page.set_ingredients([FLOUR, STARTER, BROKEN])
        assert [i.key for i in page.selected_ingredients()] == [STARTER.key]

    def test_an_unknown_key_selects_nothing(self, page: Any) -> None:
        page.table.clearSelection()
        page.select_key("gibt|es nicht")
        assert page.selected_ingredients() == []

    def test_a_filtered_out_ingredient_is_not_selected(self, page: Any) -> None:
        page.txt_search.setText("Aurora")
        page.table.clearSelection()
        page.select_key(STARTER.key)
        assert page.selected_ingredients() == []


class TestRecipesPage:
    @pytest.fixture
    def page(self, qapp: object, tokens: Any) -> Iterator[Any]:
        del qapp
        from brotrechner.gui.pages.recipes import RecipesPage

        widget = RecipesPage(tokens)
        widget.set_data([Recipe(name="Roggenbrot"), Recipe(name="Dinkelbrot")], [])
        yield widget
        widget.close()

    def test_buttons_need_a_recipe(self, page: Any, messages: list[str]) -> None:
        loaded: list[str] = []
        page.load_requested.connect(loaded.append)
        page.table.clearSelection()
        page.btn_load.click()
        assert messages == ["Auswahl nötig"]
        assert page.select_recipe("Dinkelbrot")
        page.btn_load.click()
        assert loaded == ["Dinkelbrot"]

    def test_an_unknown_recipe_is_not_selected(self, page: Any) -> None:
        assert not page.select_recipe("Baguette")


class TestCards:
    def test_a_clickable_label_reacts_to_the_left_button(self, qapp: object) -> None:
        del qapp
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        from brotrechner.gui.widgets.cards import ClickableLabel

        label = ClickableLabel("Daten: /tmp")
        clicks: list[bool] = []
        label.clicked.connect(lambda: clicks.append(True))
        QTest.mouseClick(label, Qt.MouseButton.RightButton)
        assert clicks == []
        QTest.mouseClick(label, Qt.MouseButton.LeftButton)
        assert clicks == [True]

    @staticmethod
    def _pixel(widget: Any, x: int, y: int) -> str:
        image = widget.grab().toImage()
        return str(image.pixelColor(x, y).name())

    @pytest.mark.parametrize(
        ("level", "token"),
        [(AmpelLevel.LOW, "success"), (AmpelLevel.MEDIUM, "warning"), (AmpelLevel.HIGH, "danger")],
    )
    def test_the_traffic_light_is_painted_in_its_colour(
        self, qapp: object, tokens: Any, level: AmpelLevel, token: str
    ) -> None:
        del qapp
        from brotrechner.gui.widgets.cards import AmpelDot

        dot = AmpelDot(tokens)
        dot.set_level(level)
        centre = dot.width() // 2
        assert self._pixel(dot, centre, centre) == getattr(tokens, token).lower()

    def test_without_a_level_nothing_is_painted(self, qapp: object, tokens: Any) -> None:
        del qapp
        from brotrechner.gui.widgets.cards import AmpelDot

        dot = AmpelDot(tokens)
        dot.set_level(AmpelLevel.NONE)
        centre = dot.width() // 2
        assert self._pixel(dot, centre, centre) not in {
            tokens.success.lower(),
            tokens.warning.lower(),
            tokens.danger.lower(),
        }

    def test_the_intake_bar_fills_to_its_share(self, qapp: object, tokens: Any) -> None:
        del qapp
        from brotrechner.gui.widgets.cards import IntakeBar

        bar = IntakeBar(tokens)
        bar.resize(100, 12)
        bar.set_percent(40.0)
        middle = bar.height() // 2
        assert self._pixel(bar, 20, middle) == tokens.accent.lower()
        assert self._pixel(bar, 80, middle) == tokens.border.lower()

    def test_more_than_the_reference_intake_is_a_warning(self, qapp: object, tokens: Any) -> None:
        del qapp
        from brotrechner.gui.widgets.cards import IntakeBar

        bar = IntakeBar(tokens)
        bar.resize(100, 12)
        bar.set_percent(130.0)
        assert self._pixel(bar, 95, bar.height() // 2) == tokens.warning.lower()


class TestPicker:
    @pytest.fixture
    def picker(self, qapp: object) -> Iterator[Any]:
        del qapp
        from brotrechner.gui.widgets.ingredient_picker import IngredientPicker

        widget = IngredientPicker()
        widget.set_ingredients(
            [
                FLOUR,
                Ingredient(name="Weizenmehl 1050", category=Category.FLOUR),
                Ingredient(name="Roggenmehl 1150", manufacturer="Bauck"),
            ]
        )
        yield widget
        widget.close()

    def _typed(self, picker: Any, text: str) -> str | None:
        picker.setCurrentIndex(-1)
        picker.setEditText(text)
        return picker.current_key()  # type: ignore[no-any-return]

    def test_a_typed_name(self, picker: Any) -> None:
        assert self._typed(picker, "weizenmehl 1050") == Ingredient(name="Weizenmehl 1050").key

    def test_a_unique_part(self, picker: Any) -> None:
        assert (
            self._typed(picker, "bauck")
            == Ingredient(name="Roggenmehl 1150", manufacturer="Bauck").key
        )

    def test_an_ambiguous_part_is_nothing(self, picker: Any) -> None:
        """Die Vorversion nahm bei mehreren Treffern stillschweigend den ersten."""
        assert self._typed(picker, "weizen") is None

    def test_nothing_typed(self, picker: Any) -> None:
        assert self._typed(picker, "   ") is None

    def test_choosing_from_the_list(self, picker: Any) -> None:
        from brotrechner.gui.widgets.ingredient_picker import _KEY_ROLE

        chosen: list[str] = []
        picker.ingredient_chosen.connect(chosen.append)
        picker.activated.emit(0)
        assert chosen == [picker._model.item(0, 0).data(_KEY_ROLE)]

    def test_choosing_from_the_suggestions(self, picker: Any) -> None:
        chosen: list[str] = []
        picker.ingredient_chosen.connect(chosen.append)
        picker.setCurrentIndex(-1)
        picker.setEditText("bauck")
        picker._on_completer_activated("Roggenmehl 1150")
        picker.setEditText("weizen")
        picker._on_completer_activated("Weizen")
        assert chosen == [Ingredient(name="Roggenmehl 1150", manufacturer="Bauck").key], (
            "mehrdeutig: nichts"
        )


class TestStart:
    def test_the_window_opens_and_the_loop_runs(
        self, qapp: object, data_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        del qapp
        from PySide6.QtWidgets import QApplication

        from brotrechner.gui import app

        shown: list[str] = []

        def fake_exec(self: QApplication) -> int:
            del self
            # Nur das eben geöffnete Fenster: Fenster früherer Tests sind
            # geschlossen, aber nicht zerstört - und fragten beim Schließen nach.
            opened = [w for w in QApplication.topLevelWidgets() if w.isVisible()]
            shown.extend(w.windowTitle() for w in opened)
            for widget in opened:
                widget.close()
            return 5

        monkeypatch.setattr(QApplication, "exec", fake_exec)
        assert app.run([], data_dir=data_dir) == 5
        assert any(title.startswith("Brotrechner") for title in shown)


class TestPrinting:
    def test_a_printer_that_cannot_open_is_reported(self, qapp: object, tmp_path: Path) -> None:
        del qapp
        from PySide6.QtGui import QImage
        from PySide6.QtPrintSupport import QPrinter

        from brotrechner.export.printing import Placement
        from brotrechner.gui.printing import paint_labels

        (tmp_path / "belegt").write_text("x", encoding="utf-8")
        printer = QPrinter()
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(str(tmp_path / "belegt" / "etikett.pdf"))
        image = QImage(10, 10, QImage.Format.Format_RGB32)
        assert not paint_labels(printer, image, [Placement(0, 10.0, 10.0, 70.0, 100.0)])
