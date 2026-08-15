"""Tests der Plausibilitätsprüfung.

Jeder Prüfcode bekommt mindestens einen Testfall, der ihn auslöst, und einen,
der ihn *nicht* auslöst - sonst ließe sich nicht erkennen, ob eine Prüfung
schlicht immer anschlägt.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from brotrechner.core.models import Category, Ingredient
from brotrechner.core.nutrients import Nutrients
from brotrechner.core.validation import (
    KNOWN_MANUFACTURERS,
    PLAUSIBLE_WATER_RANGES,
    Severity,
    energy_deviation,
    validate_database,
    validate_ingredient,
)


def codes(ingredient: Ingredient) -> set[str]:
    """Alle Befundcodes einer Zutat."""
    return {finding.code for finding in validate_ingredient(ingredient)}


def clean_flour(**overrides: object) -> Ingredient:
    """Ein einwandfreies Mehl, das gezielt verbogen werden kann."""
    nutrients = Nutrients(
        energy_kcal=317,
        fat=1.7,
        saturated_fat=0.3,
        carbs=60.0,
        sugar=1.0,
        protein=8.5,
        salt=0.01,
        fiber=14.0,
        water=13.0,
    )
    defaults: dict[str, object] = {
        "name": "Roggenvollkornmehl",
        "category": Category.FLOUR,
        "nutrients": nutrients,
        "is_flour": True,
        "package_price": 1.98,
        "package_size_g": 1000,
    }
    defaults.update(overrides)
    return Ingredient(**defaults)  # type: ignore[arg-type]


class TestCleanIngredient:
    def test_a_correct_ingredient_has_no_findings(self) -> None:
        assert validate_ingredient(clean_flour()) == []


class TestMassBalance:
    def test_over_one_hundred_grams_is_an_error(self) -> None:
        """Der häufigste Fehler der Altdatenbank."""
        broken = clean_flour(
            nutrients=Nutrients(
                energy_kcal=317,
                fat=2.0,
                carbs=62.0,
                protein=13.0,
                fiber=13.4,
                salt=0.01,
                water=14.0,
            )
        )
        findings = [f for f in validate_ingredient(broken) if f.code == "mass_balance"]
        assert findings and findings[0].severity is Severity.ERROR
        assert "104" in findings[0].message

    def test_suggestion_reduces_the_water(self) -> None:
        broken = clean_flour(
            nutrients=Nutrients(fat=2.0, carbs=62.0, protein=13.0, fiber=13.4, water=14.0)
        )
        finding = next(f for f in validate_ingredient(broken) if f.code == "mass_balance")
        assert finding.suggestion is not None
        assert finding.suggestion < 14.0

    def test_exactly_one_hundred_is_accepted(self) -> None:
        sugar = Ingredient(
            name="Zucker",
            category=Category.BASICS,
            nutrients=Nutrients(energy_kcal=400, carbs=100.0, sugar=100.0),
            package_price=0.89,
            package_size_g=1000,
        )
        assert "mass_balance" not in codes(sugar)


class TestSubValues:
    def test_saturates_above_total_fat(self) -> None:
        broken = clean_flour(nutrients=Nutrients(fat=2.0, saturated_fat=5.0, water=13.0))
        assert "sat_gt_fat" in codes(broken)

    def test_equal_values_are_fine(self) -> None:
        item = Ingredient(
            name="Kokosfett",
            category=Category.FATS_OILS,
            nutrients=Nutrients(energy_kcal=900, fat=100.0, saturated_fat=100.0),
            package_price=3.99,
            package_size_g=450,
        )
        assert "sat_gt_fat" not in codes(item)

    def test_sugar_above_carbs(self) -> None:
        broken = clean_flour(nutrients=Nutrients(carbs=5.0, sugar=20.0, water=13.0))
        assert "sugar_gt_carbs" in codes(broken)


class TestEnergy:
    def test_mismatch_is_a_warning(self) -> None:
        """Flohsamenschalen mit 21 kcal - der Ballaststoffanteil fehlt."""
        item = Ingredient(
            name="Flohsamenschalen",
            category=Category.SEEDS_NUTS,
            nutrients=Nutrients(
                energy_kcal=21, fat=0.5, carbs=1.7, protein=2.4, fiber=83.7, water=8.0
            ),
            package_price=4.95,
            package_size_g=500,
        )
        finding = next(f for f in validate_ingredient(item) if f.code == "energy")
        assert finding.severity is Severity.WARNING
        assert finding.suggestion == pytest.approx(188, abs=1)

    def test_small_deviation_is_tolerated(self) -> None:
        """Etikettwerte weichen durch Rundung immer etwas ab."""
        item = clean_flour(
            nutrients=Nutrients(
                energy_kcal=328, fat=1.7, carbs=60.0, protein=8.5, fiber=14.0, water=13.0
            )
        )
        assert "energy" not in codes(item)

    def test_deviation_helper(self) -> None:
        assert energy_deviation(Nutrients(energy_kcal=100, carbs=10)) == pytest.approx(60.0)


class TestWaterRange:
    def test_flour_with_too_much_water(self) -> None:
        assert "water" in codes(clean_flour(nutrients=Nutrients(water=45.0)))

    def test_starch_at_eighteen_percent_is_accepted(self) -> None:
        """Kartoffelstärke hält handelsüblich 18-20 % Wasser."""
        starch = Ingredient(
            name="Kartoffelstärke",
            category=Category.FLOUR,
            nutrients=Nutrients(energy_kcal=325, carbs=81.0, protein=0.1, water=18.0),
            package_price=0.79,
            package_size_g=400,
        )
        assert "water" not in codes(starch)

    def test_over_one_hundred_percent_is_an_error(self) -> None:
        item = clean_flour(nutrients=Nutrients(water=150.0))
        findings = [f for f in validate_ingredient(item) if f.code == "water"]
        assert any(f.severity is Severity.ERROR for f in findings)

    def test_every_category_has_a_range(self) -> None:
        assert set(PLAUSIBLE_WATER_RANGES) == set(Category)


class TestNegativeAndExtremes:
    def test_negative_value(self) -> None:
        assert "negative" in codes(clean_flour(nutrients=Nutrients(fat=-1.0)))

    def test_salt_above_one_hundred(self) -> None:
        item = Ingredient(name="Merkwürdig", nutrients=Nutrients(salt=150.0))
        assert "salt_range" in codes(item)

    def test_pure_salt_is_accepted(self) -> None:
        item = Ingredient(
            name="Salz",
            category=Category.BASICS,
            nutrients=Nutrients(salt=100.0),
            package_price=0.19,
            package_size_g=500,
        )
        assert validate_ingredient(item) == []


class TestPrice:
    def test_missing_price_is_only_a_hint(self) -> None:
        item = clean_flour(package_price=0.0, package_size_g=0.0)
        finding = next(f for f in validate_ingredient(item) if f.code == "price_missing")
        assert finding.severity is Severity.INFO

    def test_price_without_size_is_an_error(self) -> None:
        item = clean_flour(package_price=1.98, package_size_g=0.0)
        finding = next(f for f in validate_ingredient(item) if f.code == "price_inconsistent")
        assert finding.severity is Severity.ERROR


class TestManufacturerInName:
    @pytest.mark.parametrize("manufacturer", ["Bauck", "dm Bio", "Alnatura", "Rewe"])
    def test_known_manufacturer_in_the_name_is_flagged(self, manufacturer: str) -> None:
        item = clean_flour(name=f"Roggenvollkornmehl ({manufacturer})")
        assert "name_manufacturer" in codes(item)

    @pytest.mark.parametrize("suffix", ["(blau)", "(frisch)", "(ganz)", "(teilentölt)"])
    def test_factual_additions_are_left_alone(self, suffix: str) -> None:
        item = clean_flour(name=f"Mohn {suffix}")
        assert "name_manufacturer" not in codes(item)

    def test_the_list_is_sorted_and_unique(self) -> None:
        assert len(set(KNOWN_MANUFACTURERS)) == len(KNOWN_MANUFACTURERS)


class TestDatabase:
    def test_duplicates_are_detected(self) -> None:
        a = Ingredient(name="Kürbiskernöl", manufacturer="dm Bio")
        b = Ingredient(name="KürbiskernÖl", manufacturer="dm Bio")
        findings = [f for f in validate_database([a, b]) if f.code == "duplicate"]
        assert len(findings) == 1
        assert findings[0].severity is Severity.ERROR

    def test_distinct_manufacturers_are_no_duplicates(self) -> None:
        a = Ingredient(name="Mehl", manufacturer="Bauck")
        b = Ingredient(name="Mehl", manufacturer="Alnatura")
        assert not [f for f in validate_database([a, b]) if f.code == "duplicate"]

    def test_findings_are_sorted_by_severity(self) -> None:
        items = [
            clean_flour(name="Ohne Preis", package_price=0.0, package_size_g=0.0),
            clean_flour(name="Kaputt", nutrients=Nutrients(fat=2.0, saturated_fat=9.0)),
        ]
        findings = validate_database(items)
        ranks = [f.severity.rank for f in findings]
        assert ranks == sorted(ranks, reverse=True)

    def test_empty_database_has_no_findings(self) -> None:
        assert validate_database([]) == []

    def test_finding_str_includes_the_suggestion(self) -> None:
        item = clean_flour(nutrients=Nutrients(fat=2.0, saturated_fat=9.0, water=13.0))
        finding = next(f for f in validate_ingredient(item) if f.code == "sat_gt_fat")
        assert "Vorschlag" in str(finding)


class TestProperties:
    @given(
        st.builds(
            Nutrients,
            energy_kcal=st.floats(0, 900, allow_nan=False),
            fat=st.floats(0, 100, allow_nan=False),
            saturated_fat=st.floats(0, 100, allow_nan=False),
            carbs=st.floats(0, 100, allow_nan=False),
            sugar=st.floats(0, 100, allow_nan=False),
            protein=st.floats(0, 100, allow_nan=False),
            salt=st.floats(0, 100, allow_nan=False),
            fiber=st.floats(0, 100, allow_nan=False),
            water=st.floats(0, 100, allow_nan=False),
        )
    )
    def test_validation_never_raises(self, nutrients: Nutrients) -> None:
        """Auch völlig widersinnige Werte dürfen die Prüfung nicht abstürzen lassen."""
        findings = validate_ingredient(Ingredient(name="Zufall", nutrients=nutrients))
        assert all(f.display_name == "Zufall" for f in findings)

    @given(st.floats(min_value=0.0, max_value=200.0, allow_nan=False))
    def test_water_above_one_hundred_is_always_an_error(self, water: float) -> None:
        item = Ingredient(name="X", nutrients=Nutrients(water=water))
        has_error = any(
            f.code == "water" and f.severity is Severity.ERROR for f in validate_ingredient(item)
        )
        assert has_error == (water > 100.0)
