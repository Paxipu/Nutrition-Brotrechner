"""Tests der Rezeptauswertung: Bäckerprozent, Teigausbeute, Nährwerte, Kosten."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from brotrechner.core.analysis import (
    RecipeAnalysis,
    ResolvedItem,
    aggregate_nutrients,
    analyze,
    resolve_items,
)
from brotrechner.core.models import Category, Ingredient, RecipeItem
from brotrechner.core.nutrients import Nutrients


@pytest.fixture
def basic(flour: Ingredient, water: Ingredient, salt: Ingredient) -> list[ResolvedItem]:
    """1000 g Mehl, 700 g Wasser, 20 g Salz."""
    return [
        ResolvedItem(flour, 1000.0),
        ResolvedItem(water, 700.0),
        ResolvedItem(salt, 20.0),
    ]


class TestEmpty:
    def test_no_items_gives_an_empty_result(self) -> None:
        result = analyze([], baked_weight_g=1000)
        assert result.is_empty
        assert result.lines == ()
        assert result.dough_yield == 0.0
        assert result.per_100g == Nutrients()

    def test_empty_result_keeps_the_process_data(self) -> None:
        result = analyze([], baked_weight_g=800, energy_kwh=1.2, energy_price=0.4)
        assert result.baked_weight_g == 800
        assert result.energy_kwh == 1.2


class TestBakerPercent:
    def test_flour_is_one_hundred_percent(self, basic: list[ResolvedItem]) -> None:
        result = analyze(basic, baked_weight_g=1500)
        assert result.flour_mass_g == pytest.approx(1000.0)
        assert result.lines[0].baker_percent == pytest.approx(100.0)

    def test_water_relates_to_the_flour(self, basic: list[ResolvedItem]) -> None:
        result = analyze(basic, baked_weight_g=1500)
        assert result.lines[1].baker_percent == pytest.approx(70.0)

    def test_salt_percentage(self, basic: list[ResolvedItem]) -> None:
        result = analyze(basic, baked_weight_g=1500)
        assert result.lines[2].baker_percent == pytest.approx(2.0)

    def test_without_flour_the_percentage_is_zero(self, water: Ingredient) -> None:
        result = analyze([ResolvedItem(water, 500.0)], baked_weight_g=500)
        assert result.flour_mass_g == 0.0
        assert result.lines[0].baker_percent == 0.0

    def test_two_flours_are_added_up(self, flour: Ingredient, water: Ingredient) -> None:
        second = flour.copy(manufacturer="Alnatura")
        result = analyze(
            [ResolvedItem(flour, 600.0), ResolvedItem(second, 400.0), ResolvedItem(water, 700.0)],
            baked_weight_g=1500,
        )
        assert result.flour_mass_g == pytest.approx(1000.0)
        assert result.lines[0].baker_percent == pytest.approx(60.0)


class TestDoughYield:
    def test_classic_case_flour_and_water(self, basic: list[ResolvedItem]) -> None:
        """TA = (1000 + 700) / 1000 x 100 = 170."""
        result = analyze(basic, baked_weight_g=1500)
        assert result.dough_yield == pytest.approx(170.0)
        assert result.hydration_percent == pytest.approx(70.0)

    def test_hydration_is_always_dough_yield_minus_hundred(self, basic: list[ResolvedItem]) -> None:
        result = analyze(basic, baked_weight_g=1500)
        assert result.hydration_percent == pytest.approx(result.dough_yield - 100.0)

    def test_milk_contributes_only_its_water(self, flour: Ingredient, milk: Ingredient) -> None:
        """500 g Milch zählen mit 437,5 g Wasser, nicht mit 500 g.

        Genau hier rechnete die Vorversion zu hoch.
        """
        result = analyze(
            [ResolvedItem(flour, 1000.0), ResolvedItem(milk, 500.0)], baked_weight_g=1300
        )
        assert result.water_mass_g == pytest.approx(437.5)
        assert result.dough_yield == pytest.approx(143.75)

    def test_flour_moisture_is_not_counted_as_added_water(self, flour: Ingredient) -> None:
        """Reines Mehl ergibt TA 100, obwohl es 13 % Eigenfeuchte hat."""
        result = analyze([ResolvedItem(flour, 1000.0)], baked_weight_g=1000)
        assert result.water_mass_g == 0.0
        assert result.dough_yield == pytest.approx(100.0)

    @pytest.mark.parametrize(
        ("yield_value", "expected"),
        [(140, "fester"), (160, "mittlerer"), (180, "weicher"), (230, "sehr weicher")],
    )
    def test_description_matches_the_range(self, yield_value: float, expected: str) -> None:
        assert expected in RecipeAnalysis(dough_yield=yield_value).dough_yield_description

    def test_no_description_without_flour(self) -> None:
        assert RecipeAnalysis().dough_yield_description == ""


class TestScaling:
    def test_measured_dough_weight_scales_every_amount(self, basic: list[ResolvedItem]) -> None:
        """Bleiben 172 g Teig in der Schüssel, sinken alle Anteile um 10 %."""
        result = analyze(basic, baked_weight_g=1400, dough_weight_g=1548.0)
        assert result.scale_factor == pytest.approx(0.9)
        assert result.lines[0].amount_g == pytest.approx(900.0)
        assert result.flour_mass_g == pytest.approx(900.0)

    def test_without_a_measured_weight_nothing_is_scaled(self, basic: list[ResolvedItem]) -> None:
        result = analyze(basic, baked_weight_g=1500)
        assert result.scale_factor == 1.0
        assert result.dough_weight_g == pytest.approx(1720.0)

    def test_scaling_leaves_the_baker_percentages_untouched(
        self, basic: list[ResolvedItem]
    ) -> None:
        plain = analyze(basic, baked_weight_g=1500)
        scaled = analyze(basic, baked_weight_g=1500, dough_weight_g=860.0)
        for a, b in zip(plain.lines, scaled.lines, strict=True):
            assert a.baker_percent == pytest.approx(b.baker_percent)


class TestNutrition:
    def test_per_100g_refers_to_the_baked_weight(self, flour: Ingredient) -> None:
        result = analyze([ResolvedItem(flour, 1000.0)], baked_weight_g=800.0)
        # 1000 g Mehl mit 317 kcal/100 g = 3170 kcal, verteilt auf 800 g
        assert result.per_100g.energy_kcal == pytest.approx(3170 / 8)

    def test_total_is_the_absolute_sum(self, flour: Ingredient) -> None:
        result = analyze([ResolvedItem(flour, 250.0)], baked_weight_g=200.0)
        assert result.total.energy_kcal == pytest.approx(317 * 2.5)

    def test_water_content_follows_the_baking_loss(self, basic: list[ResolvedItem]) -> None:
        """Beim Backen verdampft genau die Differenz Rohteig minus Brot."""
        result = analyze(basic, baked_weight_g=1500.0, dough_weight_g=1720.0)
        expected_water = result.total.water - (1720.0 - 1500.0)
        assert result.per_100g.water == pytest.approx(expected_water / 1500.0 * 100.0)

    def test_water_content_never_goes_negative(self, flour: Ingredient) -> None:
        result = analyze([ResolvedItem(flour, 1000.0)], baked_weight_g=100.0, dough_weight_g=1000.0)
        assert result.per_100g.water >= 0.0

    def test_without_a_baked_weight_the_per_100g_values_stay_zero(
        self, basic: list[ResolvedItem]
    ) -> None:
        result = analyze(basic, baked_weight_g=0.0)
        assert result.per_100g == Nutrients()
        assert result.ranges_per_100g == {}

    def test_tolerance_bands_are_present(self, basic: list[ResolvedItem]) -> None:
        result = analyze(basic, baked_weight_g=1500)
        band = result.ranges_per_100g["carbs"]
        assert band.minimum < band.value < band.maximum

    def test_aggregate_helper_matches_the_analysis(self, basic: list[ResolvedItem]) -> None:
        assert aggregate_nutrients(basic).energy_kcal == pytest.approx(
            analyze(basic, baked_weight_g=1000).total.energy_kcal
        )


class TestCosts:
    def test_material_costs_add_up(self, basic: list[ResolvedItem]) -> None:
        result = analyze(basic, baked_weight_g=1500)
        expected = 1.98 + 700 / 1_000_000 * 4.50 + 20 / 500 * 0.19
        assert result.material_cost == pytest.approx(expected)

    def test_energy_costs(self, basic: list[ResolvedItem]) -> None:
        result = analyze(basic, baked_weight_g=1500, energy_kwh=1.5, energy_price=0.40)
        assert result.energy_cost == pytest.approx(0.60)
        assert result.total_cost == pytest.approx(result.material_cost + 0.60)

    def test_cost_per_kilogram(self, basic: list[ResolvedItem]) -> None:
        result = analyze(basic, baked_weight_g=1000)
        assert result.cost_per_kg == pytest.approx(result.cost_per_100g * 10)

    def test_ingredient_without_price_is_reported(self, flour: Ingredient) -> None:
        free = Ingredient(name="Sauerteig", category=Category.LEAVENING)
        result = analyze(
            [ResolvedItem(flour, 500.0), ResolvedItem(free, 100.0)], baked_weight_g=500
        )
        assert not result.has_complete_prices
        assert [line.ingredient.name for line in result.lines_without_price] == ["Sauerteig"]

    def test_complete_prices_are_recognised(self, basic: list[ResolvedItem]) -> None:
        assert analyze(basic, baked_weight_g=1500).has_complete_prices


class TestInputValidation:
    def test_negative_amount_is_rejected(self, flour: Ingredient) -> None:
        with pytest.raises(ValueError, match="Negative Menge"):
            analyze([ResolvedItem(flour, -1.0)], baked_weight_g=100)

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"baked_weight_g": -1.0},
            {"baked_weight_g": 100.0, "dough_weight_g": -5.0},
            {"baked_weight_g": 100.0, "energy_kwh": -1.0},
            {"baked_weight_g": 100.0, "energy_price": -0.1},
        ],
    )
    def test_negative_process_values_are_rejected(self, kwargs: dict[str, float]) -> None:
        with pytest.raises(ValueError, match="nicht negativ"):
            analyze([], **kwargs)


class TestResolve:
    def test_known_items_are_resolved(self, flour: Ingredient) -> None:
        items = [RecipeItem(flour.key, flour.name, flour.manufacturer, 500.0)]
        resolved, missing = resolve_items(items, {flour.key: flour})
        assert not missing
        assert resolved[0].ingredient is flour
        assert resolved[0].amount_g == 500.0

    def test_unknown_items_are_reported_not_dropped(self) -> None:
        items = [RecipeItem("gibt|esnicht", "Phantom", "", 100.0)]
        resolved, missing = resolve_items(items, {})
        assert resolved == []
        assert missing[0].name == "Phantom"


class TestProperties:
    """Eigenschaftstests bauen ihre Zutaten selbst.

    Hypothesis erzeugt je Beispiel einen neuen Durchlauf, pytest-Fixtures aber
    nur einen je Testfunktion. Eigene Objekte im Test halten beides sauber
    getrennt.
    """

    @staticmethod
    def _flour() -> Ingredient:
        return Ingredient(
            name="Mehl",
            category=Category.FLOUR,
            nutrients=Nutrients(energy_kcal=317, carbs=60, protein=8.5, fiber=14, water=13),
            is_flour=True,
            package_price=2.0,
            package_size_g=1000,
        )

    @staticmethod
    def _water() -> Ingredient:
        return Ingredient(
            name="Wasser",
            category=Category.BASICS,
            nutrients=Nutrients(water=100.0),
            package_price=4.5,
            package_size_g=1_000_000,
        )

    @given(
        amounts=st.lists(
            st.floats(min_value=0.1, max_value=5000, allow_nan=False, allow_infinity=False),
            min_size=1,
            max_size=8,
        )
    )
    def test_share_percentages_sum_to_one_hundred(self, amounts: list[float]) -> None:
        items = [ResolvedItem(self._flour(), amount) for amount in amounts]
        result = analyze(items, baked_weight_g=100.0)
        assert sum(line.share_percent for line in result.lines) == pytest.approx(100.0, rel=1e-6)

    @given(factor=st.floats(min_value=0.5, max_value=4.0, allow_nan=False))
    def test_doubling_everything_keeps_the_per_100g_values(self, factor: float) -> None:
        """Ein doppelt so großer Ansatz ergibt dasselbe Brot."""
        flour, water = self._flour(), self._water()
        single = analyze(
            [ResolvedItem(flour, 1000.0), ResolvedItem(water, 700.0)], baked_weight_g=1500.0
        )
        double = analyze(
            [ResolvedItem(flour, 1000.0 * factor), ResolvedItem(water, 700.0 * factor)],
            baked_weight_g=1500.0 * factor,
        )
        assert double.per_100g.energy_kcal == pytest.approx(single.per_100g.energy_kcal, rel=1e-6)
        assert double.dough_yield == pytest.approx(single.dough_yield, rel=1e-6)

    @given(
        flour_g=st.floats(min_value=1.0, max_value=10_000, allow_nan=False),
        water_g=st.floats(min_value=1.0, max_value=10_000, allow_nan=False),
    )
    def test_costs_are_never_negative(self, flour_g: float, water_g: float) -> None:
        result = analyze(
            [ResolvedItem(self._flour(), flour_g), ResolvedItem(self._water(), water_g)],
            baked_weight_g=max(1.0, (flour_g + water_g) * 0.8),
        )
        assert result.material_cost >= 0.0
        assert result.total_cost >= 0.0
        assert result.cost_per_100g >= 0.0

    @given(
        flour_g=st.floats(min_value=1.0, max_value=10_000, allow_nan=False),
        water_g=st.floats(min_value=0.0, max_value=10_000, allow_nan=False),
    )
    def test_dough_yield_is_at_least_one_hundred(self, flour_g: float, water_g: float) -> None:
        """Wasser kann die Teigausbeute nur erhöhen, nie unter 100 drücken."""
        result = analyze(
            [ResolvedItem(self._flour(), flour_g), ResolvedItem(self._water(), water_g)],
            baked_weight_g=max(1.0, flour_g),
        )
        assert result.dough_yield >= 100.0 - 1e-9
