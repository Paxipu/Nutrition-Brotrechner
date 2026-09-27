"""Rezeptstufen in Bericht, Rezeptvorschau und CSV."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from brotrechner.core.analysis import RecipeAnalysis, ResolvedItem, analyze
from brotrechner.core.models import Ingredient, Recipe, RecipeItem, Stage
from brotrechner.export import report
from brotrechner.export.table import write_analysis_csv


@pytest.fixture
def staged(flour: Ingredient, water: Ingredient, salt: Ingredient) -> RecipeAnalysis:
    return analyze(
        [
            ResolvedItem(flour, 300.0),
            ResolvedItem(water, 150.0),
            ResolvedItem(salt, 10.0),
            ResolvedItem(flour, 200.0, Stage.SOURDOUGH),
            ResolvedItem(water, 200.0, Stage.SOURDOUGH),
        ],
        baked_weight_g=750.0,
    )


@pytest.fixture
def plain(flour: Ingredient, water: Ingredient) -> RecipeAnalysis:
    return analyze([ResolvedItem(flour, 500.0), ResolvedItem(water, 350.0)], baked_weight_g=750.0)


class TestRatioText:
    def test_with_flour(self, staged: RecipeAnalysis) -> None:
        assert staged.stages[0].ratio_text == "TA 200 · 40 % des Mehls"

    def test_without_flour(self, flour: Ingredient, water: Ingredient) -> None:
        analysis = analyze(
            [ResolvedItem(flour, 500.0), ResolvedItem(water, 100.0, Stage.SOAKER)],
            baked_weight_g=500.0,
        )
        assert analysis.stages[0].ratio_text == "ohne Mehl"


def _texts(table: object) -> list[list[str]]:
    return [
        [cell if isinstance(cell, str) else cell.getPlainText() for cell in row]
        for row in table._cellvalues  # type: ignore[attr-defined]
    ]


@pytest.mark.skipif(not report.is_available(), reason="reportlab nicht installiert")
class TestReport:
    def test_without_stages_nothing_changes(self, plain: RecipeAnalysis) -> None:
        rows = _texts(report._ingredients_table(plain))
        assert [row[0] for row in rows] == ["Zutat", "Roggenvollkornmehl", "Wasser"]

    def test_each_stage_has_a_heading(self, staged: RecipeAnalysis) -> None:
        rows = _texts(report._ingredients_table(staged))
        assert [row[0] for row in rows] == [
            "Zutat",
            "Sauerteig · TA 200 · 40 % des Mehls",
            "Roggenvollkornmehl",
            "Wasser",
            "Hauptteig · TA 150 · 60 % des Mehls",
            "Roggenvollkornmehl",
            "Wasser",
            "Salz",
        ]

    def test_a_heading_spans_the_table(self, staged: RecipeAnalysis) -> None:
        table = report._ingredients_table(staged)
        spans = [
            command
            for command in table._spanCmds  # type: ignore[attr-defined]
            if command[0] == "SPAN"
        ]
        assert [(start, end) for _, start, end in spans] == [((0, 1), (-1, 1)), ((0, 4), (-1, 4))]

    @pytest.mark.gui
    def test_the_pdf_names_the_stages(
        self, qapp: object, staged: RecipeAnalysis, tmp_path: Path
    ) -> None:
        del qapp
        pdf = pytest.importorskip("PySide6.QtPdf")
        target = tmp_path / "bericht.pdf"
        report.write_report(target, staged, recipe_name="Roggenbrot")
        document = pdf.QPdfDocument()
        document.load(str(target))
        text = " ".join(document.getAllText(page).text() for page in range(document.pageCount()))
        assert "Sauerteig · TA 200 · 40 % des Mehls" in text


class TestCsv:
    def test_a_column_with_the_stage(self, staged: RecipeAnalysis, tmp_path: Path) -> None:
        target = tmp_path / "auswertung.csv"
        write_analysis_csv(target, staged)
        with target.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle, delimiter=";"))
        assert rows[0][-1] == "Stufe"
        assert [row[-1] for row in rows[1:6]] == [
            "Hauptteig",
            "Hauptteig",
            "Hauptteig",
            "Sauerteig",
            "Sauerteig",
        ]


@pytest.mark.gui
class TestPreview:
    @pytest.fixture
    def page(  # type: ignore[no-untyped-def]
        self, qapp: object, flour: Ingredient, water: Ingredient, salt: Ingredient
    ):
        del qapp
        from brotrechner.gui.pages.recipes import RecipesPage
        from brotrechner.gui.theme import ThemeMode, resolve_tokens

        widget = RecipesPage(resolve_tokens(ThemeMode.LIGHT))
        widget.set_data([], [flour, water, salt])
        return widget

    def _preview(self, page: object, items: list[RecipeItem], ingredients: list[Ingredient]) -> str:
        recipe = Recipe(name="Roggenbrot", items=items, baked_weight_g=750.0)
        page.set_data([recipe], ingredients)  # type: ignore[attr-defined]
        assert page.select_recipe("Roggenbrot")  # type: ignore[attr-defined]
        return str(page.lbl_preview.text())  # type: ignore[attr-defined]

    def test_grouped_by_stage(
        self, page: object, flour: Ingredient, water: Ingredient, salt: Ingredient
    ) -> None:
        items = [
            RecipeItem(flour.key, flour.name, flour.manufacturer, 300.0),
            RecipeItem(salt.key, salt.name, salt.manufacturer, 10.0),
            RecipeItem(flour.key, flour.name, flour.manufacturer, 200.0, Stage.SOURDOUGH),
            RecipeItem(water.key, water.name, water.manufacturer, 200.0, Stage.SOURDOUGH),
        ]
        text = self._preview(page, items, [flour, water, salt])
        assert text.index("Sauerteig") < text.index("Hauptteig")
        assert "TA 200 · 40 % des Mehls" in text

    def test_without_stages_no_headings(
        self, page: object, flour: Ingredient, water: Ingredient, salt: Ingredient
    ) -> None:
        items = [RecipeItem(flour.key, flour.name, flour.manufacturer, 500.0)]
        text = self._preview(page, items, [flour, water, salt])
        assert "Hauptteig" not in text
