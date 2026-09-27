"""Druck in Originalgröße.

Die Vorversion skalierte das Etikett auf die ganze Seite: Ein Etikett von
70 × 100 mm kam auf A4 als rund 190 × 270 mm heraus - ein Aufkleber in
Plakatgröße. Außerdem rechnete sie den Seitenrand doppelt ein, weil Qt den
Ursprung schon in den bedruckbaren Bereich legt.
"""

from __future__ import annotations

import itertools
from pathlib import Path
from typing import Any

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from brotrechner.export.printing import (
    A4_MM,
    MM_PER_INCH,
    Placement,
    PrintMode,
    SheetLayout,
    centered,
    fitted_sheet,
    one_per_page,
    sheet_placements,
)


class TestPlacement:
    def test_millimeters_become_device_pixels(self) -> None:
        placement = Placement(page=0, x_mm=25.4, y_mm=12.7, width_mm=70.0, height_mm=100.0)
        x, y, width, height = placement.to_pixels(1200)
        assert (x, y) == (1200.0, 600.0)
        assert width == pytest.approx(70 / MM_PER_INCH * 1200)
        assert height == pytest.approx(100 / MM_PER_INCH * 1200)

    def test_centered_on_a4(self) -> None:
        placement = centered((70.0, 100.0), (210.0, 297.0))
        assert (placement.x_mm, placement.y_mm) == (70.0, 98.5)
        assert (placement.width_mm, placement.height_mm) == (70.0, 100.0)

    def test_a_label_printer_page_is_filled_exactly(self) -> None:
        """Beim Etikettendrucker ist die Seite so groß wie das Etikett."""
        placement = centered((54.0, 86.0), (54.0, 86.0))
        assert (placement.x_mm, placement.y_mm) == (0.0, 0.0)

    @given(
        label=st.tuples(st.floats(1, 300), st.floats(1, 300)),
        page=st.tuples(st.floats(1, 500), st.floats(1, 500)),
        dpi=st.floats(36, 2400),
    )
    def test_the_size_never_depends_on_the_page(
        self, label: tuple[float, float], page: tuple[float, float], dpi: float
    ) -> None:
        placement = centered(label, page)
        _, _, width, height = placement.to_pixels(dpi)
        assert width / dpi * MM_PER_INCH == pytest.approx(label[0])
        assert height / dpi * MM_PER_INCH == pytest.approx(label[1])


class TestOnePerPage:
    def test_one_label_per_page(self) -> None:
        placements = one_per_page((70.0, 100.0), A4_MM, count=3)
        assert [p.page for p in placements] == [0, 1, 2]
        assert {(p.x_mm, p.y_mm) for p in placements} == {(70.0, 98.5)}

    def test_a_rotated_label_swaps_its_footprint(self) -> None:
        """Am Etikettendrucker, der das Etikett quer einzieht."""
        (placement,) = one_per_page((70.0, 100.0), (100.0, 70.0), count=1, rotated=True)
        assert placement == Placement(0, 0.0, 0.0, 100.0, 70.0, rotated=True)

    def test_no_labels_no_pages(self) -> None:
        assert one_per_page((70.0, 100.0), A4_MM, count=0) == []


#: Ein Bogen mit 2 × 4 Etiketten von 105 × 74 mm und 0,5 mm Rand oben.
SHEET = SheetLayout(columns=2, rows=4, margin_top_mm=0.5)
SHEET_LABEL = (105.0, 74.0)


