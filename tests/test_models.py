"""Tests des Datenmodells: Schlüssel, Preise, Serialisierung, Skalierung."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st

from brotrechner.core.models import (
    Category,
    Ingredient,
    PriceEntry,
    Recipe,
    RecipeItem,
    Source,
    normalize_key_part,
)
from brotrechner.core.nutrients import Nutrients


class TestCategory:
    def test_parses_its_own_key(self) -> None:
        assert Category.parse("flour") is Category.FLOUR

    def test_parses_the_german_label(self) -> None:
        assert Category.parse("Getreide & Flocken") is Category.GRAINS

    def test_parsing_is_case_insensitive_for_labels(self) -> None:
        assert Category.parse("mehl") is Category.FLOUR

    def test_unknown_becomes_other(self) -> None:
        assert Category.parse("Weltraumnahrung") is Category.OTHER

    @pytest.mark.parametrize("value", [None, "", 42, []])
    def test_junk_becomes_other(self, value: object) -> None:
        assert Category.parse(value) is Category.OTHER

    def test_passthrough_of_members(self) -> None:
        assert Category.parse(Category.DAIRY) is Category.DAIRY

    def test_every_member_has_a_label(self) -> None:
        assert all(category.label for category in Category)

    def test_is_not_a_str_subclass(self) -> None:
        """Sonst reicht Qt beim Umweg über QVariant nur die Zeichenkette zurück."""
        assert not issubclass(Category, str)


class TestSource:
    def test_parses_known_values(self) -> None:
        assert Source.parse("label") is Source.LABEL

    def test_unknown_becomes_unknown(self) -> None:
        assert Source.parse("hörensagen") is Source.UNKNOWN


class TestKeyNormalisation:
    def test_case_is_ignored(self) -> None:
        assert normalize_key_part("Kürbiskernöl") == normalize_key_part("KürbiskernÖl")

    def test_whitespace_is_collapsed(self) -> None:
        assert normalize_key_part("  Weizen   mehl ") == "weizen mehl"

    def test_the_real_duplicate_from_the_old_database(self) -> None:
        """ "Kürbiskernöl (dm Bio)" stand zweimal drin, nur anders geschrieben."""
        a = Ingredient(name="Kürbiskernöl", manufacturer="dm Bio")
        b = Ingredient(name="KürbiskernÖl", manufacturer="dm Bio")
        assert a.key == b.key

    def test_manufacturer_separates_otherwise_identical_items(self) -> None:
        a = Ingredient(name="Roggenvollkornmehl", manufacturer="Bauck")
        b = Ingredient(name="Roggenvollkornmehl", manufacturer="Alnatura")
        c = Ingredient(name="Roggenvollkornmehl")
        assert len({a.key, b.key, c.key}) == 3


class TestIngredient:
    def test_display_name_with_manufacturer(self, flour: Ingredient) -> None:
        assert flour.display_name == "Roggenvollkornmehl (Bauck)"

    def test_display_name_without_manufacturer(self) -> None:
        assert Ingredient(name="Wasser").display_name == "Wasser"

    def test_price_per_100g(self, flour: Ingredient) -> None:
        assert flour.price_per_100g == pytest.approx(0.198)

    def test_price_per_100g_without_size_is_zero(self) -> None:
        assert Ingredient(name="X", package_price=5.0).price_per_100g == 0.0

    def test_has_price_needs_both_values(self) -> None:
        assert not Ingredient(name="X", package_price=5.0).has_price
        assert not Ingredient(name="X", package_size_g=500).has_price
        assert Ingredient(name="X", package_price=5.0, package_size_g=500).has_price

    def test_cost_for_amount(self, flour: Ingredient) -> None:
        assert flour.cost_for(250.0) == pytest.approx(0.495)

    def test_cost_without_size_is_zero(self) -> None:
        assert Ingredient(name="X", package_price=5.0).cost_for(100) == 0.0

    def test_enum_fields_are_normalised_from_strings(self) -> None:
        """Qt liefert gelegentlich Zeichenketten - die dürfen nicht durchrutschen."""
        item = Ingredient(name="X", category="flour", water_source="label")  # type: ignore[arg-type]
        assert item.category is Category.FLOUR
        assert item.water_source is Source.LABEL

    def test_copy_is_independent(self, flour: Ingredient) -> None:
        clone = flour.copy(name="Kopie")
        clone.price_history.append(PriceEntry(datetime.now(timezone.utc), 1.0, 100.0))
        assert clone.name == "Kopie"
        assert flour.price_history == []

    def test_copy_can_change_the_manufacturer(self, flour: Ingredient) -> None:
        assert flour.copy(manufacturer="Spielberger").manufacturer == "Spielberger"


class TestPriceUpdate:
    def test_first_price_creates_no_history(self) -> None:
        item = Ingredient(name="X")
        item.update_price(1.99, 1000)
        assert item.price_history == []
        assert item.package_price == 1.99

    def test_change_archives_the_previous_price(self, flour: Ingredient) -> None:
        flour.update_price(2.49, 1000, source="Rewe")
        assert len(flour.price_history) == 1
        assert flour.price_history[0].package_price == pytest.approx(1.98)
        assert flour.price_source == "Rewe"

    def test_unchanged_price_leaves_the_history_alone(self, flour: Ingredient) -> None:
        flour.update_price(1.98, 1000)
        flour.update_price(1.98, 1000)
        assert flour.price_history == []

    def test_changed_package_size_also_counts(self, flour: Ingredient) -> None:
        flour.update_price(1.98, 500)
        assert len(flour.price_history) == 1

    def test_date_is_recorded(self, flour: Ingredient) -> None:
        flour.update_price(2.49, 1000, today=date(2026, 3, 1))
        assert flour.price_updated == date(2026, 3, 1)

    def test_history_entry_computes_its_unit_price(self) -> None:
        entry = PriceEntry(datetime.now(timezone.utc), 2.0, 500.0)
        assert entry.price_per_100g == pytest.approx(0.4)

    def test_history_entry_without_size(self) -> None:
        assert PriceEntry(datetime.now(timezone.utc), 2.0, 0.0).price_per_100g == 0.0


class TestSerialisation:
    def test_ingredient_roundtrip(self, flour: Ingredient) -> None:
        flour.price_updated = date(2026, 8, 16)
        flour.notes = "Etikett abgetippt"
        restored = Ingredient.from_dict(flour.to_dict())
        assert restored.name == flour.name
        assert restored.manufacturer == flour.manufacturer
        assert restored.category is flour.category
        assert restored.nutrients == flour.nutrients
        assert restored.is_flour == flour.is_flour
        assert restored.price_updated == flour.price_updated
        assert restored.notes == flour.notes

    def test_price_history_survives(self, flour: Ingredient) -> None:
        flour.update_price(2.49, 1000)
        restored = Ingredient.from_dict(flour.to_dict())
        assert len(restored.price_history) == 1

    def test_ingredient_without_name_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="ohne Namen"):
            Ingredient.from_dict({"name": "   "})

    def test_bad_number_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="Zahlenwert"):
            Ingredient.from_dict({"name": "X", "package_price": "teuer"})

    def test_broken_date_becomes_none(self) -> None:
        assert Ingredient.from_dict({"name": "X", "price_updated": "gestern"}).price_updated is None

    def test_recipe_roundtrip(self, simple_recipe: Recipe) -> None:
        restored = Recipe.from_dict(simple_recipe.to_dict())
        assert restored.name == simple_recipe.name
        assert len(restored.items) == 3
        assert restored.baked_weight_g == simple_recipe.baked_weight_g
        assert restored.created_at == simple_recipe.created_at

    def test_recipe_without_name_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="ohne Namen"):
            Recipe.from_dict({"name": ""})

    def test_recipe_item_derives_a_key_when_missing(self) -> None:
        item = RecipeItem.from_dict({"name": "Mehl", "manufacturer": "Bauck", "amount_g": 5})
        assert item.ingredient_key == "mehl|bauck"

    def test_broken_timestamp_falls_back_to_now(self) -> None:
        recipe = Recipe.from_dict({"name": "X", "created_at": "irgendwann"})
        assert recipe.created_at.year >= 2024


class TestRecipe:
    def test_total_amount(self, simple_recipe: Recipe) -> None:
        assert simple_recipe.total_amount_g == pytest.approx(1720.0)

    def test_scaling_multiplies_amounts_and_weights(self, simple_recipe: Recipe) -> None:
        scaled = simple_recipe.scaled(2.0)
        assert scaled.total_amount_g == pytest.approx(3440.0)
        assert scaled.baked_weight_g == pytest.approx(3000.0)

    def test_scaling_leaves_the_baking_energy_alone(self, simple_recipe: Recipe) -> None:
        """Der Ofen braucht für zwei Brote nicht doppelt so viel Strom."""
        simple_recipe.energy_kwh = 1.5
        assert simple_recipe.scaled(2.0).energy_kwh == pytest.approx(1.5)

    def test_scaling_generates_a_name(self, simple_recipe: Recipe) -> None:
        assert "×2,00" in simple_recipe.scaled(2.0).name

    def test_scaling_accepts_an_explicit_name(self, simple_recipe: Recipe) -> None:
        assert simple_recipe.scaled(2.0, name="Doppelt").name == "Doppelt"

    @pytest.mark.parametrize("factor", [0.0, -1.0, float("inf")])
    def test_invalid_factor_is_rejected(self, simple_recipe: Recipe, factor: float) -> None:
        with pytest.raises(ValueError, match="Skalierungsfaktor"):
            simple_recipe.scaled(factor)

    def test_item_display_name(self) -> None:
        assert RecipeItem("k", "Mehl", "Bauck", 1).display_name == "Mehl (Bauck)"
        assert RecipeItem("k", "Wasser", "", 1).display_name == "Wasser"


class TestProperties:
    @given(
        name=st.text(min_size=1, max_size=40).filter(lambda s: s.strip()),
        manufacturer=st.text(max_size=20),
    )
    def test_key_is_stable_and_lowercase(self, name: str, manufacturer: str) -> None:
        item = Ingredient(name=name, manufacturer=manufacturer)
        assert item.key == item.key
        assert item.key == item.key.casefold()

    @given(
        energy=st.floats(min_value=0, max_value=900, allow_nan=False),
        fat=st.floats(min_value=0, max_value=100, allow_nan=False),
        price=st.floats(min_value=0, max_value=100, allow_nan=False),
        size=st.floats(min_value=1, max_value=10000, allow_nan=False),
    )
    def test_serialisation_roundtrip_preserves_numbers(
        self, energy: float, fat: float, price: float, size: float
    ) -> None:
        original = Ingredient(
            name="Prüfzutat",
            nutrients=Nutrients(energy_kcal=energy, fat=fat),
            package_price=price,
            package_size_g=size,
        )
        restored = Ingredient.from_dict(original.to_dict())
        assert restored.nutrients == original.nutrients
        assert restored.package_price == pytest.approx(original.package_price)

    @given(factor=st.floats(min_value=0.01, max_value=50, allow_nan=False))
    def test_scaling_preserves_the_ratios(self, factor: float) -> None:
        recipe = Recipe(
            name="R",
            items=[RecipeItem("a|", "A", "", 100.0), RecipeItem("b|", "B", "", 250.0)],
            baked_weight_g=300.0,
        )
        scaled = recipe.scaled(factor)
        ratio_before = recipe.items[1].amount_g / recipe.items[0].amount_g
        ratio_after = scaled.items[1].amount_g / scaled.items[0].amount_g
        assert ratio_after == pytest.approx(ratio_before)
