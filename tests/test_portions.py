"""Portionen: Nährwerte und Kosten je Scheibe, Brötchen oder Stück.

Bisher kannte das Programm nur Angaben je 100 g. Wer wissen wollte, was eine
Scheibe hat oder kostet, musste selbst rechnen - und auf dem Etikett ließ sich
die Angabe je Portion nach Artikel 33 VO (EU) Nr. 1169/2011 nicht machen.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from brotrechner.core.analysis import ResolvedItem, analyze
from brotrechner.core.models import Ingredient, Recipe, RecipeItem
from brotrechner.core.nutrients import NUTRIENT_FIELDS, Nutrients
from brotrechner.core.plausibility import check_process
from brotrechner.core.portions import SUGGESTED_NAMES, Portion
from brotrechner.core.validation import Severity

FLOUR = Ingredient(
    name="Weizenmehl 550",
    nutrients=Nutrients(
        energy_kcal=350, fat=1.2, saturated_fat=0.2, carbs=71, sugar=0.7, protein=10, salt=0.01
    ),
    flour_percent=100.0,
    package_price=1.0,
    package_size_g=1000.0,
)
WATER = Ingredient(name="Wasser", nutrients=Nutrients(water=100.0))


def _analysis(*, baked: float = 800.0, portion: Portion | None = None):  # type: ignore[no-untyped-def]
    return analyze(
        [ResolvedItem(FLOUR, 600.0), ResolvedItem(WATER, 400.0)],
        baked_weight_g=baked,
        portion=portion,
    )


class TestPortion:
    def test_name_and_weight(self) -> None:
        portion = Portion("Scheibe", 50.0)
        assert portion.name == "Scheibe"
        assert portion.weight_g == 50.0
        assert portion.title == "Scheibe (50 g)"

    def test_fractions_of_a_gram_are_shown(self) -> None:
        assert Portion("Scheibe", 45.5).title == "Scheibe (45,5 g)"

    def test_whitespace_is_tidied(self) -> None:
        assert Portion("  Scheibe \n Toast ", 30.0).name == "Scheibe Toast"

    def test_without_a_name_it_is_a_portion(self) -> None:
        assert Portion("   ", 30.0).name == "Portion"

    @pytest.mark.parametrize("weight", [0.0, -1.0, math.nan, math.inf])
    def test_a_weight_must_be_positive_and_finite(self, weight: float) -> None:
        with pytest.raises(ValueError, match="Portion"):
            Portion("Scheibe", weight)

    def test_the_suggestions_are_valid_names(self) -> None:
        assert "Scheibe" in SUGGESTED_NAMES
        assert all(Portion(name, 10.0).name == name for name in SUGGESTED_NAMES)


class TestCount:
    def test_an_exact_count(self) -> None:
        assert Portion("Scheibe", 50.0).count_text(1000.0) == "20 Scheiben"

    def test_an_approximate_count(self) -> None:
        assert Portion("Scheibe", 50.0).count_text(996.0) == "ca. 20 Scheiben"

    def test_one_portion_is_singular(self) -> None:
        assert Portion("Scheibe", 60.0).count_text(60.0) == "1 Scheibe"

    def test_plural_equal_to_singular(self) -> None:
        assert Portion("Brötchen", 75.0).count_text(900.0) == "12 Brötchen"

    def test_known_names_ignore_case(self) -> None:
        assert Portion("scheibe", 50.0).count_text(1000.0) == "20 Scheiben"

    def test_an_unknown_name_is_counted_without_a_plural(self) -> None:
        """Den Plural von „Stulle“ kennt das Programm nicht - und rät ihn nicht."""
        assert Portion("Stulle", 50.0).count_text(1000.0) == "20 × Stulle"

    def test_half_a_portion_rounds_up(self) -> None:
        assert Portion("Stück", 100.0).count_text(250.0) == "ca. 3 Stück"

    def test_the_count_as_a_number(self) -> None:
        assert Portion("Scheibe", 50.0).count(996.0) == pytest.approx(19.92)

    @pytest.mark.parametrize("grams", [math.inf, math.nan])
    def test_a_count_needs_a_real_weight(self, grams: float) -> None:
        with pytest.raises(ValueError, match="endlich"):
            Portion("Scheibe", 50.0).count_text(grams)

    def test_a_portion_heavier_than_the_bread_has_no_count(self) -> None:
        portion = Portion("Scheibe", 50.0)
        assert not portion.fits_into(40.0)
        assert portion.fits_into(50.0)
        with pytest.raises(ValueError, match="schwerer"):
            portion.count_text(40.0)

    @given(
        weight=st.floats(min_value=1.0, max_value=5000.0),
        count=st.floats(min_value=1.0, max_value=500.0),
    )
    def test_the_count_is_never_off_by_more_than_half(self, weight: float, count: float) -> None:
        portion = Portion("Scheibe", weight)
        text = portion.count_text(weight * count)
        number = int(text.removeprefix("ca. ").split(" ")[0])
        assert abs(number - count) <= 0.5 + 1e-9
        # „ca.“ genau dann, wenn die Zahl nicht fast aufgeht.
        exact = portion.count(weight * count)
        assert text.startswith("ca. ") == (abs(number - exact) > 0.05)


class TestNutrientsAndCost:
    @given(
        weight=st.floats(min_value=1.0, max_value=2000.0),
        values=st.lists(
            st.floats(min_value=0.0, max_value=900.0),
            min_size=len(NUTRIENT_FIELDS),
            max_size=len(NUTRIENT_FIELDS),
        ),
    )
    def test_nutrients_scale_with_the_weight(self, weight: float, values: list[float]) -> None:
        per_100g = Nutrients(**dict(zip(NUTRIENT_FIELDS, values, strict=True)))
        per_portion = Portion("Stück", weight).nutrients(per_100g)
        for name in NUTRIENT_FIELDS:
            assert getattr(per_portion, name) == pytest.approx(
                getattr(per_100g, name) * weight / 100.0
            )

    def test_cost(self) -> None:
        assert Portion("Scheibe", 50.0).cost(0.40) == pytest.approx(0.20)


class TestSerialisation:
    def test_round_trip(self) -> None:
        portion = Portion("Brötchen", 72.5)
        assert Portion.from_dict(portion.to_dict()) == portion

    @given(
        name=st.text(max_size=30),
        weight=st.floats(min_value=0.1, max_value=100_000.0),
    )
    def test_any_valid_portion_survives_saving(self, name: str, weight: float) -> None:
        portion = Portion(name, weight)
        assert Portion.from_dict(portion.to_dict()) == portion

    @pytest.mark.parametrize(
        "data",
        [
            None,
            "Scheibe",
            [],
            {},
            {"name": "Scheibe"},
            {"name": "Scheibe", "weight_g": "viel"},
            {"name": "Scheibe", "weight_g": -5},
            {"name": "Scheibe", "weight_g": 0},
            {"name": "Scheibe", "weight_g": "nan"},
            {"name": "Scheibe", "weight_g": True},
        ],
    )
    def test_anything_broken_means_no_portion(self, data: object) -> None:
        """Eine kaputte Portion darf nicht das ganze Rezept kosten."""
        assert Portion.from_dict(data) is None

    def test_a_number_as_text_is_read(self) -> None:
        assert Portion.from_dict({"name": "Scheibe", "weight_g": "50"}) == Portion("Scheibe", 50)

    def test_a_non_text_name_is_read_as_text(self) -> None:
        assert Portion.from_dict({"name": 7, "weight_g": 50}) == Portion("7", 50.0)


class TestRecipe:
    def _recipe(self, portion: Portion | None) -> Recipe:
        return Recipe(
            name="Kasten",
            items=[RecipeItem(FLOUR.key, FLOUR.name, FLOUR.manufacturer, 500.0)],
            baked_weight_g=750.0,
            portion=portion,
        )

    def test_without_a_portion_by_default(self) -> None:
        assert Recipe(name="Leer").portion is None

    def test_it_is_saved_and_read(self) -> None:
        recipe = self._recipe(Portion("Scheibe", 40.0))
        data = recipe.to_dict()
        assert data["portion"] == {"name": "Scheibe", "weight_g": 40.0}
        assert Recipe.from_dict(data).portion == Portion("Scheibe", 40.0)

    def test_no_portion_is_saved_as_null(self) -> None:
        assert self._recipe(None).to_dict()["portion"] is None

    def test_older_files_have_no_portion(self) -> None:
        data = self._recipe(None).to_dict()
        del data["portion"]
        assert Recipe.from_dict(data).portion is None

    def test_a_broken_portion_keeps_the_recipe(self) -> None:
        data = self._recipe(None).to_dict()
        data["portion"] = {"name": "Scheibe", "weight_g": "dick"}
        recipe = Recipe.from_dict(data)
        assert recipe.name == "Kasten"
        assert recipe.portion is None

    def test_scaling_keeps_the_size_of_a_slice(self) -> None:
        """Ein doppeltes Rezept ergibt mehr Scheiben, nicht dickere."""
        doubled = self._recipe(Portion("Scheibe", 40.0)).scaled(2.0)
        assert doubled.portion == Portion("Scheibe", 40.0)


class TestAnalysis:
    def test_without_a_portion_there_is_nothing_per_portion(self) -> None:
        analysis = _analysis()
        assert analysis.portion is None
        assert analysis.per_portion is None
        assert analysis.cost_per_portion is None
        assert analysis.portion_count is None

    def test_per_portion(self) -> None:
        analysis = _analysis(portion=Portion("Scheibe", 50.0))
        assert analysis.portion == Portion("Scheibe", 50.0)
        assert analysis.per_portion is not None
        assert analysis.per_portion.energy_kcal == pytest.approx(analysis.per_100g.energy_kcal / 2)
        assert analysis.cost_per_portion == pytest.approx(analysis.cost_per_100g / 2)
        assert analysis.portion_count == pytest.approx(16.0)

    def test_without_a_baked_weight_there_is_nothing_per_portion(self) -> None:
        analysis = _analysis(baked=0.0, portion=Portion("Scheibe", 50.0))
        assert analysis.per_portion is None
        assert analysis.cost_per_portion is None
        assert analysis.portion_count is None

    def test_an_empty_recipe_keeps_its_portion(self) -> None:
        empty = analyze([], baked_weight_g=0.0, portion=Portion("Scheibe", 50.0))
        assert empty.portion == Portion("Scheibe", 50.0)
        assert empty.per_portion is None


class TestPlausibility:
    def test_a_portion_heavier_than_the_bread_is_suspicious(self) -> None:
        findings = check_process(_analysis(portion=Portion("Scheibe", 900.0)))
        (finding,) = [f for f in findings if f.code == "portion_too_heavy"]
        assert finding.severity is Severity.WARNING
        assert "Scheibe" in finding.message

    def test_a_portion_as_heavy_as_the_bread_is_fine(self) -> None:
        """Ein Brötchen-Rezept für genau ein Brötchen."""
        findings = check_process(_analysis(portion=Portion("Brötchen", 800.0)))
        assert [f for f in findings if f.code == "portion_too_heavy"] == []

    def test_without_a_baked_weight_nothing_is_said(self) -> None:
        findings = check_process(_analysis(baked=0.0, portion=Portion("Scheibe", 900.0)))
        assert [f for f in findings if f.code == "portion_too_heavy"] == []