class TestSheet:
    def test_the_cells_run_row_by_row(self) -> None:
        assert SHEET.cell(0, SHEET_LABEL) == (0.0, 0.5)
        assert SHEET.cell(1, SHEET_LABEL) == (105.0, 0.5)
        assert SHEET.cell(2, SHEET_LABEL) == (0.0, 74.5)
        assert SHEET.cell(7, SHEET_LABEL) == (105.0, 222.5)

    def test_gaps_lie_between_the_labels(self) -> None:
        layout = SheetLayout(
            columns=3, rows=1, margin_left_mm=5.0, margin_top_mm=10.0, gap_x_mm=2.5
        )
        assert layout.cell(2, (63.5, 38.1)) == (5.0 + 2 * 66.0, 10.0)

    def test_a_started_sheet_is_continued(self) -> None:
        """Fünf Etiketten ab Feld 7: zwei auf diesem Bogen, drei auf dem nächsten."""
        placements = sheet_placements(SHEET, SHEET_LABEL, count=5, first=7)
        assert [p.page for p in placements] == [0, 0, 1, 1, 1]
        assert (placements[0].x_mm, placements[0].y_mm) == (0.0, 222.5)
        assert (placements[2].x_mm, placements[2].y_mm) == (0.0, 0.5)

    @pytest.mark.parametrize("first", [0, 9])
    def test_the_first_label_must_be_on_the_sheet(self, first: int) -> None:
        with pytest.raises(ValueError, match="Erstes Etikett"):
            sheet_placements(SHEET, SHEET_LABEL, count=1, first=first)

    def test_an_exact_fit_is_fine(self) -> None:
        assert SHEET.problems(SHEET_LABEL) == []

    def test_a_grid_wider_than_the_sheet(self) -> None:
        problems = SheetLayout(columns=3, rows=1).problems(SHEET_LABEL)
        assert len(problems) == 1
        assert "315,0 mm breit" in problems[0]

    def test_a_grid_taller_than_the_sheet(self) -> None:
        problems = SheetLayout(columns=1, rows=5).problems(SHEET_LABEL)
        assert "370,0 mm hoch" in problems[0]

    def test_negative_distances(self) -> None:
        problems = SheetLayout(columns=1, rows=1, gap_x_mm=-1.0).problems(SHEET_LABEL)
        assert problems == ["Ränder und Abstände dürfen nicht negativ sein."]

    def test_a_sheet_without_cells(self) -> None:
        empty = SheetLayout(columns=0, rows=4)
        assert empty.problems(SHEET_LABEL) == [
            "Der Bogen braucht mindestens eine Spalte und eine Reihe."
        ]
        assert sheet_placements(empty, SHEET_LABEL, count=3) == []


class TestFittedSheet:
    @pytest.mark.parametrize(
        ("label", "grid"),
        [
            ((70.0, 100.0), (2, 2)),
            ((54.0, 86.0), (3, 3)),
            ((90.0, 130.0), (2, 2)),
            ((90.0, 90.0), (2, 2)),
            ((105.0, 74.0), (1, 3)),
        ],
    )
    def test_how_many_fit_on_a4(self, label: tuple[float, float], grid: tuple[int, int]) -> None:
        layout = fitted_sheet(label)
        assert (layout.columns, layout.rows) == grid
        assert layout.problems(label) == []

    def test_the_grid_is_centred(self) -> None:
        """2 × 70 mm und 5 mm Abstand sind 145 mm - bleiben links und rechts je 32,5."""
        layout = fitted_sheet((70.0, 100.0))
        assert layout.margin_left_mm == pytest.approx(32.5)
        assert layout.margin_top_mm == pytest.approx((297.0 - 205.0) / 2)

    def test_a_label_bigger_than_the_sheet_is_reported(self) -> None:
        layout = fitted_sheet((250.0, 100.0))
        assert layout.columns == 1
        assert layout.problems((250.0, 100.0))

    @given(
        label=st.tuples(st.floats(30.0, 297.0), st.floats(30.0, 297.0)),
        count=st.integers(min_value=1, max_value=40),
    )
    def test_labels_never_overlap_and_stay_on_the_sheet(
        self, label: tuple[float, float], count: int
    ) -> None:
        layout = fitted_sheet(label)
        assume(layout.problems(label) == [])
        placements = sheet_placements(layout, label, count=count)
        assert len(placements) == count
        tolerance = 1e-6
        for spot in placements:
            assert spot.x_mm >= -tolerance
            assert spot.y_mm >= -tolerance
            assert spot.x_mm + spot.width_mm <= A4_MM[0] + tolerance
            assert spot.y_mm + spot.height_mm <= A4_MM[1] + tolerance
        for a, b in itertools.combinations(placements, 2):
            if a.page != b.page:
                continue
            apart_x = (
                a.x_mm + a.width_mm <= b.x_mm + tolerance
                or b.x_mm + b.width_mm <= a.x_mm + tolerance
            )
            apart_y = (
                a.y_mm + a.height_mm <= b.y_mm + tolerance
                or b.y_mm + b.height_mm <= a.y_mm + tolerance
            )
            assert apart_x or apart_y


