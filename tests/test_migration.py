"""Tests der Migration aus dem Altformat (Brot-Kalkulator v4)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from brotrechner.core.models import Category, Source
from brotrechner.data.migration import (
    LEGACY_CATEGORY_MAP,
    looks_like_legacy_ingredients,
    looks_like_legacy_recipes,
    migrate_ingredient,
    migrate_ingredients,
    migrate_recipes,
    split_manufacturer,
)
from brotrechner.data.repository import load_ingredients, load_recipes


def legacy_entry(name: str, **overrides: Any) -> dict[str, Any]:
    """Ein Zutateneintrag im Altformat."""
    entry: dict[str, Any] = {
        "name": name,
        "kategorie": "Mehl",
        "kalorien": 323,
        "fett": 2.0,
        "fett_gesaettigt": 0.3,
        "kohlenhydrate": 62.0,
        "zucker": 0.9,
        "eiweiss": 13.0,
        "salz": 0.01,
        "ballaststoffe": 13.4,
        "wassergehalt": 14.0,
        "preis_pro_packung": 0,
        "packungsgroesse": 0,
        "preis_historie": [],
    }
    entry.update(overrides)
    return entry


class TestSplitManufacturer:
    @pytest.mark.parametrize(
        ("raw", "name", "manufacturer"),
        [
            ("Roggenvollkornmehl (Bauck)", "Roggenvollkornmehl", "Bauck"),
            ("Dinkelvollkornmehl (dm Bio)", "Dinkelvollkornmehl", "dm Bio"),
            ("Hafer (ganz)(dm)", "Hafer (ganz)", "dm"),
            ("Dinkel (ganz)(Alnatura)", "Dinkel (ganz)", "Alnatura"),
            ("Leinmehl (teilentölt)(Rapunzel)", "Leinmehl (teilentölt)", "Rapunzel"),
            ("Gluten rein (Grünland)", "Gluten rein", "Grünland"),
            ("Weizenmehl Type 550 (Aldi)", "Weizenmehl Type 550", "Aldi"),
        ],
    )
    def test_known_manufacturers_are_extracted(
        self, raw: str, name: str, manufacturer: str
    ) -> None:
        assert split_manufacturer(raw) == (name, manufacturer)

    @pytest.mark.parametrize(
        "raw",
        [
            "Mohn (blau)",
            "Hefe (frisch)",
            "Joghurt (natur, 3,5%)",
            "Kartoffel (gekocht)",
            "Backmalz (inaktiv)",
            "Gluten (Weizenkleber)",
            "Schwarzkümmel (Nigella)",
            "Cranberries (getrocknet)",
        ],
    )
    def test_factual_additions_stay_in_the_name(self, raw: str) -> None:
        """Fachliche Klammerzusätze dürfen nicht als Hersteller gedeutet werden."""
        assert split_manufacturer(raw) == (raw, "")

    def test_plain_name_is_untouched(self) -> None:
        assert split_manufacturer("Weizenmehl Type 405") == ("Weizenmehl Type 405", "")

    def test_whitespace_is_normalised(self) -> None:
        assert split_manufacturer("Mehl   (Bauck)") == ("Mehl", "Bauck")

    def test_matching_ignores_case(self) -> None:
        assert split_manufacturer("Mehl (BAUCK)")[1] == "Bauck"


class TestIngredientMigration:
    def test_field_names_are_translated(self) -> None:
        item = migrate_ingredient(legacy_entry("Roggenvollkornmehl"))
        assert item.nutrients.energy_kcal == 323
        assert item.nutrients.carbs == 62.0
        assert item.nutrients.protein == 13.0
        assert item.nutrients.fiber == 13.4
        assert item.nutrients.water == 14.0

    def test_category_is_translated(self) -> None:
        assert migrate_ingredient(legacy_entry("X")).category is Category.FLOUR

    def test_every_old_category_is_mapped(self) -> None:
        assert set(LEGACY_CATEGORY_MAP.values()) == set(Category)

    def test_unknown_category_becomes_other(self) -> None:
        item = migrate_ingredient(legacy_entry("X", kategorie="Astronautenkost"))
        assert item.category is Category.OTHER

    def test_flour_flag_from_the_category(self) -> None:
        assert migrate_ingredient(legacy_entry("Weizenmehl")).is_flour

    def test_flour_flag_from_the_name(self) -> None:
        item = migrate_ingredient(legacy_entry("Kartoffelstärke", kategorie="Sonstiges"))
        assert item.is_flour

    def test_breadcrumbs_are_no_longer_flour(self) -> None:
        """Die alte Heuristik zählte "Altbrot (Paniermehl)" wegen der Silbe mit."""
        item = migrate_ingredient(legacy_entry("Altbrot (Paniermehl)", kategorie="Sonstiges"))
        assert not item.is_flour

    def test_linseed_flour_stays_flour(self) -> None:
        """Bewusst unverändert, damit sich bestehende Rezepte nicht verschieben."""
        item = migrate_ingredient(legacy_entry("Leinmehl (teilentölt)", kategorie="Sonstiges"))
        assert item.is_flour

    def test_branded_items_are_marked_as_label_source(self) -> None:
        assert migrate_ingredient(legacy_entry("Mehl (Bauck)")).nutrition_source is Source.LABEL

    def test_generic_items_are_marked_as_reference(self) -> None:
        assert migrate_ingredient(legacy_entry("Mehl")).nutrition_source is Source.REFERENCE

    def test_price_history_is_carried_over(self) -> None:
        item = migrate_ingredient(
            legacy_entry(
                "Mehl",
                preis_historie=[{"datum": "2025-01-01T10:00:00", "preis": 1.49, "groesse": 1000}],
            )
        )
        assert len(item.price_history) == 1
        assert item.price_history[0].package_price == pytest.approx(1.49)

    def test_broken_history_timestamp_falls_back(self) -> None:
        item = migrate_ingredient(
            legacy_entry("Mehl", preis_historie=[{"datum": "??", "preis": 1, "groesse": 1}])
        )
        assert item.price_history[0].recorded_at.year >= 2024

    def test_name_comes_from_the_dict_key_if_missing(self) -> None:
        entry = legacy_entry("X")
        del entry["name"]
        assert migrate_ingredient(entry, fallback_name="Ersatzname").name == "Ersatzname"

    def test_entry_without_any_name_is_rejected(self) -> None:
        entry = legacy_entry("X")
        entry["name"] = ""
        with pytest.raises(ValueError, match="ohne Namen"):
            migrate_ingredient(entry)


class TestDatabaseMigration:
    def test_case_only_duplicates_are_merged(self) -> None:
        """Genau der Fall "Kürbiskernöl" / "KürbiskernÖl" aus der Altdatenbank."""
        raw = {
            "Kürbiskernöl (dm Bio)": legacy_entry("Kürbiskernöl (dm Bio)", kategorie="Fette & Öle"),
            "KürbiskernÖl (dm Bio)": legacy_entry("KürbiskernÖl (dm Bio)", kategorie="Fette & Öle"),
        }
        items, notes = migrate_ingredients(raw)
        assert len(items) == 1
        assert any("zusammengeführt" in note for note in notes)

    def test_the_more_complete_entry_wins(self) -> None:
        raw = {
            "Mehl": legacy_entry("Mehl", preis_pro_packung=0, packungsgroesse=0),
            "MEHL": legacy_entry("MEHL", preis_pro_packung=1.99, packungsgroesse=1000),
        }
        items, _ = migrate_ingredients(raw)
        assert items[0].has_price

    def test_non_object_entries_are_skipped(self) -> None:
        items, notes = migrate_ingredients({"Mehl": legacy_entry("Mehl"), "Müll": "kaputt"})
        assert len(items) == 1
        assert any("übersprungen" in note for note in notes)

    def test_nameless_entry_is_skipped(self) -> None:
        entry = legacy_entry("X")
        entry["name"] = ""
        items, notes = migrate_ingredients({"": entry})
        assert items == []
        assert notes


class TestRecipeMigration:
    def test_pairs_become_recipe_items(self) -> None:
        ingredients, _ = migrate_ingredients({"Mehl (Bauck)": legacy_entry("Mehl (Bauck)")})
        by_key = {i.key: i for i in ingredients}
        raw = {
            "Brot": {
                "name": "Brot",
                "zutaten": [["Mehl (Bauck)", 550.0]],
                "gewicht_gebacken": 775.0,
                "gewicht_rohteig": 0,
                "notizen": "lecker",
                "erstellt_am": "2025-10-12T00:06:20",
            }
        }
        recipes, notes = migrate_recipes(raw, by_key)
        assert len(recipes) == 1
        assert recipes[0].items[0].name == "Mehl"
        assert recipes[0].items[0].manufacturer == "Bauck"
        assert recipes[0].items[0].amount_g == 550.0
        assert recipes[0].notes == "lecker"
        assert not notes

    def test_unknown_ingredient_is_reported_but_kept(self) -> None:
        raw = {"Brot": {"name": "Brot", "zutaten": [["Phantommehl", 100.0]]}}
        recipes, notes = migrate_recipes(raw, {})
        assert len(recipes[0].items) == 1
        assert any("nicht in der Datenbank" in note for note in notes)

    def test_broken_row_is_skipped(self) -> None:
        raw = {"Brot": {"name": "Brot", "zutaten": [["Mehl"], ["Wasser", 1, 2]]}}
        recipes, notes = migrate_recipes(raw, {})
        assert recipes[0].items == []
        assert len(notes) == 2

    def test_non_object_recipe_is_skipped(self) -> None:
        recipes, notes = migrate_recipes({"X": "kaputt"}, {})
        assert recipes == []
        assert notes


class TestFormatDetection:
    def test_legacy_ingredients_are_recognised(self) -> None:
        assert looks_like_legacy_ingredients({"Mehl": legacy_entry("Mehl")})

    def test_new_format_is_not_mistaken(self) -> None:
        assert not looks_like_legacy_ingredients({"schema_version": 2, "ingredients": []})

    def test_non_dict_is_not_legacy(self) -> None:
        assert not looks_like_legacy_ingredients([])

    def test_legacy_recipes_are_recognised(self) -> None:
        assert looks_like_legacy_recipes({"Brot": {"zutaten": []}})

    def test_new_recipes_are_not_mistaken(self) -> None:
        assert not looks_like_legacy_recipes({"schema_version": 2, "recipes": []})


class TestEndToEnd:
    def test_legacy_files_load_through_the_repository(self, tmp_path: Path) -> None:
        """Der Weg, den das Programm beim ersten Start nimmt."""
        ingredients_file = tmp_path / "brot_zutaten.json"
        ingredients_file.write_text(
            json.dumps(
                {
                    "Roggenvollkornmehl (Bauck)": legacy_entry("Roggenvollkornmehl (Bauck)"),
                    "Wasser": legacy_entry(
                        "Wasser", kategorie="Grundzutaten", kalorien=0, wassergehalt=100.0
                    ),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        recipes_file = tmp_path / "brot_rezepte.json"
        recipes_file.write_text(
            json.dumps(
                {
                    "Brot": {
                        "name": "Brot",
                        "zutaten": [["Roggenvollkornmehl (Bauck)", 550.0], ["Wasser", 392.0]],
                        "gewicht_gebacken": 775.0,
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        store, ingredient_result = load_ingredients(ingredients_file)
        recipes, recipe_result = load_recipes(recipes_file, store)

        assert ingredient_result.migrated
        assert recipe_result.migrated
        assert len(store) == 2
        assert store.find_by_name("Roggenvollkornmehl", "Bauck") is not None
        recipe = recipes.get("Brot")
        assert recipe is not None
        assert all(item.ingredient_key in store for item in recipe.items)
