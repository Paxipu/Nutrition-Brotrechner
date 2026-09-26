"""Tests der Persistenzschicht: Container, atomares Schreiben, Laden, Fehlerfälle."""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from brotrechner.core.models import Ingredient, Recipe, RecipeItem
from brotrechner.data.repository import (
    MAX_JSON_NESTING,
    SCHEMA_VERSION,
    IngredientStore,
    RecipeStore,
    RepositoryError,
    load_ingredients,
    load_recipes,
    read_json,
    save_ingredients,
    save_recipes,
    write_json_atomic,
)

#: Zeichen, an denen sich eine Zählung der Klammern verschlucken kann.
_TRICKY = '[]{}"\\ x\n'


class TestIngredientStore:
    def test_indexes_by_key(self, flour: Ingredient) -> None:
        store = IngredientStore([flour])
        assert len(store) == 1
        assert store.get(flour.key) is flour
        assert flour.key in store

    def test_unknown_key_returns_none(self) -> None:
        assert IngredientStore().get("gibt|esnicht") is None

    def test_duplicate_add_is_rejected(self, flour: Ingredient) -> None:
        store = IngredientStore([flour])
        with pytest.raises(KeyError, match="existiert bereits"):
            store.add(flour.copy())

    def test_replace_existing_is_allowed_explicitly(self, flour: Ingredient) -> None:
        store = IngredientStore([flour])
        store.add(flour.copy(), replace_existing=True)
        assert len(store) == 1

    def test_remove_returns_the_item(self, flour: Ingredient) -> None:
        store = IngredientStore([flour])
        assert store.remove(flour.key) is flour
        assert len(store) == 0

    def test_remove_unknown_raises(self) -> None:
        with pytest.raises(KeyError):
            IngredientStore().remove("weg|")

    def test_replace_handles_a_changed_key(self, flour: Ingredient) -> None:
        """Beim Umbenennen ändert sich der Schlüssel - der alte muss verschwinden."""
        store = IngredientStore([flour])
        old_key = flour.key
        renamed = flour.copy(name="Roggenmehl Vollkorn")
        store.replace(old_key, renamed)
        assert old_key not in store
        assert renamed.key in store
        assert len(store) == 1

    def test_replace_rejects_a_collision(self, flour: Ingredient, water: Ingredient) -> None:
        store = IngredientStore([flour, water])
        collision = flour.copy(name=water.name, manufacturer=water.manufacturer)
        with pytest.raises(KeyError, match="existiert bereits"):
            store.replace(flour.key, collision)

    def test_replace_with_unchanged_key_works(self, flour: Ingredient) -> None:
        store = IngredientStore([flour])
        flour.package_price = 2.49
        store.replace(flour.key, flour)
        assert store[flour.key].package_price == 2.49

    def test_find_by_name(self, flour: Ingredient) -> None:
        store = IngredientStore([flour])
        assert store.find_by_name("roggenvollkornmehl", "BAUCK") is flour
        assert store.find_by_name("Roggenvollkornmehl") is None

    def test_manufacturers_are_unique_and_sorted(self, flour: Ingredient) -> None:
        store = IngredientStore(
            [flour, flour.copy(name="Anderes"), flour.copy(name="X", manufacturer="Aldi")]
        )
        assert store.manufacturers == ["Aldi", "Bauck"]

    def test_sorted_by_display_name(self, flour: Ingredient, water: Ingredient) -> None:
        store = IngredientStore([water, flour])
        assert [i.name for i in store.sorted()] == ["Roggenvollkornmehl", "Wasser"]

    def test_iteration_and_dict_view(self, flour: Ingredient) -> None:
        store = IngredientStore([flour])
        assert list(store) == [flour]
        assert store.as_dict() == {flour.key: flour}