class TestPrintModes:
    def test_every_mode_has_a_german_name(self) -> None:
        assert [mode.label for mode in PrintMode] == [
            "Einzeln mitten aufs Blatt",
            "Etikettendrucker",
            "Etikettenbogen",
            "Mehrere auf A4 zum Ausschneiden",
        ]


def _drawn_rect(args: tuple[Any, ...]) -> tuple[float, float, float, float]:
    """Zielrechteck eines ``drawImage``-Aufrufs, gleich in welcher Aufrufform."""
    from PySide6.QtCore import QRect, QRectF

    first = args[0]
    if isinstance(first, (QRect, QRectF)):
        return (first.x(), first.y(), first.width(), first.height())
    image = args[2]
    return (float(first), float(args[1]), float(image.width()), float(image.height()))


@pytest.fixture
def dialog(qapp: object, tmp_path: Path):  # type: ignore[no-untyped-def]
    """Etikettdialog für ein einfaches Weizenbrot, ohne Bildschirm."""
    del qapp
    from brotrechner.core.analysis import ResolvedItem, analyze
    from brotrechner.core.models import Category, Ingredient
    from brotrechner.core.nutrients import Nutrients
    from brotrechner.gui.dialogs.label_dialog import LabelDialog

    flour = Ingredient(
        name="Weizenmehl Type 550",
        category=Category.FLOUR,
        nutrients=Nutrients(energy_kcal=341, carbs=70.0, protein=11.0, fiber=4.0, water=13.5),
        flour_percent=100.0,
        allergens=frozenset(),
    )
    water = Ingredient(name="Wasser", nutrients=Nutrients(water=100.0), allergens=frozenset())
    analysis = analyze([ResolvedItem(flour, 500), ResolvedItem(water, 350)], baked_weight_g=750)
    widget = LabelDialog(analysis, recipe_name="Weizenbrot", default_dir=tmp_path)
    yield widget
    widget.close()


def _select(combo: Any, data: object) -> None:
    """Wählt den Eintrag einer Auswahlliste über seinen Datenwert."""
    index = combo.findData(data)
    assert index >= 0, data
    combo.setCurrentIndex(index)


