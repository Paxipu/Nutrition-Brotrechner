"""Portionen im PDF-Bericht: Werte, Anzahl und Preis je Portion."""

from __future__ import annotations

from pathlib import Path

import pytest

from brotrechner.core.analysis import RecipeAnalysis, ResolvedItem, analyze
from brotrechner.core.models import Ingredient
from brotrechner.core.portions import Portion
from brotrechner.core.rounding import declare_energy, declare_nutrient
from brotrechner.export import report
from brotrechner.i18n import format_currency

pytestmark = pytest.mark.skipif(not report.is_available(), reason="reportlab nicht installiert")


@pytest.fixture
def make(flour: Ingredient, water: Ingredient, salt: Ingredient):  # type: ignore[no-untyped-def]
    def build(portion: Portion | None, *, baked: float = 1500.0) -> RecipeAnalysis:
        return analyze(
            [ResolvedItem(flour, 1000.0), ResolvedItem(water, 700.0), ResolvedItem(salt, 20.0)],
            baked_weight_g=baked,
            portion=portion,
        )

    return build


def _texts(table: object) -> list[list[str]]:
    """Die Zellen einer Tabelle als Text - auch die umbrechenden Absätze."""
    rows: list[list[str]] = []
    for row in table._cellvalues:  # type: ignore[attr-defined]
        rows.append([cell if isinstance(cell, str) else cell.getPlainText() for cell in row])
    return rows


def _overflowing(table: object, *, size: float) -> list[str]:
    """Zellen, deren Text breiter ist als ihre Spalte samt Innenabstand.

    Einfacher Text bricht in einer reportlab-Tabelle nicht um, er läuft in die
    Nachbarzelle. Absätze brechen um und zählen nicht.
    """
    from reportlab.pdfbase.pdfmetrics import stringWidth

    padding = 10.0  # LEFTPADDING 5 und RIGHTPADDING 5 der Nährwerttabelle
    widths = table._colWidths  # type: ignore[attr-defined]
    too_wide: list[str] = []
    for index, row in enumerate(table._cellvalues):  # type: ignore[attr-defined]
        font = "Helvetica-Bold" if index == 0 else "Helvetica"
        for column, cell in enumerate(row):
            if isinstance(cell, str) and stringWidth(cell, font, size) + padding > widths[column]:
                too_wide.append(cell)
    return too_wide


class TestNutritionTable:
    def test_without_a_portion_nothing_changes(self, make) -> None:  # type: ignore[no-untyped-def]
        header = _texts(report._nutrition_table(make(None)))[0]
        assert header == ["Nährstoff", "je 100 g", "Bandbreite", "% RM", "Ampel"]

    def test_a_column_per_portion(self, make) -> None:  # type: ignore[no-untyped-def]
        analysis = make(Portion("Scheibe", 50.0))
        rows = _texts(report._nutrition_table(analysis))
        assert rows[0] == [
            "Nährstoff",
            "je 100 g",
            "je Scheibe (50 g)",
            "Bandbreite",
            "% RM",
            "Ampel",
        ]
        by_name = {row[0]: row[2] for row in rows[1:]}
        per_portion = analysis.per_portion
        assert by_name["Brennwert"] == declare_energy(per_portion.energy_kcal)
        assert by_name["Salz"] == declare_nutrient("salt", per_portion.salt).text

    def test_without_a_baked_weight_there_is_no_column(self, make) -> None:  # type: ignore[no-untyped-def]
        rows = _texts(report._nutrition_table(make(Portion("Scheibe", 50.0), baked=0.0)))
        assert len(rows[0]) == 5

    @pytest.mark.parametrize("portion", [None, Portion("Scheibe", 50.0), Portion("Stück", 900.0)])
    def test_nothing_runs_into_the_next_cell(self, make, portion: Portion | None) -> None:  # type: ignore[no-untyped-def]
        assert _overflowing(report._nutrition_table(make(portion)), size=8.5) == []

    def test_the_whole_table_fits_the_page(self, make) -> None:  # type: ignore[no-untyped-def]
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm

        table = report._nutrition_table(make(Portion("Scheibe", 50.0)))
        assert sum(table._colWidths) <= A4[0] - 4 * cm


