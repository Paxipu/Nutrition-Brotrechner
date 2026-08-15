"""Tests des Nährwertvektors und der Energieberechnung."""

from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from brotrechner.core.nutrients import (
    ENERGY_FACTORS_KCAL_PER_G,
    KCAL_TO_KJ,
    NUTRIENT_FIELDS,
    Nutrients,
    energy_from_macros,
    energy_kj,
)

# Endliche, realistische Nährwerte je 100 g.
_values = st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)


@st.composite
def nutrients(draw: st.DrawFn) -> Nutrients:
    """Erzeugt zufällige, aber plausible Nährwertvektoren."""
    return Nutrients(**{field: draw(_values) for field in NUTRIENT_FIELDS})


class TestConstruction:
    def test_defaults_are_zero(self) -> None:
        assert Nutrients().to_dict() == dict.fromkeys(NUTRIENT_FIELDS, 0.0)

    def test_is_immutable(self) -> None:
        with pytest.raises(AttributeError):
            Nutrients().fat = 5.0  # type: ignore[misc]

    def test_from_dict_ignores_unknown_keys(self) -> None:
        result = Nutrients.from_dict({"fat": 3.0, "voellig_unbekannt": 99})
        assert result.fat == 3.0
        assert result.protein == 0.0

    def test_from_dict_treats_none_as_zero(self) -> None:
        assert Nutrients.from_dict({"fat": None}).fat == 0.0

    def test_from_dict_accepts_numeric_strings(self) -> None:
        assert Nutrients.from_dict({"fat": "3.5"}).fat == 3.5

    @pytest.mark.parametrize("bad", ["viel", [1], {"a": 1}])
    def test_from_dict_rejects_non_numeric(self, bad: object) -> None:
        with pytest.raises(ValueError, match="nicht numerisch"):
            Nutrients.from_dict({"fat": bad})


class TestArithmetic:
    def test_scaled_multiplies_every_field(self) -> None:
        base = Nutrients(energy_kcal=100, fat=10, water=50)
        scaled = base.scaled(2.5)
        assert scaled.energy_kcal == 250
        assert scaled.fat == 25
        assert scaled.water == 125

    def test_scaled_by_zero_yields_zero(self) -> None:
        assert Nutrients(fat=10).scaled(0.0) == Nutrients()

    @pytest.mark.parametrize("factor", [float("nan"), float("inf"), float("-inf")])
    def test_scaled_rejects_non_finite(self, factor: float) -> None:
        with pytest.raises(ValueError, match="endlich"):
            Nutrients().scaled(factor)

    def test_addition_is_field_wise(self) -> None:
        total = Nutrients(fat=1, protein=2) + Nutrients(fat=3, carbs=4)
        assert (total.fat, total.protein, total.carbs) == (4, 2, 4)

    def test_addition_with_foreign_type_is_not_implemented(self) -> None:
        with pytest.raises(TypeError):
            _ = Nutrients() + 5  # type: ignore[operator]

    def test_with_values_replaces_single_field(self) -> None:
        assert Nutrients(fat=1).with_values(fat=9).fat == 9

    def test_with_values_rejects_unknown_field(self) -> None:
        with pytest.raises(ValueError, match="Unbekannte"):
            Nutrients().with_values(kalorien=1)


class TestEnergy:
    def test_uses_annex_xiv_factors(self) -> None:
        # 10 g KH + 10 g Eiweiß + 10 g Fett + 10 g Ballaststoffe
        value = energy_from_macros(Nutrients(carbs=10, protein=10, fat=10, fiber=10))
        assert value == pytest.approx(40 + 40 + 90 + 20)

    def test_fiber_counts_with_two_kcal(self) -> None:
        """Der Punkt, an dem viele Etiketten zu niedrig liegen."""
        assert energy_from_macros(Nutrients(fiber=83.7)) == pytest.approx(167.4)

    def test_water_and_salt_carry_no_energy(self) -> None:
        assert energy_from_macros(Nutrients(water=100, salt=100)) == 0.0

    def test_kj_conversion(self) -> None:
        assert energy_kj(100) == pytest.approx(418.4)
        assert Nutrients(energy_kcal=209).energy_kj == round(209 * KCAL_TO_KJ)

    def test_factors_cover_exactly_the_energy_carriers(self) -> None:
        assert set(ENERGY_FACTORS_KCAL_PER_G) == {"carbs", "protein", "fat", "fiber"}


class TestMassBalance:
    def test_sums_the_balanced_components(self) -> None:
        value = Nutrients(fat=1, carbs=2, protein=3, salt=4, fiber=5, water=6).mass_sum
        assert value == pytest.approx(21)

    def test_energy_is_not_part_of_the_mass(self) -> None:
        assert Nutrients(energy_kcal=500).mass_sum == 0.0


class TestProperties:
    @given(nutrients(), st.floats(min_value=0.01, max_value=1000, allow_nan=False))
    def test_scaling_is_linear(self, base: Nutrients, factor: float) -> None:
        """Zweimal skalieren entspricht einmal mit dem Produkt der Faktoren."""
        once = base.scaled(factor).scaled(factor)
        twice = base.scaled(factor * factor)
        for field in NUTRIENT_FIELDS:
            assert getattr(once, field) == pytest.approx(getattr(twice, field), rel=1e-9)

    @given(nutrients())
    def test_dict_roundtrip_is_lossless(self, base: Nutrients) -> None:
        assert Nutrients.from_dict(base.to_dict()) == base

    @given(nutrients(), nutrients())
    def test_addition_is_commutative(self, a: Nutrients, b: Nutrients) -> None:
        for field in NUTRIENT_FIELDS:
            assert getattr(a + b, field) == pytest.approx(getattr(b + a, field))

    @given(nutrients())
    def test_energy_is_never_negative_for_valid_input(self, base: Nutrients) -> None:
        assert energy_from_macros(base) >= 0.0

    @given(nutrients())
    def test_energy_is_finite(self, base: Nutrients) -> None:
        assert math.isfinite(energy_from_macros(base))

    @given(nutrients(), st.floats(min_value=0.0, max_value=100, allow_nan=False))
    def test_energy_scales_with_the_vector(self, base: Nutrients, factor: float) -> None:
        assert energy_from_macros(base.scaled(factor)) == pytest.approx(
            energy_from_macros(base) * factor, rel=1e-9, abs=1e-9
        )
