"""Druck in Originalgröße.

Die Vorversion skalierte das Etikett auf die ganze Seite: Ein Etikett von
70 × 100 mm kam auf A4 als rund 190 × 270 mm heraus - ein Aufkleber in
Plakatgröße. Außerdem rechnete sie den Seitenrand doppelt ein, weil Qt den
Ursprung schon in den bedruckbaren Bereich legt.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from brotrechner.export.printing import MM_PER_INCH, Placement, centered


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


def _drawn_rect(args: tuple[Any, ...]) -> tuple[float, float, float, float]:
    """Zielrechteck eines ``drawImage``-Aufrufs, gleich in welcher Aufrufform."""
    from PySide6.QtCore import QRect, QRectF

    first = args[0]
    if isinstance(first, (QRect, QRectF)):
        return (first.x(), first.y(), first.width(), first.height())
    image = args[2]
    return (float(first), float(args[1]), float(image.width()), float(image.height()))


@pytest.mark.gui
class TestPrintingTheLabel:
    @pytest.fixture
    def dialog(self, qapp: object, tmp_path: Path):  # type: ignore[no-untyped-def]
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