class TestFacts:
    def test_portion_and_count(self, make) -> None:  # type: ignore[no-untyped-def]
        cells = [
            cell
            for row in _texts(report._facts_table(make(Portion("Scheibe", 50.0))))
            for cell in row
        ]
        assert "Scheibe (50 g)" in cells
        assert "30" in cells

    def test_an_approximate_count(self, make) -> None:  # type: ignore[no-untyped-def]
        # 1500 g / 46 g = 32,6 Scheiben
        rows = _texts(report._facts_table(make(Portion("Scheibe", 46.0))))
        (row,) = [row for row in rows if row[0] == "Portion"]
        assert row[2:] == ["Portionen", "ca. 33"]

    def test_a_long_name_is_not_cut_in_the_middle(self, make) -> None:  # type: ignore[no-untyped-def]
        """Die Spalte ist breit genug für eine lange, aber übliche Bezeichnung."""
        from reportlab.pdfbase.pdfmetrics import stringWidth

        table = report._facts_table(make(Portion("Kastenweißbrotscheibe", 45.5)))
        padding = 12.0  # Vorgabe von reportlab: 6 pt links und rechts
        assert stringWidth("Kastenweißbrotscheibe", "Helvetica", 9) + padding <= table._colWidths[1]

    def test_without_a_portion_there_is_no_row(self, make) -> None:  # type: ignore[no-untyped-def]
        cells = [cell for row in _texts(report._facts_table(make(None))) for cell in row]
        assert "Portion" not in cells

    def test_a_portion_heavier_than_the_bread_has_no_count(self, make) -> None:  # type: ignore[no-untyped-def]
        rows = _texts(report._facts_table(make(Portion("Laib", 2000.0))))
        (row,) = [row for row in rows if row[0] == "Portion"]
        assert row[1] == "Laib (2000 g)"
        assert row[3] == "-"


class TestCost:
    def test_price_per_portion(self, make) -> None:  # type: ignore[no-untyped-def]
        analysis = make(Portion("Scheibe", 50.0))
        rows = _texts(report._cost_summary(analysis))
        assert ["Preis je Scheibe (50 g)", format_currency(analysis.cost_per_portion)] in rows

    def test_without_a_portion_no_price_per_portion(self, make) -> None:  # type: ignore[no-untyped-def]
        rows = _texts(report._cost_summary(make(None)))
        assert not any(row[0].startswith("Preis je Scheibe") for row in rows)


@pytest.mark.gui
def test_the_cost_summary_stays_on_one_page(qapp: object, tmp_path: Path) -> None:
    """Sonst stand „Preis je Portion“ allein oben auf der nächsten Seite."""
    del qapp
    pdf = pytest.importorskip("PySide6.QtPdf")
    from brotrechner.core.nutrients import Nutrients

    flour = Ingredient(
        name="Roggenmehl 1150",
        nutrients=Nutrients(energy_kcal=330, fat=1.4, carbs=67, sugar=1.0, protein=8, fiber=8),
        flour_percent=100.0,
        package_price=1.49,
        package_size_g=1000.0,
    )
    water = Ingredient(name="Wasser", nutrients=Nutrients(water=100.0))
    salt = Ingredient(
        name="Salz", nutrients=Nutrients(salt=100.0), package_price=0.5, package_size_g=500.0
    )
    analysis = analyze(
        [ResolvedItem(flour, 1000.0), ResolvedItem(water, 750.0), ResolvedItem(salt, 20.0)],
        baked_weight_g=1530.0,
        energy_kwh=1.4,
        portion=Portion("Kastenweißbrotscheibe", 45.5),
    )
    target = tmp_path / "bericht.pdf"
    report.write_report(target, analysis, recipe_name="Roggenbrot", notes="Test")
    document = pdf.QPdfDocument()
    document.load(str(target))
    pages = [document.getAllText(page).text() for page in range(document.pageCount())]
    (page,) = [text for text in pages if "Preis je Kastenweißbrotscheibe" in text]
    assert "Preis je 100 g" in page
    assert "Materialkosten" in page


@pytest.mark.gui
def test_the_pdf_contains_the_portion(qapp: object, make, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """Geprüft am geschriebenen PDF, nicht nur an den Tabellen davor."""
    del qapp
    pdf = pytest.importorskip("PySide6.QtPdf")

    target = tmp_path / "bericht.pdf"
    report.write_report(target, make(Portion("Scheibe", 50.0)), recipe_name="Roggenbrot")
    document = pdf.QPdfDocument()
    document.load(str(target))
    text = " ".join(document.getAllText(page).text() for page in range(document.pageCount()))
    for expected in ("je Scheibe (50 g)", "Portionen", "Preis je Scheibe (50 g)"):
        assert expected in text