class TestRecipeStore:
    def test_lookup_ignores_case(self, simple_recipe: Recipe) -> None:
        store = RecipeStore([simple_recipe])
        assert store.get("TESTBROT") is simple_recipe
        assert "testbrot" in store

    def test_duplicate_is_rejected(self, simple_recipe: Recipe) -> None:
        store = RecipeStore([simple_recipe])
        with pytest.raises(KeyError, match="existiert bereits"):
            store.add(simple_recipe)

    def test_remove(self, simple_recipe: Recipe) -> None:
        store = RecipeStore([simple_recipe])
        store.remove("Testbrot")
        assert len(store) == 0

    def test_sorting_survives_migrated_timestamps(self, simple_recipe: Recipe) -> None:
        """Ein migriertes Rezept neben einem neuen darf die Sortierung nicht sprengen."""
        migrated = Recipe.from_dict(
            {"name": "Aus der Altversion", "created_at": "2025-10-12T00:06:20.377423"}
        )
        store = RecipeStore([migrated, simple_recipe])
        assert store.sorted_by_date()[0].name == simple_recipe.name

    def test_saving_a_mixed_store_works(self, tmp_path: Path, simple_recipe: Recipe) -> None:
        """Der Fall, der beim Speichern eines neuen Rezepts abstürzte."""
        migrated = Recipe.from_dict(
            {"name": "Aus der Altversion", "created_at": "2025-10-12T00:06:20.377423"}
        )
        target = tmp_path / "recipes.json"
        save_recipes(target, RecipeStore([migrated, simple_recipe]))
        loaded, _ = load_recipes(target, IngredientStore())
        assert len(loaded) == 2

    def test_sorting(self, simple_recipe: Recipe) -> None:
        older = Recipe(name="Alt")
        older.created_at = simple_recipe.created_at.replace(year=2020)
        store = RecipeStore([older, simple_recipe])
        assert store.sorted_by_date()[0] is simple_recipe
        assert [r.name for r in store.sorted_by_name()] == ["Alt", "Testbrot"]


class TestAtomicWrite:
    def test_creates_the_file_and_parent(self, tmp_path: Path) -> None:
        target = tmp_path / "tief" / "daten.json"
        write_json_atomic(target, {"a": 1}, backup=False)
        assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1}

    def test_leaves_no_temporary_files(self, tmp_path: Path) -> None:
        target = tmp_path / "daten.json"
        write_json_atomic(target, {"a": 1}, backup=False)
        assert [p.name for p in tmp_path.iterdir()] == ["daten.json"]

    def test_overwrites_completely(self, tmp_path: Path) -> None:
        target = tmp_path / "daten.json"
        write_json_atomic(target, {"lang": "x" * 500}, backup=False)
        write_json_atomic(target, {"kurz": 1}, backup=False)
        assert json.loads(target.read_text(encoding="utf-8")) == {"kurz": 1}

    def test_umlauts_survive(self, tmp_path: Path) -> None:
        target = tmp_path / "daten.json"
        write_json_atomic(target, {"name": "Kürbiskernöl"}, backup=False)
        assert "Kürbiskernöl" in target.read_text(encoding="utf-8")

    def test_backup_is_written_next_to_the_file(self, tmp_path: Path) -> None:
        """Die Sicherung liegt neben der Datei, nicht in einem festen Ordner.

        Sonst landeten Sicherungen bei ``--data-dir`` im falschen Verzeichnis.
        """
        target = tmp_path / "daten.json"
        write_json_atomic(target, {"stand": 1})
        write_json_atomic(target, {"stand": 2})
        backups = list((tmp_path / "backups").glob("daten_*.json"))
        assert len(backups) == 1
        assert json.loads(backups[0].read_text(encoding="utf-8")) == {"stand": 1}

    def test_only_the_most_recent_backups_are_kept(self, tmp_path: Path) -> None:
        from brotrechner.data.repository import MAX_BACKUPS

        target = tmp_path / "daten.json"
        for stand in range(MAX_BACKUPS + 4):
            write_json_atomic(target, {"stand": stand})
        assert len(list((tmp_path / "backups").glob("daten_*.json"))) <= MAX_BACKUPS

    def test_unwritable_target_raises(self, tmp_path: Path) -> None:
        blocked = tmp_path / "datei.json"
        blocked.write_text("x", encoding="utf-8")
        with pytest.raises(RepositoryError, match="konnte nicht geschrieben werden"):
            write_json_atomic(blocked / "unmoeglich.json", {}, backup=False)


