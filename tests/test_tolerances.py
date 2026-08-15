"""Tests der EU-Deklarationstoleranzen.

Die Zahlenwerte stammen aus Tabelle 1 der Guidance der Europäischen
Kommission vom Dezember 2012 und sind hier bewusst hart hinterlegt: Wenn
jemand die Tabelle in :mod:`brotrechner.core.tolerances` verändert, muss er
sich auch mit diesen Tests auseinandersetzen.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from brotrechner.core.nutrients import Nutrients
from brotrechner.core.tolerances import TOLERANCE_FIELDS, ValueRange, nutrient_ranges, tolerance_for


class TestTable1:
    @pytest.mark.parametrize("field", ["carbs", "sugar", "protein", "fiber"])
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (0.5, 2.0),  # < 10 g -> +/- 2 g
            (9.99, 2.0),
            (10.0, 2.0),  # 10-40 g -> +/- 20 %
            (25.0, 5.0),
            (40.0, 8.0),
            (40.01, 8.0),  # > 40 g -> +/- 8 g
            (95.0, 8.0),
        ],
    )
    def test_carbohydrate_group(self, field: str, value: float, expected: float) -> None:
        assert tolerance_for(field, value) == pytest.approx(expected)

    @pytest.mark.parametrize(
        ("value", "expected"),
        [(0.5, 1.5), (9.99, 1.5), (10.0, 2.0), (30.0, 6.0), (40.0, 8.0), (100.0, 8.0)],
    )
    def test_fat_has_its_own_lower_band(self, value: float, expected: float) -> None:
        """Fett hat unter 10 g +/- 1,5 g statt der +/- 2 g der Kohlenhydrate."""
        assert tolerance_for("fat", value) == pytest.approx(expected)

    @pytest.mark.parametrize(
        ("value", "expected"), [(0.1, 0.8), (3.99, 0.8), (4.0, 0.8), (10.0, 2.0), (52.0, 10.4)]
    )
    def test_saturates(self, value: float, expected: float) -> None:
        assert tolerance_for("saturated_fat", value) == pytest.approx(expected)

    @pytest.mark.parametrize(
        ("value", "expected"), [(0.01, 0.375), (1.24, 0.375), (1.25, 0.25), (100.0, 20.0)]
    )
    def test_salt(self, value: float, expected: float) -> None:
        assert tolerance_for("salt", value) == pytest.approx(expected)

    def test_declared_zero_gets_no_band(self) -> None:
        """ "Enthält 0 g Fett" darf in der Auswertung nicht zu "0-1,5 g" werden."""
        assert tolerance_for("fat", 0.0) == 0.0

    def test_energy_has_no_own_tolerance(self) -> None:
        """Die Guidance definiert für den Brennwert keine Toleranz."""
        assert tolerance_for("energy_kcal", 200.0) == 0.0

    def test_water_has_no_tolerance(self) -> None:
        assert tolerance_for("water", 50.0) == 0.0

    def test_negative_value_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="nicht negativ"):
            tolerance_for("fat", -1.0)


class TestRanges:
    def test_lower_bound_is_clamped_at_zero(self) -> None:
        band = nutrient_ranges(Nutrients(fat=1.0))["fat"]
        assert band.minimum == 0.0
        assert band.maximum == pytest.approx(2.5)

    def test_energy_is_derived_from_the_nutrients(self) -> None:
        """Der Brennwertkorridor wird gerechnet, nicht geschätzt."""
        base = Nutrients(energy_kcal=400, carbs=50, protein=20, fat=10, fiber=5)
        bands = nutrient_ranges(base)
        # untere Grenze: 42 KH, 16 Eiweiß, 8 Fett, 3 Ballaststoffe
        expected_min = 42 * 4 + 16 * 4 + 8 * 9 + 3 * 2
        assert bands["energy_kcal"].minimum == pytest.approx(expected_min)

    def test_declared_energy_stays_inside_its_own_band(self) -> None:
        """Ein unstimmiger Etikettwert weitet das Intervall, statt herauszufallen."""
        base = Nutrients(energy_kcal=21, fiber=83.7, carbs=1.7, protein=2.4, fat=0.5)
        band = nutrient_ranges(base)["energy_kcal"]
        assert band.minimum <= band.value <= band.maximum

    def test_all_tolerance_fields_are_present(self) -> None:
        bands = nutrient_ranges(Nutrients(fat=5, carbs=20))
        assert set(bands) == set(TOLERANCE_FIELDS) | {"energy_kcal"}

    def test_half_width_and_relative_width(self) -> None:
        band = ValueRange(10.0, 8.0, 12.0)
        assert band.half_width == pytest.approx(2.0)
        assert band.relative_width == pytest.approx(40.0)

    def test_relative_width_of_zero_value_is_zero(self) -> None:
        assert ValueRange(0.0, 0.0, 0.0).relative_width == 0.0


class TestProperties:
    @given(
        st.sampled_from(TOLERANCE_FIELDS),
        st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
    )
    def test_tolerance_is_never_negative(self, field: str, value: float) -> None:
        assert tolerance_for(field, value) >= 0.0

    @given(
        st.fixed_dictionaries(
            {
                f: st.floats(min_value=0.0, max_value=100.0, allow_nan=False)
                for f in TOLERANCE_FIELDS
            }
        )
    )
    def test_bands_always_contain_the_declared_value(self, values: dict[str, float]) -> None:
        base = Nutrients(**values)
        for field, band in nutrient_ranges(base).items():
            assert band.minimum <= band.value + 1e-9, field
            assert band.value <= band.maximum + 1e-9, field

    @given(st.floats(min_value=0.01, max_value=100.0, allow_nan=False))
    def test_tolerance_never_exceeds_the_value_plus_two_grams(self, value: float) -> None:
        """Sonst reichte die Bandbreite unsinnig weit ins Negative."""
        assert tolerance_for("carbs", value) <= max(value, 2.0) + 1e-9
