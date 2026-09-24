"""Rundung der Nährwertangabe nach der Leitlinie der EU-Kommission (Dezember 2012).

Quelle: *Guidance document for competent authorities for the control of
compliance with EU legislation ... with regard to the setting of tolerances for
nutrient values declared on a label*, Abschnitt "Rounding guidelines".
Vorher zeigte das Etikett jeden Wert mit einer Nachkommastelle (Salz mit
zweien) - "45,3 g" statt "45 g", "0,4 g" statt "< 0,5 g", "1,23 g" statt "1,2 g".
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from brotrechner.core.nutrients import Nutrients
from brotrechner.core.rounding import (
    DECLARED_FIELDS,
    as_declarable,
    declare_energy,
    declare_nutrient,
)

MAIN = ("fat", "carbs", "sugar", "protein", "fiber")


class TestMainNutrients:
    """Fett, Kohlenhydrate, Zucker, Eiweiß und Ballaststoffe."""

    @pytest.mark.parametrize("field", MAIN)
    @pytest.mark.parametrize(
        ("grams", "text"),
        [
            (45.34, "45 g"),
            (45.5, "46 g"),
            (10.0, "10 g"),
            (9.96, "10 g"),
            (9.94, "9,9 g"),
            (2.45, "2,5 g"),
            (0.51, "0,5 g"),
            (0.5, "< 0,5 g"),
            (0.43, "< 0,5 g"),
            (0.0, "0 g"),
        ],
    )
    def test_bands(self, field: str, grams: float, text: str) -> None:
        assert declare_nutrient(field, grams).text == text


class TestSaturatedFat:
    @pytest.mark.parametrize(
        ("grams", "text"),
        [
            (12.3, "12 g"),
            (4.44, "4,4 g"),
            (0.25, "0,3 g"),
            (0.11, "0,1 g"),
            (0.1, "< 0,1 g"),
            (0.08, "< 0,1 g"),
            (0.0, "0 g"),
        ],
    )
    def test_bands(self, grams: float, text: str) -> None:
        assert declare_nutrient("saturated_fat", grams).text == text


class TestSalt:
    @pytest.mark.parametrize(
        ("grams", "text"),
        [
            (2.25, "2,3 g"),
            (1.234, "1,2 g"),
            (1.0, "1,0 g"),
            (0.996, "1,0 g"),
            (0.456, "0,46 g"),
            (0.0126, "0,01 g"),
            (0.0125, "< 0,01 g"),
            (0.004, "< 0,01 g"),
            (0.0, "0 g"),
        ],
    )
    def test_bands(self, grams: float, text: str) -> None:
        assert declare_nutrient("salt", grams).text == text


class TestEnergy:
    def test_both_units_are_whole_numbers(self) -> None:
        """227,4 kcal x 4,184 = 951,4 kJ."""
        assert declare_energy(227.4) == "951 kJ / 227 kcal"

    def test_halves_are_rounded_up(self) -> None:
        assert declare_energy(227.5) == "952 kJ / 228 kcal"

    def test_zero(self) -> None:
        assert declare_energy(0.0) == "0 kJ / 0 kcal"

    @pytest.mark.parametrize("bad", [-1.0, math.nan, math.inf])
    def test_nonsense_is_rejected(self, bad: float) -> None:
        with pytest.raises(ValueError, match="Brennwert"):
            declare_energy(bad)


class TestContract:
    def test_the_declared_fields(self) -> None:
        assert set(DECLARED_FIELDS) == {*MAIN, "saturated_fat", "salt"}

    def test_the_amount_is_numeric(self) -> None:
        declared = declare_nutrient("carbs", 45.34)
        assert declared.amount == 45.0
        assert not declared.below

    def test_below_the_limit_carries_the_limit(self) -> None:
        declared = declare_nutrient("sugar", 0.3)
        assert declared.below
        assert declared.amount == 0.5

    def test_salt_below_the_limit_carries_the_shown_limit(self) -> None:
        """Angegeben wird "< 0,01 g", also ist 0,01 die Zahl - nicht 0,0125."""
        assert declare_nutrient("salt", 0.012).amount == 0.01

    def test_water_has_no_declaration(self) -> None:
        with pytest.raises(ValueError, match="water"):
            declare_nutrient("water", 40.0)

    @pytest.mark.parametrize("bad", [-0.01, math.nan, math.inf, -math.inf])
    def test_nonsense_is_rejected(self, bad: float) -> None:
        with pytest.raises(ValueError, match="fat"):
            declare_nutrient("fat", bad)


#: Bis zu diesem Gehalt lautet die Angabe "< x g" (Salz: 0,0125 g = 0,005 g Natrium).
LIMITS = {"salt": 0.0125, "saturated_fat": 0.1} | dict.fromkeys(MAIN, 0.5)


#: Rundungsschritt oberhalb der "<"-Schranke je Feld und Größenordnung.
def _step(field: str, grams: float) -> float:
    if field == "salt":
        return 0.1 if grams >= 1.0 else 0.01
    return 1.0 if grams >= 10.0 else 0.1


class TestProperties:
    @given(
        field=st.sampled_from(DECLARED_FIELDS),
        grams=st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
    )
    def test_the_declared_amount_is_close_to_the_true_one(self, field: str, grams: float) -> None:
        """Höchstens ein halber Rundungsschritt Abstand - oder unter der Schranke."""
        declared = declare_nutrient(field, grams)
        if declared.below:
            assert 0.0 < grams <= LIMITS[field]
            assert declared.amount <= LIMITS[field]
        else:
            assert abs(declared.amount - grams) <= _step(field, grams) / 2 + 1e-9

    @given(
        field=st.sampled_from(DECLARED_FIELDS),
        low=st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
        high=st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
    )
    def test_rounding_keeps_the_order(self, field: str, low: float, high: float) -> None:
        """Mehr Inhalt ergibt nie eine kleinere Angabe."""
        low, high = sorted((low, high))
        assert declare_nutrient(field, low).amount <= declare_nutrient(field, high).amount

    @given(grams=st.floats(min_value=0.0, max_value=100.0, allow_nan=False))
    def test_the_text_uses_a_decimal_comma(self, grams: float) -> None:
        text = declare_nutrient("salt", grams).text
        assert "." not in text
        assert text.endswith(" g")


#: Ein Brot, dessen Werte in jedem Rundungsband liegen.
BREAD = Nutrients(
    energy_kcal=227.4,
    fat=1.44,
    saturated_fat=0.08,
    carbs=45.34,
    sugar=0.43,
    protein=7.96,
    salt=1.234,
    fiber=4.0,
    water=40.0,
)


class TestAsDeclarable:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [(3.5, 3.5), (0.0, 0.0), (-1.0, 0.0), (math.nan, 0.0), (math.inf, 0.0)],
    )
    def test_only_positive_finite_values_pass(self, value: float, expected: float) -> None:
        assert as_declarable(value) == expected


class TestUsage:
    def test_the_label_shows_rounded_values(self) -> None:
        from brotrechner.export.label import _nutrition_rows

        rows = {label: value for label, value, *_ in _nutrition_rows(BREAD, show_fiber=True)}
        assert rows["Brennwert"] == "951 kJ / 227 kcal"
        assert rows["Fett"] == "1,4 g"
        assert rows["davon gesättigte Fettsäuren"] == "< 0,1 g"
        assert rows["Kohlenhydrate"] == "45 g"
        assert rows["davon Zucker"] == "< 0,5 g"
        assert rows["Eiweiß"] == "8,0 g"
        assert rows["Salz"] == "1,2 g"

    def test_broken_values_do_not_crash_the_label(self) -> None:
        from brotrechner.export.label import LabelOptions, render_label

        broken = Nutrients(energy_kcal=math.inf, fat=-1.0, salt=math.nan)
        image = render_label(broken, LabelOptions(dpi=72))
        assert image.size == LabelOptions(dpi=72).pixel_size()

    def test_the_report_shows_the_same_values(self) -> None:
        pytest.importorskip("reportlab")
        from brotrechner.core.analysis import RecipeAnalysis
        from brotrechner.export import report

        table = report._nutrition_table(RecipeAnalysis(per_100g=BREAD))
        shown = {row[0]: row[1] for row in table._cellvalues[1:]}
        assert shown["Kohlenhydrate"] == "45 g"
        assert shown["Salz"] == "1,2 g"
        assert shown["Brennwert"] == "951 kJ / 227 kcal"

    @pytest.mark.gui
    def test_the_calculator_names_the_label_value(self, qapp: object) -> None:
        del qapp
        from brotrechner.gui.theme import ThemeMode, resolve_tokens
        from brotrechner.gui.widgets.nutrition_panel import NutritionPanel

        panel = NutritionPanel(resolve_tokens(ThemeMode.LIGHT))
        panel.update_values(BREAD)
        assert panel._value_labels["carbs"].text() == "45,3 g", "Rechner bleibt genau"
        assert "45 g" in panel._value_labels["carbs"].toolTip()
        panel.clear()
        assert panel._value_labels["carbs"].toolTip() == ""
