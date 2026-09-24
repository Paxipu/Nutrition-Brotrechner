"""Etikett für den Verkauf: Pflichtangaben und Mindestschriftgröße.

Wer Brot verpackt verkauft, braucht nach Artikel 9 VO (EU) Nr. 1169/2011 unter
anderem die Bezeichnung, das Zutatenverzeichnis mit hervorgehobenen
Allergenen, die Nettofüllmenge, das Mindesthaltbarkeitsdatum und Name samt
Anschrift des Lebensmittelunternehmers. Alles in einer x-Höhe von mindestens
1,2 mm (Artikel 13 Abs. 2, Anhang IV). Das Zutatenverzeichnis darf dafür nicht
gekürzt werden - das tat das Etikett bisher, wenn der Platz nicht reichte.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from brotrechner.core.allergens import Allergen
from brotrechner.core.labeling import IngredientList, ListEntry
from brotrechner.core.nutrients import Nutrients
from brotrechner.core.sales import SaleIssue, check_sale
from brotrechner.export.fonts import FontSet, ink_height, load_font_set
from brotrechner.export.label import (
    MIN_X_HEIGHT_MM,
    LabelOptions,
    LabelSize,
    measure_label,
    render_and_measure,
    render_label,
    required_digit_height_mm,
)

BREAD = Nutrients(
    energy_kcal=238,
    fat=2.8,
    saturated_fat=0.5,
    carbs=43.0,
    sugar=1.1,
    protein=7.0,
    salt=1.2,
    fiber=6.2,
    water=40.0,
)

LISTING = IngredientList(
    entries=(
        ListEntry("*Roggen*mehl Type 1150", 300),
        ListEntry("*Weizen*mehl Type 1050", 200),
        ListEntry("Wasser", 99),
        ListEntry("Jodsalz", 11),
    ),
    allergens=frozenset({Allergen.RYE, Allergen.WHEAT}),
)

PRODUCER = "Backstube Muster, Hauptstraße 1, 12345 Musterstadt"

FONTS = load_font_set()


def sale_options(**changes: object) -> LabelOptions:
    values: dict[str, object] = {
        "title": "Roggenmischbrot",
        "size": LabelSize.MEDIUM,
        "dpi": 200,
        "for_sale": True,
        "producer": PRODUCER,
        "baked_on": date(2026, 9, 24),
        "best_before": date(2026, 10, 1),
        "ingredients": tuple(e.markup for e in LISTING.entries),
        "net_weight_g": 900.0,
    }
    values.update(changes)
    return LabelOptions(**values)  # type: ignore[arg-type]


def codes(issues: list[SaleIssue]) -> set[str]:
    return {issue.code for issue in issues}


def complete(**changes: object) -> list[SaleIssue]:
    values: dict[str, object] = {
        "title": "Roggenmischbrot",
        "producer": PRODUCER,
        "baked_on": date(2026, 9, 24),
        "best_before": date(2026, 10, 1),
        "show_ingredients": True,
        "listing": LISTING,
        "net_weight_g": 900.0,
    }
    values.update(changes)
    return check_sale(**values)  # type: ignore[arg-type]


class TestMandatoryParticulars:
    def test_a_complete_label(self) -> None:
        assert complete() == []

    @pytest.mark.parametrize("producer", ["", "   "])
    def test_the_producer_is_mandatory(self, producer: str) -> None:
        assert "producer_missing" in codes(complete(producer=producer))

    def test_the_best_before_date_is_mandatory(self) -> None:
        assert "best_before_missing" in codes(complete(best_before=None))

    def test_the_best_before_date_cannot_precede_baking(self) -> None:
        issues = complete(best_before=date(2026, 9, 20))
        assert "best_before_before_baking" in codes(issues)

    def test_the_ingredient_list_is_mandatory(self) -> None:
        assert "ingredients_hidden" in codes(complete(show_ingredients=False))

    def test_unrecorded_allergens_are_named(self) -> None:
        listing = IngredientList(entries=LISTING.entries, unknown=("Margarine", "Rosinen"))
        issue = next(i for i in complete(listing=listing) if i.code == "allergens_unknown")
        assert "Margarine" in issue.message
        assert "Rosinen" in issue.message

    def test_the_net_quantity_is_mandatory(self) -> None:
        assert "net_weight_missing" in codes(complete(net_weight_g=0.0))

    def test_the_name_of_the_food_is_mandatory(self) -> None:
        assert "title_missing" in codes(complete(title=" "))

    def test_every_issue_names_its_legal_basis(self) -> None:
        issues = complete(producer="", best_before=None, show_ingredients=False)
        assert all("Art." in issue.message or "Anhang" in issue.message for issue in issues)


class TestNetQuantityDigits:
    @pytest.mark.parametrize(
        ("grams", "height"),
        [(50, 2.0), (50.1, 3.0), (200, 3.0), (200.5, 4.0), (1000, 4.0), (1000.1, 6.0)],
    )
    def test_the_table(self, grams: float, height: float) -> None:
        assert required_digit_height_mm(grams) == height

    def test_the_digits_are_big_enough_for_sale(self) -> None:
        report = measure_label(BREAD, sale_options(), fonts=FONTS)
        assert report.net_weight_digit_mm >= 4.0 - 0.05

    def test_a_heavy_bread_fits_on_the_small_label(self) -> None:
        """6 mm Ziffern für 1,5 kg - das Wort rückt dafür in eine eigene Zeile."""
        options = sale_options(size=LabelSize.SMALL, net_weight_g=1500.0)
        report = measure_label(BREAD, options, fonts=FONTS)
        assert report.net_weight_digit_mm >= 6.0 - 0.05
        assert report.net_weight_width_ok


class TestMinimumTextSize:
    @pytest.mark.parametrize("size", list(LabelSize))
    def test_every_text_meets_the_x_height_for_sale(self, size: LabelSize) -> None:
        report = measure_label(BREAD, sale_options(size=size), fonts=FONTS)
        assert report.min_x_height_mm >= MIN_X_HEIGHT_MM - 0.02

    def test_the_constant(self) -> None:
        assert MIN_X_HEIGHT_MM == 1.2

    @settings(max_examples=40)
    @given(
        size=st.sampled_from(list(LabelSize)),
        dpi=st.sampled_from([72, 110, 150, 300, 600]),
        grams=st.floats(min_value=1.0, max_value=5000.0),
    )
    def test_the_minimum_sizes_hold_at_any_resolution(
        self, size: LabelSize, dpi: int, grams: float
    ) -> None:
        """Die Schrift rundet auf ganze Pixel - bei 72 dpi ist ein Pixel 0,35 mm."""
        options = sale_options(size=size, dpi=dpi, net_weight_g=grams)
        report = measure_label(BREAD, options, fonts=FONTS)
        if report.net_weight_width_ok:
            assert report.min_x_height_mm >= MIN_X_HEIGHT_MM
            assert report.net_weight_digit_mm >= required_digit_height_mm(grams)

    def test_a_gift_label_may_stay_smaller(self) -> None:
        """Ohne Verkauf gilt die Vorschrift nicht; die Typografie darf schrumpfen."""
        many = tuple(f"Zutat Nummer {i}" for i in range(30))
        options = sale_options(size=LabelSize.SMALL, for_sale=False, ingredients=many)
        report = measure_label(BREAD, options, fonts=FONTS)
        assert report.min_x_height_mm < MIN_X_HEIGHT_MM


class TestNeverTruncated:
    def test_a_normal_list_fits(self) -> None:
        report = measure_label(BREAD, sale_options(), fonts=FONTS)
        assert report.fits
        assert report.issues(for_sale=True) == []

    def test_a_list_that_does_not_fit_is_reported(self) -> None:
        many = tuple(f"*Weizen*mehl Nummer {i}" for i in range(40))
        report = measure_label(
            BREAD, sale_options(size=LabelSize.SMALL, ingredients=many), fonts=FONTS
        )
        assert not report.fits
        assert any("passt nicht" in issue.message for issue in report.issues(for_sale=True))

    def test_a_long_list_that_pushes_the_footer_out_is_reported(self) -> None:
        """Der feste Teil passt, das vollständige Verzeichnis nicht mehr.

        Der Fuß rückt dann unter das Verzeichnis und wird abgeschnitten - das
        darf nicht als "passt" durchgehen.
        """
        many = tuple(f"*Weizen*mehl Nummer {i}" for i in range(30))
        report = measure_label(
            BREAD, sale_options(size=LabelSize.LARGE, ingredients=many), fonts=FONTS
        )
        assert report.fixed_part_fits
        assert report.required_height_px > report.available_height_px
        assert not report.fits

    @settings(max_examples=40)
    @given(
        size=st.sampled_from(list(LabelSize)),
        count=st.integers(min_value=0, max_value=60),
        producer_lines=st.integers(min_value=0, max_value=6),
    )
    def test_the_verdict_matches_the_measured_height(
        self, size: LabelSize, count: int, producer_lines: int
    ) -> None:
        """Zeichnen und Rechnen dürfen nicht auseinanderlaufen."""
        options = sale_options(
            size=size,
            ingredients=tuple(f"*Weizen*mehl Nummer {i}" for i in range(count)),
            producer="\n".join(f"Zeile {i}" for i in range(producer_lines)),
        )
        report = measure_label(BREAD, options, fonts=FONTS)
        assert report.fits == (report.required_height_px <= report.available_height_px)

    def test_a_gift_label_does_not_complain(self) -> None:
        many = tuple(f"Zutat {i}" for i in range(40))
        options = sale_options(size=LabelSize.SMALL, for_sale=False, ingredients=many)
        report = measure_label(BREAD, options, fonts=FONTS)
        assert report.issues(for_sale=False) == []

    def test_without_a_scalable_font_nothing_can_be_promised(self) -> None:
        report = measure_label(BREAD, sale_options(), fonts=FontSet(None, None))
        assert any(i.code == "no_scalable_font" for i in report.issues(for_sale=True))


class TestRendering:
    def test_producer_and_storage_hint_are_printed(self) -> None:
        options = sale_options(storage_hint="Trocken und bei Raumtemperatur lagern.")
        image = render_label(BREAD, options, fonts=FONTS)
        assert image.size == options.pixel_size()

    def test_the_producer_takes_space(self) -> None:
        """Auf dem großen Format passt beides ohne Stauchen - verglichen wird also
        dieselbe Schriftgröße. Auf einem knappen Format wählte die Einpassung mit
        Anschrift eine kleinere Stufe, und die Gesamthöhe sagte nichts mehr aus."""
        large = {"size": LabelSize.LARGE}
        with_producer = measure_label(BREAD, sale_options(**large), fonts=FONTS)
        without = measure_label(BREAD, sale_options(producer="", **large), fonts=FONTS)
        assert with_producer.required_height_px > without.required_height_px

    @pytest.mark.parametrize("size", list(LabelSize))
    def test_every_size_renders_for_sale(self, size: LabelSize) -> None:
        options = sale_options(size=size, storage_hint="Trocken lagern.")
        assert render_label(BREAD, options, fonts=FONTS).size == options.pixel_size()


class TestReportIssues:
    def test_without_a_scalable_font_the_sizes_are_reported(self) -> None:
        report = measure_label(BREAD, sale_options(), fonts=FontSet(None, None))
        found = {issue.code for issue in report.issues(for_sale=True)}
        assert {"no_scalable_font", "font_too_small", "net_weight_too_small"} <= found

    def test_the_messages_use_a_decimal_comma(self) -> None:
        report = measure_label(BREAD, sale_options(), fonts=FontSet(None, None))
        issues = report.issues(for_sale=True)
        message = next(i.message for i in issues if i.code == "font_too_small")
        assert "1,20 mm" in message

    def test_a_huge_weight_does_not_fit_the_width(self) -> None:
        """12 345,68 kg in 6 mm hohen Ziffern sind breiter als 54 mm."""
        options = sale_options(size=LabelSize.SMALL, net_weight_g=12_345_678.0)
        report = measure_label(BREAD, options, fonts=FONTS)
        assert not report.net_weight_width_ok
        found = {i.code for i in report.issues(for_sale=True)}
        assert "net_weight_too_wide" in found
        assert "net_weight_too_small" not in found, "dieselbe Ursache nur einmal melden"

    def test_a_gift_label_reports_content_that_cannot_fit(self) -> None:
        title = " ".join(["Vollkornbrot"] * 40)
        options = sale_options(size=LabelSize.SMALL, for_sale=False, title=title)
        report = measure_label(BREAD, options, fonts=FONTS)
        assert not report.fixed_part_fits
        assert [i.code for i in report.issues(for_sale=False)] == ["does_not_fit"]

    def test_without_a_net_weight_no_digits_are_required(self) -> None:
        report = measure_label(BREAD, sale_options(net_weight_g=0.0), fonts=FONTS)
        assert report.required_digit_mm == 0.0
        assert report.net_weight_width_ok

    def test_render_and_measure_agree(self) -> None:
        options = sale_options()
        image, report = render_and_measure(BREAD, options, fonts=FONTS)
        assert image.size == options.pixel_size()
        assert report == measure_label(BREAD, options, fonts=FONTS)

    def test_the_system_fonts_are_used_by_default(self) -> None:
        assert measure_label(BREAD, sale_options()).scalable_font == FONTS.is_scalable


class TestFontSizing:
    """Die kleinste Schriftgröße, bei der ein Zeichen hoch genug gedruckt wird."""

    def test_both_cuts_reach_the_height(self) -> None:
        size = FONTS.size_for_ink("x", 20.0)
        assert size is not None
        assert ink_height(FONTS.get(size), "x") >= 20
        assert ink_height(FONTS.get(size, bold=True), "x") >= 20

    @given(height=st.floats(min_value=1.0, max_value=80.0))
    def test_the_size_is_the_smallest_that_reaches_the_height(self, height: float) -> None:
        size = FONTS.size_for_ink("0123456789", height, cuts=(True,))
        assert size is not None
        assert ink_height(FONTS.get(size, bold=True), "0123456789") >= height
        if size > 1:
            assert ink_height(FONTS.get(size - 1, bold=True), "0123456789") < height

    def test_glyphs_without_ink_have_no_size(self) -> None:
        assert FONTS.size_for_ink(" ", 10.0) is None

    def test_a_bitmap_font_cannot_be_sized(self) -> None:
        assert FontSet(None, None).size_for_ink("x", 10.0) is None

    def test_the_result_is_remembered(self) -> None:
        font_set = load_font_set()
        first = font_set.size_for_ink("x", 12.0)
        assert font_set.size_for_ink("x", 12.0) == first

    def test_no_glyphs_have_no_ink(self) -> None:
        assert ink_height(FONTS.get(20), "") == 0


@pytest.mark.gui
class TestLabelDialog:
    @pytest.fixture
    def dialog(self, qapp: object, tmp_path: Path):  # type: ignore[no-untyped-def]
        del qapp
        from brotrechner.core.analysis import ResolvedItem, analyze
        from brotrechner.core.models import Category, Ingredient
        from brotrechner.gui.dialogs.label_dialog import LabelDialog

        flour = Ingredient(
            name="Weizenmehl Type 550",
            category=Category.FLOUR,
            nutrients=Nutrients(energy_kcal=341, carbs=70.0, protein=11.0, fiber=4.0, water=13.5),
            flour_percent=100.0,
            label_name="*Weizen*mehl Type 550",
            allergens=frozenset({Allergen.WHEAT}),
        )
        water = Ingredient(name="Wasser", nutrients=Nutrients(water=100.0), allergens=frozenset())
        analysis = analyze([ResolvedItem(flour, 500), ResolvedItem(water, 350)], baked_weight_g=750)
        widget = LabelDialog(analysis, recipe_name="Weizenbrot", default_dir=tmp_path)
        yield widget
        widget.close()

    def test_sale_mode_starts_off(self, dialog: object) -> None:
        assert not dialog.chk_for_sale.isChecked()  # type: ignore[attr-defined]
        assert dialog.txt_producer.isHidden()  # type: ignore[attr-defined]

    def test_switching_it_on_asks_for_the_producer(self, dialog: object) -> None:
        dialog.chk_for_sale.setChecked(True)  # type: ignore[attr-defined]
        assert not dialog.txt_producer.isHidden()  # type: ignore[attr-defined]
        assert dialog.chk_best_before.isChecked(), "MHD ist Pflicht"  # type: ignore[attr-defined]
        assert "Anschrift" in dialog.lbl_issues.text()  # type: ignore[attr-defined]

    def test_the_options_carry_the_sale_fields(self, dialog: object) -> None:
        dialog.chk_for_sale.setChecked(True)  # type: ignore[attr-defined]
        dialog.txt_producer.setPlainText(PRODUCER)  # type: ignore[attr-defined]
        dialog.txt_storage.setText("Trocken lagern.")  # type: ignore[attr-defined]
        options = dialog._options(dpi=110)  # type: ignore[attr-defined]
        assert options.for_sale
        assert options.producer == PRODUCER
        assert options.storage_hint == "Trocken lagern."

    def test_a_complete_sale_label_has_no_issues(self, dialog: object) -> None:
        dialog.chk_for_sale.setChecked(True)  # type: ignore[attr-defined]
        dialog.txt_producer.setPlainText(PRODUCER)  # type: ignore[attr-defined]
        assert dialog.lbl_issues.isHidden()  # type: ignore[attr-defined]

    def test_saving_with_open_issues_asks_first(
        self, dialog: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from PySide6.QtWidgets import QMessageBox

        asked: list[str] = []

        def answer_no(_parent: object, title: str, *_rest: object) -> int:
            asked.append(title)
            return int(QMessageBox.StandardButton.No)

        monkeypatch.setattr(QMessageBox, "question", answer_no)
        monkeypatch.setattr(QMessageBox, "information", lambda *_a: None)
        dialog.chk_for_sale.setChecked(True)  # type: ignore[attr-defined]
        dialog._on_save()  # type: ignore[attr-defined]
        assert asked == ["Pflichtangaben unvollständig"]
        assert list(tmp_path.glob("*.png")) == []

    def test_saving_anyway_writes_the_file(
        self, dialog: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from PySide6.QtWidgets import QMessageBox

        monkeypatch.setattr(
            QMessageBox, "question", lambda *_a, **_k: int(QMessageBox.StandardButton.Yes)
        )
        monkeypatch.setattr(QMessageBox, "information", lambda *_a: None)
        dialog.chk_for_sale.setChecked(True)  # type: ignore[attr-defined]
        dialog._on_save()  # type: ignore[attr-defined]
        assert len(list(tmp_path.glob("*.png"))) == 1

    def test_switching_it_off_hides_the_fields_again(self, dialog: object) -> None:
        dialog.chk_for_sale.setChecked(True)  # type: ignore[attr-defined]
        dialog.chk_for_sale.setChecked(False)  # type: ignore[attr-defined]
        assert dialog.txt_producer.isHidden()  # type: ignore[attr-defined]
        assert dialog.txt_storage.isHidden()  # type: ignore[attr-defined]

    def test_the_producer_is_only_printed_for_sale(self, dialog: object) -> None:
        dialog.chk_for_sale.setChecked(True)  # type: ignore[attr-defined]
        dialog.txt_producer.setPlainText(PRODUCER)  # type: ignore[attr-defined]
        dialog.chk_for_sale.setChecked(False)  # type: ignore[attr-defined]
        assert dialog._options(dpi=110).producer == ""  # type: ignore[attr-defined]

    def test_a_gift_label_is_saved_without_asking(
        self, dialog: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from PySide6.QtWidgets import QMessageBox

        asked: list[object] = []
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **_k: asked.append(a))
        monkeypatch.setattr(QMessageBox, "information", lambda *_a: None)
        dialog._on_save()  # type: ignore[attr-defined]
        assert asked == []
        assert len(list(tmp_path.glob("*.png"))) == 1

    def test_printing_with_open_issues_asks_first(
        self, dialog: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from PySide6.QtWidgets import QMessageBox

        from brotrechner.gui.dialogs import label_dialog

        opened: list[object] = []
        monkeypatch.setattr(
            QMessageBox, "question", lambda *_a, **_k: int(QMessageBox.StandardButton.No)
        )
        monkeypatch.setattr(label_dialog, "QPrintDialog", lambda *a: opened.append(a))
        dialog.chk_for_sale.setChecked(True)  # type: ignore[attr-defined]
        dialog._on_print()  # type: ignore[attr-defined]
        assert opened == []

    def test_save_as_with_open_issues_asks_first(
        self, dialog: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        opened: list[object] = []
        monkeypatch.setattr(
            QMessageBox, "question", lambda *_a, **_k: int(QMessageBox.StandardButton.No)
        )
        monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a: opened.append(a))
        dialog.chk_for_sale.setChecked(True)  # type: ignore[attr-defined]
        dialog._on_save_as()  # type: ignore[attr-defined]
        assert opened == []

    def test_the_label_is_checked_at_the_printing_resolution(self, dialog: object) -> None:
        dialog.cmb_dpi.setCurrentIndex(2)  # type: ignore[attr-defined]
        assert "600 dpi" in dialog.lbl_dimensions.text()  # type: ignore[attr-defined]