@pytest.mark.gui
class TestPrintingTheLabel:
    def _print(
        self,
        dialog: object,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        *,
        margin_mm: float = 0.0,
    ) -> tuple[tuple[float, float, float, float], float, Path]:
        from PySide6.QtCore import QMarginsF
        from PySide6.QtGui import QPageLayout, QPageSize, QPainter
        from PySide6.QtPrintSupport import QPrinter

        calls: list[tuple[Any, ...]] = []
        original = QPainter.drawImage

        def recording(self: QPainter, *args: Any) -> None:
            calls.append(args)
            original(self, *args)

        monkeypatch.setattr(QPainter, "drawImage", recording)
        target = tmp_path / "etikett.pdf"
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(str(target))
        printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        margins = QMarginsF(margin_mm, margin_mm, margin_mm, margin_mm)
        printer.setPageMargins(margins, QPageLayout.Unit.Millimeter)
        dialog._paint_to_printer(printer)  # type: ignore[attr-defined]
        assert len(calls) == 1
        # Ohne "fullPage" liegt der Ursprung des Painters in der Ecke des
        # bedruckbaren Bereichs - aufs Papier umgerechnet kommt der Rand dazu.
        x, y, width, height = _drawn_rect(calls[0])
        if not printer.fullPage():
            printable = printer.pageRect(QPrinter.Unit.DevicePixel)
            x, y = x + printable.x(), y + printable.y()
        return (x, y, width, height), printer.resolution(), target

    def test_the_label_keeps_its_size_on_a4(
        self, dialog: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (_, _, width, height), dpi, _ = self._print(dialog, tmp_path, monkeypatch)
        assert width / dpi * MM_PER_INCH == pytest.approx(70.0, abs=0.1)
        assert height / dpi * MM_PER_INCH == pytest.approx(100.0, abs=0.1)

    @pytest.mark.parametrize("margin_mm", [0.0, 20.0])
    def test_it_sits_in_the_middle_of_the_sheet(
        self, dialog: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, margin_mm: float
    ) -> None:
        """Auch mit Druckerrand - der Rand zählt nur einmal."""
        (x, y, width, height), dpi, _ = self._print(
            dialog, tmp_path, monkeypatch, margin_mm=margin_mm
        )
        centre_x = (x + width / 2) / dpi * MM_PER_INCH
        centre_y = (y + height / 2) / dpi * MM_PER_INCH
        assert centre_x == pytest.approx(105.0, abs=0.1)
        assert centre_y == pytest.approx(148.5, abs=0.1)

    def test_a_pdf_is_written(
        self, dialog: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, _, target = self._print(dialog, tmp_path, monkeypatch)
        assert target.read_bytes().startswith(b"%PDF")

    def test_the_custom_format_shows_its_fields(self, dialog: object) -> None:
        combo = dialog.cmb_size  # type: ignore[attr-defined]
        spin = dialog.spin_width  # type: ignore[attr-defined]
        assert not spin.isVisibleTo(dialog)
        combo.setCurrentIndex(combo.findData(None))
        assert spin.isVisibleTo(dialog)
        combo.setCurrentIndex(0)
        assert not spin.isVisibleTo(dialog)

    def test_the_custom_format_reaches_the_label(self, dialog: object) -> None:
        combo = dialog.cmb_size  # type: ignore[attr-defined]
        combo.setCurrentIndex(combo.findData(None))
        dialog.spin_width.setValue(105.0)  # type: ignore[attr-defined]
        dialog.spin_height.setValue(74.0)  # type: ignore[attr-defined]
        assert dialog._options(dpi=110).millimeters == (105.0, 74.0)  # type: ignore[attr-defined]
        assert "105 × 74 mm" in dialog.lbl_dimensions.text()  # type: ignore[attr-defined]

    def test_a_preset_ignores_the_fields(self, dialog: object) -> None:
        dialog.spin_width.setValue(105.0)  # type: ignore[attr-defined]
        assert dialog._options(dpi=110).custom_mm is None  # type: ignore[attr-defined]

    def test_a_custom_format_is_printed_at_its_size(
        self, dialog: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        combo = dialog.cmb_size  # type: ignore[attr-defined]
        combo.setCurrentIndex(combo.findData(None))
        dialog.spin_width.setValue(105.0)  # type: ignore[attr-defined]
        dialog.spin_height.setValue(74.0)  # type: ignore[attr-defined]
        (_, _, width, height), dpi, _ = self._print(dialog, tmp_path, monkeypatch)
        assert width / dpi * MM_PER_INCH == pytest.approx(105.0, abs=0.1)
        assert height / dpi * MM_PER_INCH == pytest.approx(74.0, abs=0.1)


@pytest.mark.gui
class TestPrintSettingsCard:
    @pytest.fixture
    def card(self, qapp: object):  # type: ignore[no-untyped-def]
        del qapp
        from brotrechner.gui.widgets.print_settings import PrintSettingsCard

        widget = PrintSettingsCard()
        yield widget
        widget.close()

    def test_single_asks_only_for_the_count(self, card: Any) -> None:
        assert card.spin_count.isVisibleTo(card)
        assert not card.chk_rotate.isVisibleTo(card)
        assert not card.spin_columns.isVisibleTo(card)
        assert not card.spin_first.isVisibleTo(card)

    def test_the_label_printer_can_rotate(self, card: Any) -> None:
        _select(card.cmb_mode, PrintMode.LABEL_PRINTER)
        assert card.chk_rotate.isVisibleTo(card)
        assert not card.spin_columns.isVisibleTo(card)

    def test_the_sheet_shows_its_grid(self, card: Any) -> None:
        _select(card.cmb_mode, PrintMode.SHEET)
        for widget in (
            card.spin_columns,
            card.spin_rows,
            card.spin_margin_left,
            card.spin_gap_y,
            card.spin_first,
        ):
            assert widget.isVisibleTo(card)
        assert not card.chk_rotate.isVisibleTo(card)

    def test_rotation_only_counts_at_the_label_printer(self, card: Any) -> None:
        _select(card.cmb_mode, PrintMode.LABEL_PRINTER)
        card.chk_rotate.setChecked(True)
        assert card.rotated()
        _select(card.cmb_mode, PrintMode.SHEET)
        assert not card.rotated()

    def test_the_first_label_stays_on_the_sheet(self, card: Any) -> None:
        _select(card.cmb_mode, PrintMode.SHEET)
        card.spin_first.setValue(8)
        card.spin_rows.setValue(2)
        assert card.spin_first.maximum() == 4
        assert card.spin_first.value() == 4

    @pytest.mark.parametrize(
        ("mode", "count", "expected"),
        [
            (PrintMode.SINGLE, 1, "1 Etikett, eines je Blatt"),
            (PrintMode.LABEL_PRINTER, 3, "3 Etiketten, eines je Seite"),
            (PrintMode.CUT_SHEET, 6, "6 Etiketten auf 2 Blättern (4 je Blatt)"),
            (PrintMode.CUT_SHEET, 4, "4 Etiketten auf 1 Blatt (4 je Blatt)"),
        ],
    )
    def test_the_summary(self, card: Any, mode: PrintMode, count: int, expected: str) -> None:
        _select(card.cmb_mode, mode)
        card.spin_count.setValue(count)
        card.update_summary((70.0, 100.0))
        assert card.lbl_summary.text() == expected

    def test_a_started_sheet_in_the_summary(self, card: Any) -> None:
        _select(card.cmb_mode, PrintMode.SHEET)
        card.spin_margin_top.setValue(0.5)
        card.spin_count.setValue(5)
        card.spin_first.setValue(7)
        card.update_summary(SHEET_LABEL)
        assert card.lbl_summary.text() == "5 Etiketten auf 2 Bögen (8 je Bogen)"

    def test_a_grid_that_does_not_fit_is_shown(self, card: Any) -> None:
        _select(card.cmb_mode, PrintMode.SHEET)
        card.spin_columns.setValue(3)
        card.update_summary(SHEET_LABEL)
        assert "breit" in card.lbl_summary.text()
        assert card.problems(SHEET_LABEL)

    def test_changes_are_announced(self, card: Any) -> None:
        seen: list[bool] = []
        card.changed.connect(lambda: seen.append(True))
        card.spin_count.setValue(4)
        assert seen


@pytest.mark.gui
class TestPrintingEachMode:
    """Jede Druckart einmal durch den Dialog in ein PDF gedruckt."""

    def _print(
        self, dialog: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> tuple[int, list[tuple[float, float, float, float]], tuple[float, float], Path]:
        """Seitenzahl, gezeichnete Flächen in mm, Papier in mm und die PDF-Datei."""
        from PySide6.QtGui import QPainter
        from PySide6.QtPrintSupport import QPrinter

        from brotrechner.gui.printing import paper_mm

        calls: list[tuple[Any, ...]] = []
        new_pages: list[bool] = []
        draw_image = QPainter.drawImage
        new_page = QPrinter.newPage

        def recording_draw(self: QPainter, *args: Any) -> None:
            calls.append(args)
            draw_image(self, *args)

        def recording_page(self: QPrinter) -> bool:
            new_pages.append(True)
            return bool(new_page(self))

        monkeypatch.setattr(QPainter, "drawImage", recording_draw)
        monkeypatch.setattr(QPrinter, "newPage", recording_page)
        target = tmp_path / "druck.pdf"
        printer = dialog._new_printer()
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(str(target))
        dialog._paint_to_printer(printer)
        scale = MM_PER_INCH / printer.resolution()
        rects = []
        for call in calls:
            x, y, width, height = _drawn_rect(call)
            rects.append((x * scale, y * scale, width * scale, height * scale))
        return len(new_pages) + 1, rects, paper_mm(printer), target

    def test_a_started_label_sheet(
        self, dialog: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Fünf Etiketten ab dem siebten Feld eines Bogens mit 2 × 4."""
        _select(dialog.cmb_size, None)
        dialog.spin_width.setValue(105.0)
        dialog.spin_height.setValue(74.0)
        card = dialog.print_card
        _select(card.cmb_mode, PrintMode.SHEET)
        card.spin_margin_top.setValue(0.5)
        card.spin_count.setValue(5)
        card.spin_first.setValue(7)
        pages, rects, paper, _ = self._print(dialog, tmp_path, monkeypatch)
        assert pages == 2
        assert paper == pytest.approx(A4_MM, abs=0.1)
        corners = [(round(x, 1), round(y, 1)) for x, y, _, _ in rects]
        assert corners == [(0.0, 222.5), (105.0, 222.5), (0.0, 0.5), (105.0, 0.5), (0.0, 74.5)]

    def test_the_label_printer_prints_one_page_per_label(
        self, dialog: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        card = dialog.print_card
        _select(card.cmb_mode, PrintMode.LABEL_PRINTER)
        card.spin_count.setValue(3)
        pages, rects, paper, _ = self._print(dialog, tmp_path, monkeypatch)
        assert pages == 3
        assert paper == pytest.approx((70.0, 100.0), abs=0.1)
        for rect in rects:
            assert rect == pytest.approx((0.0, 0.0, 70.0, 100.0), abs=0.1)

    def test_a_rotated_label_printer_page_is_landscape(
        self, dialog: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Gedreht liegt der Kopf des Etiketts rechts - dort steht der grüne Titel."""
        pdf = pytest.importorskip("PySide6.QtPdf")
        from PIL import Image
        from PySide6.QtCore import QSize

        card = dialog.print_card
        _select(card.cmb_mode, PrintMode.LABEL_PRINTER)
        card.chk_rotate.setChecked(True)
        pages, _, paper, target = self._print(dialog, tmp_path, monkeypatch)
        assert pages == 1
        assert paper == pytest.approx((100.0, 70.0), abs=0.1)

        document = pdf.QPdfDocument()
        document.load(str(target))
        page = document.render(0, QSize(400, 280))
        png = tmp_path / "seite.png"
        page.save(str(png))
        with Image.open(png) as image:
            rgb = image.convert("RGB")
        width, height = rgb.size

        def green(x_range: range) -> int:
            """Pixel in der grünen Akzentfarbe des Titels."""
            count = 0
            for x in x_range:
                for y in range(height):
                    red, grn, blue = rgb.getpixel((x, y))  # type: ignore[misc]
                    count += grn > red + 40 and grn > blue + 20
            return count

        right = green(range(width * 3 // 4, width))
        left = green(range(width // 4))
        assert right > 5 * max(1, left)

    def test_several_on_a4_to_cut_out(
        self, dialog: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        card = dialog.print_card
        _select(card.cmb_mode, PrintMode.CUT_SHEET)
        card.spin_count.setValue(6)
        pages, rects, _, _ = self._print(dialog, tmp_path, monkeypatch)
        assert pages == 2
        layout = fitted_sheet((70.0, 100.0))
        expected = [v for index in range(6) for v in layout.cell(index % 4, (70.0, 100.0))]
        assert [v for x, y, _, _ in rects for v in (x, y)] == pytest.approx(expected, abs=0.1)

    def test_a_grid_that_does_not_fit_stops_printing(
        self, dialog: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from PySide6.QtWidgets import QMessageBox

        from brotrechner.gui.dialogs import label_dialog

        warned: list[str] = []
        opened: list[object] = []
        monkeypatch.setattr(QMessageBox, "warning", lambda _p, title, *_a: warned.append(title))
        monkeypatch.setattr(label_dialog, "QPrintDialog", lambda *a: opened.append(a))
        monkeypatch.setattr(label_dialog, "QPrintPreviewDialog", lambda *a: opened.append(a))
        card = dialog.print_card
        _select(card.cmb_mode, PrintMode.SHEET)
        card.spin_columns.setValue(4)
        dialog._on_print()
        dialog._on_print_preview()
        assert warned == ["Raster passt nicht", "Raster passt nicht"]
        assert opened == []
