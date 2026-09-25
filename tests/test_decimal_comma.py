"""Zahlen erscheinen überall mit Dezimalkomma.

Rechner, Etikett und CSV schrieben schon „1,99 €“ - der PDF-Bericht dagegen
„1.99 €“ und „60.0 %“, die Zutatentabelle des Rechners „60.0 %“ neben
„600,0“ g, und einige Meldungen „Backverlust 40.0 %“.
"""

from __future__ import annotations

import re

import pytest

from brotrechner.core.analysis import RecipeAnalysis, ResolvedItem, analyze
from brotrechner.core.models import Ingredient
from brotrechner.core.nutrients import Nutrients
from brotrechner.core.plausibility import check_process
from brotrechner.core.validation import validate_ingredient
from brotrechner.export import report

#: Eine Zahl mit Dezimalpunkt, etwa "1.99" - aber nicht "5.1.0".
_DOT_DECIMAL = re.compile(r"(?<![\d.])\d+\.\d+(?![\d.])")


def _analysis(flour: Ingredient, water: Ingredient, salt: Ingredient) -> RecipeAnalysis:
    return analyze(
        [ResolvedItem(flour, 1000.0), ResolvedItem(water, 700.0), ResolvedItem(salt, 20.0)],
        baked_weight_g=1500.0,
        dough_weight_g=1650.0,
        energy_kwh=1.25,
    )


def _cells(table: object) -> list[str]:
    return [cell for row in table._cellvalues for cell in row if isinstance(cell, str)]  # type: ignore[attr-defined]


@pytest.mark.skipif(not report.is_available(), reason="reportlab nicht installiert")
class TestReport:
    def test_costs(self, flour: Ingredient, water: Ingredient, salt: Ingredient) -> None:
        cells = _cells(report._cost_summary(_analysis(flour, water, salt)))
        assert [c for c in cells if _DOT_DECIMAL.search(c)] == []
        assert any(re.fullmatch(r"\d+,\d\d €", c) for c in cells)

    def test_ingredients(self, flour: Ingredient, water: Ingredient, salt: Ingredient) -> None:
        cells = _cells(report._ingredients_table(_analysis(flour, water, salt)))
        assert [c for c in cells if _DOT_DECIMAL.search(c)] == []
        assert any(re.fullmatch(r"\d+,\d %", c) for c in cells)

    def test_facts(self, flour: Ingredient, water: Ingredient, salt: Ingredient) -> None:
        cells = _cells(report._facts_table(_analysis(flour, water, salt)))
        assert [c for c in cells if _DOT_DECIMAL.search(c)] == []
        assert "9,1 %" in cells  # Backverlust 1650 g -> 1500 g


class TestMessages:
    def test_bake_loss(self, flour: Ingredient, water: Ingredient) -> None:
        analysis = analyze(
            [ResolvedItem(flour, 1000.0), ResolvedItem(water, 700.0)], baked_weight_g=1020.0
        )
        (finding,) = [f for f in check_process(analysis) if f.code == "bake_loss"]
        assert "40,0 %" in finding.message

    def test_mass_balance(self) -> None:
        broken = Ingredient(name="Kaputt", nutrients=Nutrients(carbs=80.0, water=21.5))
        messages = [f.message for f in validate_ingredient(broken)]
        assert any("101,5 g" in message for message in messages)

    def test_flour_share_out_of_range(self) -> None:
        odd = Ingredient(name="Seltsam", flour_percent=100.5)
        messages = [f.message for f in validate_ingredient(odd)]
        assert any("100,5 %" in message for message in messages)


@pytest.mark.gui
class TestCalculator:
    @pytest.fixture
    def page(  # type: ignore[no-untyped-def]
        self, qapp: object, flour: Ingredient, water: Ingredient, salt: Ingredient
    ):
        del qapp
        from brotrechner.gui.pages.calculator import CalculatorPage
        from brotrechner.gui.theme import ThemeMode, resolve_tokens

        widget = CalculatorPage(resolve_tokens(ThemeMode.LIGHT))
        widget.set_ingredients([flour, water, salt])
        widget._items_model.add_item(flour, 1000.0)
        widget._items_model.add_item(water, 700.0)
        widget.spin_dough.setValue(1650.0)
        widget.spin_baked.setValue(1500.0)
        widget._recalculate()
        return widget

    def test_share_column(self, page: object) -> None:
        model = page._items_model  # type: ignore[attr-defined]
        share = model.data(model.index(0, 3))
        assert share == "58,8 %"

    def test_scale_factor_and_bake_loss(self, page: object) -> None:
        assert "×0,971" in page.lbl_summary.text()  # type: ignore[attr-defined]
        assert page.stat_weight._hint.text() == "Backverlust 9,1 %"  # type: ignore[attr-defined]
