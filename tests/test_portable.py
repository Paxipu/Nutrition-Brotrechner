"""Tests für Im- und Export einzelner Zutaten."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from brotrechner.core.models import Ingredient
from brotrechner.data.portable import (
    ConflictPolicy,
    apply_import,
    export_ingredients,
    parse_ingredient_file,
    preview_import,
)
from brotrechner.data.repository import SCHEMA_VERSION, IngredientStore, RepositoryError


class TestExport:
    def test_writes_the_exchange_format(self, tmp_path: Path, flour: Ingredient) -> None:
        target = tmp_path / "zutat.json"
        export_ingredients(target, [flour])
        payload = json.loads(target.read_text(encoding="utf-8"))
        assert payload["schema_version"] == SCHEMA_VERSION
        assert payload["kind"] == "ingredient"
        assert payload["ingredients"][0]["name"] == "Roggenvollkornmehl"
        assert payload["ingredients"][0]["manufacturer"] == "Bauck"

    def test_several_ingredients_at_once(
        self, tmp_path: Path, flour: Ingredient, water: Ingredient
    ) -> None:
        target = tmp_path / "auswahl.json"
        export_ingredients(target, [flour, water])
        assert len(json.loads(target.read_text(encoding="utf-8"))["ingredients"]) == 2

    def test_empty_selection_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="keine Zutat"):
            export_ingredients(tmp_path / "leer.json", [])

    def test_no_backup_file_is_created(self, tmp_path: Path, flour: Ingredient) -> None:
        """Ein Export ist kein Datenbankstand und braucht keine Sicherung."""
        target = tmp_path / "zutat.json"
        export_ingredients(target, [flour])
        export_ingredients(target, [flour])
        assert list(tmp_path.iterdir()) == [target]


class TestRoundtrip:
    def test_export_and_import_preserve_everything(self, tmp_path: Path, flour: Ingredient) -> None:
        target = tmp_path / "zutat.json"
        flour.notes = "Etikett vom 03.06."
        export_ingredients(target, [flour])
        restored = parse_ingredient_file(target)[0]
        assert restored.key == flour.key
        assert restored.nutrients == flour.nutrients
        assert restored.is_flour == flour.is_flour
        assert restored.notes == flour.notes


class TestParsing:
    def test_bare_single_ingredient(self, tmp_path: Path) -> None:
        target = tmp_path / "einzeln.json"
        target.write_text(json.dumps({"name": "Salz", "salt": 100.0}), encoding="utf-8")
        items = parse_ingredient_file(target)
        assert items[0].name == "Salz"
        assert items[0].nutrients.salt == 100.0

    def test_bare_list(self, tmp_path: Path) -> None:
        target = tmp_path / "liste.json"
        target.write_text(json.dumps([{"name": "A"}, {"name": "B"}]), encoding="utf-8")
        assert len(parse_ingredient_file(target)) == 2

    def test_full_database_file(self, tmp_path: Path, flour: Ingredient) -> None:
        target = tmp_path / "db.json"
        target.write_text(
            json.dumps({"schema_version": SCHEMA_VERSION, "ingredients": [flour.to_dict()]}),
            encoding="utf-8",
        )
        assert parse_ingredient_file(target)[0].name == "Roggenvollkornmehl"

    def test_legacy_dictionary(self, tmp_path: Path) -> None:
        """Alte Exporte sollen weiter einlesbar bleiben."""
        target = tmp_path / "alt.json"
        target.write_text(
            json.dumps(
                {
                    "Roggenvollkornmehl (Bauck)": {
                        "name": "Roggenvollkornmehl (Bauck)",
                        "kategorie": "Mehl",
                        "kalorien": 323,
                        "kohlenhydrate": 62.0,
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        item = parse_ingredient_file(target)[0]
        assert item.name == "Roggenvollkornmehl"
        assert item.manufacturer == "Bauck"

    def test_bare_legacy_ingredient(self, tmp_path: Path) -> None:
        target = tmp_path / "alt_einzeln.json"
        target.write_text(
            json.dumps({"name": "Mehl", "kalorien": 300, "kohlenhydrate": 60}), encoding="utf-8"
        )
        assert parse_ingredient_file(target)[0].nutrients.carbs == 60

    @pytest.mark.parametrize(
        ("content", "message"),
        [
            ("42", "Objekt oder Liste"),
            ('{"beliebig": 1}', "kein erkennbares"),
            ('{"schema_version": 99, "ingredients": []}', "Schemaversion"),
            ('{"ingredients": ["kein Objekt"]}', "kein Objekt"),
            ('{"ingredients": [{"name": ""}]}', "fehlerhaft"),
            ('{"ingredients": []}', "enthält keine Zutat"),
        ],
    )
    def test_broken_files_are_rejected_with_a_reason(
        self, tmp_path: Path, content: str, message: str
    ) -> None:
        target = tmp_path / "kaputt.json"
        target.write_text(content, encoding="utf-8")
        with pytest.raises(RepositoryError, match=message):
            parse_ingredient_file(target)


class TestPreview:
    def test_separates_new_from_conflicting(self, flour: Ingredient, water: Ingredient) -> None:
        store = IngredientStore([flour])
        preview = preview_import([flour.copy(), water], store)
        assert len(preview.new) == 1
        assert len(preview.conflicting) == 1
        assert preview.total == 2
        assert preview.has_conflicts

    def test_preview_leaves_the_store_untouched(self, flour: Ingredient) -> None:
        store = IngredientStore()
        preview_import([flour], store)
        assert len(store) == 0

    def test_no_conflicts(self, water: Ingredient) -> None:
        assert not preview_import([water], IngredientStore()).has_conflicts


class TestApplyImport:
    def test_new_ingredients_are_added(self, water: Ingredient) -> None:
        store = IngredientStore()
        result = apply_import([water], store)
        assert len(store) == 1
        assert len(result.added) == 1
        assert result.changed == 1

    def test_skip_keeps_the_existing_values(self, flour: Ingredient) -> None:
        store = IngredientStore([flour])
        incoming = flour.copy()
        incoming.package_price = 99.0
        apply_import([incoming], store, ConflictPolicy.SKIP)
        assert store[flour.key].package_price == pytest.approx(1.98)

    def test_replace_overwrites(self, flour: Ingredient) -> None:
        store = IngredientStore([flour])
        incoming = flour.copy()
        incoming.package_price = 99.0
        result = apply_import([incoming], store, ConflictPolicy.REPLACE)
        assert store[flour.key].package_price == pytest.approx(99.0)
        assert len(result.replaced) == 1

    def test_keep_both_renames_the_import(self, flour: Ingredient) -> None:
        store = IngredientStore([flour])
        result = apply_import([flour.copy()], store, ConflictPolicy.KEEP_BOTH)
        assert len(store) == 2
        assert result.renamed[0].name == "Roggenvollkornmehl (2)"

    def test_keep_both_counts_up_on_repeat(self, flour: Ingredient) -> None:
        store = IngredientStore([flour])
        apply_import([flour.copy()], store, ConflictPolicy.KEEP_BOTH)
        apply_import([flour.copy()], store, ConflictPolicy.KEEP_BOTH)
        assert len(store) == 3
        assert store.find_by_name("Roggenvollkornmehl (3)", "Bauck") is not None

    def test_summary_text(self, flour: Ingredient, water: Ingredient) -> None:
        store = IngredientStore([flour])
        result = apply_import([flour.copy(), water], store, ConflictPolicy.SKIP)
        assert "1 neu" in result.summary()
        assert "1 übersprungen" in result.summary()

    def test_summary_when_nothing_happened(self) -> None:
        store = IngredientStore()
        assert apply_import([], store).summary() == "keine Änderungen"

    def test_every_policy_has_a_label(self) -> None:
        assert all(policy.label for policy in ConflictPolicy)