class TestReadJson:
    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(RepositoryError, match="konnte nicht gelesen werden"):
            read_json(tmp_path / "weg.json")

    def test_deeply_nested_file_is_rejected_not_crashed(self, tmp_path: Path) -> None:
        """Eine bösartig verschachtelte Importdatei darf nicht durchschlagen."""
        evil = tmp_path / "tief.json"
        evil.write_text("[" * 60_000 + "]" * 60_000, encoding="utf-8")
        with pytest.raises(RepositoryError, match="verschachtelt"):
            read_json(evil)

    def test_the_nesting_limit_does_not_depend_on_python(self, tmp_path: Path) -> None:
        """Python 3.14.7 liest 60 000 Ebenen ohne Rekursionsfehler - abgewiesen wird trotzdem.

        Der Schutz hing bisher am ``RecursionError`` des JSON-Lesers, und der
        tritt je nach Interpreter früher, später oder gar nicht auf.
        """
        allowed = tmp_path / "grenze.json"
        allowed.write_text("[" * MAX_JSON_NESTING + "]" * MAX_JSON_NESTING, encoding="utf-8")
        assert read_json(allowed) is not None
        # Das Objekt ist eine Ebene, die Listen darin sind die übrigen.
        too_deep = tmp_path / "zu_tief.json"
        lists = "[" * MAX_JSON_NESTING + "]" * MAX_JSON_NESTING
        too_deep.write_text('{"a": ' + lists + "}", encoding="utf-8")
        with pytest.raises(RepositoryError, match=f"mehr als {MAX_JSON_NESTING} Ebenen"):
            read_json(too_deep)

    def test_brackets_in_text_do_not_count(self, tmp_path: Path) -> None:
        """Klammern in Zeichenketten zählen nicht.

        ``\\"`` beendet eine Zeichenkette nicht, ``\\\\"`` dagegen schon - wer
        das verwechselt, hält die Klammern in ``rest`` für Verschachtelung.
        """
        many = "[" * (MAX_JSON_NESTING * 5)
        data = {
            "name": "[{" * MAX_JSON_NESTING,
            "notiz": f'" {many} "\\',
            "pfad": "\\",
            "rest": many,
        }
        path = tmp_path / "text.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        assert read_json(path) == data

    @given(
        data=st.recursive(
            st.none()
            | st.booleans()
            | st.integers()
            | st.floats(allow_nan=False)
            | st.text(alphabet=_TRICKY)
            | st.text(),
            lambda inner: (
                st.lists(inner, max_size=4)
                | st.dictionaries(st.text(alphabet=_TRICKY), inner, max_size=4)
            ),
            max_leaves=30,
        ),
        ascii_only=st.booleans(),
    )
    def test_everything_below_the_limit_is_read_back(self, data: object, ascii_only: bool) -> None:
        """Was die eigenen Dateien enthalten können, kommt unverändert zurück."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "daten.json"
            path.write_text(json.dumps(data, ensure_ascii=ascii_only, indent=2), encoding="utf-8")
            assert read_json(path) == data

    def test_an_unfinished_text_is_scanned_quickly(self, tmp_path: Path) -> None:
        """Eine offene Zeichenkette voller ``\\"``.

        Ein Muster, das Zeichenketten naiv erkennt, braucht dafür Rechenzeit im
        Quadrat der Länge - hier gut eine halbe Minute statt Millisekunden.
        """
        broken = tmp_path / "offen.json"
        broken.write_text('["' + '\\"' * 50_000, encoding="utf-8")
        start = time.perf_counter()
        with pytest.raises(RepositoryError, match="kein gültiges JSON"):
            read_json(broken)
        assert time.perf_counter() - start < 2

    def test_broken_json_names_the_line(self, tmp_path: Path) -> None:
        broken = tmp_path / "kaputt.json"
        broken.write_text('{\n  "a": 1,\n  "b":\n}', encoding="utf-8")
        with pytest.raises(RepositoryError, match="Zeile"):
            read_json(broken)


class TestLoadSave:
    def test_roundtrip(self, tmp_path: Path, flour: Ingredient, water: Ingredient) -> None:
        target = tmp_path / "ingredients.json"
        save_ingredients(target, IngredientStore([flour, water]))
        loaded, result = load_ingredients(target)
        assert len(loaded) == 2
        assert not result.migrated
        assert loaded.get(flour.key) is not None

    def test_missing_file_yields_empty_store(self, tmp_path: Path) -> None:
        store, result = load_ingredients(tmp_path / "weg.json")
        assert len(store) == 0
        assert not result.migrated

    def test_unknown_schema_version_is_rejected(self, tmp_path: Path) -> None:
        target = tmp_path / "ingredients.json"
        target.write_text(json.dumps({"schema_version": 99, "ingredients": []}), encoding="utf-8")
        with pytest.raises(RepositoryError, match="Schemaversion"):
            load_ingredients(target)

    def test_missing_ingredients_field(self, tmp_path: Path) -> None:
        target = tmp_path / "ingredients.json"
        target.write_text(json.dumps({"schema_version": SCHEMA_VERSION}), encoding="utf-8")
        with pytest.raises(RepositoryError, match="'ingredients' fehlt"):
            load_ingredients(target)

    def test_list_instead_of_object(self, tmp_path: Path) -> None:
        target = tmp_path / "ingredients.json"
        target.write_text("[]", encoding="utf-8")
        with pytest.raises(RepositoryError, match="Objekt erwartet"):
            load_ingredients(target)

    def test_broken_entry_is_skipped_and_reported(self, tmp_path: Path) -> None:
        """Eine kaputte Zeile darf nicht die ganze Datenbank unbrauchbar machen."""
        target = tmp_path / "ingredients.json"
        target.write_text(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "ingredients": [{"name": "Gut"}, {"name": ""}, "kein Objekt"],
                }
            ),
            encoding="utf-8",
        )
        store, result = load_ingredients(target)
        assert len(store) == 1
        assert len(result.notes) == 2

    def test_recipes_roundtrip(self, tmp_path: Path, simple_recipe: Recipe) -> None:
        target = tmp_path / "recipes.json"
        save_recipes(target, RecipeStore([simple_recipe]))
        loaded, _ = load_recipes(target, IngredientStore())
        assert len(loaded) == 1
        assert loaded.get("Testbrot") is not None

    def test_recipes_unknown_schema(self, tmp_path: Path) -> None:
        target = tmp_path / "recipes.json"
        target.write_text(json.dumps({"schema_version": 7, "recipes": []}), encoding="utf-8")
        with pytest.raises(RepositoryError, match="Schemaversion"):
            load_recipes(target, IngredientStore())

    def test_recipes_missing_field(self, tmp_path: Path) -> None:
        target = tmp_path / "recipes.json"
        target.write_text(json.dumps({"schema_version": SCHEMA_VERSION}), encoding="utf-8")
        with pytest.raises(RepositoryError, match="'recipes' fehlt"):
            load_recipes(target, IngredientStore())

    def test_broken_recipe_entry_is_skipped(self, tmp_path: Path) -> None:
        target = tmp_path / "recipes.json"
        target.write_text(
            json.dumps({"schema_version": SCHEMA_VERSION, "recipes": [{"name": ""}, 5]}),
            encoding="utf-8",
        )
        store, result = load_recipes(target, IngredientStore())
        assert len(store) == 0
        assert len(result.notes) == 2

    def test_saved_file_carries_metadata(self, tmp_path: Path, flour: Ingredient) -> None:
        target = tmp_path / "ingredients.json"
        save_ingredients(target, IngredientStore([flour]))
        payload = json.loads(target.read_text(encoding="utf-8"))
        assert payload["schema_version"] == SCHEMA_VERSION
        assert payload["generator"].startswith("brotrechner")
        assert "updated_at" in payload

    def test_recipe_item_references_survive(
        self, tmp_path: Path, simple_recipe: Recipe, flour: Ingredient
    ) -> None:
        target = tmp_path / "recipes.json"
        save_recipes(target, RecipeStore([simple_recipe]))
        loaded, _ = load_recipes(target, IngredientStore([flour]))
        recipe = loaded.get("Testbrot")
        assert recipe is not None
        assert any(item.ingredient_key == flour.key for item in recipe.items)


class TestRecipeItemPersistence:
    def test_denormalised_name_keeps_deleted_ingredients_readable(self, tmp_path: Path) -> None:
        recipe = Recipe(
            name="Historisch",
            items=[RecipeItem("weg|weg", "Verschollenes Mehl", "Mühle X", 500.0)],
            baked_weight_g=400.0,
        )
        target = tmp_path / "recipes.json"
        save_recipes(target, RecipeStore([recipe]))
        loaded, _ = load_recipes(target, IngredientStore())
        item = loaded.get("Historisch").items[0]  # type: ignore[union-attr]
        assert item.display_name == "Verschollenes Mehl (Mühle X)"
