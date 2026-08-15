"""Tests der Startdatenbank, der Erstbefüllung und der Kommandozeile."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from brotrechner import cli, paths
from brotrechner.core.models import Category, Ingredient
from brotrechner.core.nutrients import Nutrients
from brotrechner.core.validation import Severity, validate_database
from brotrechner.data.repository import IngredientStore, load_ingredients
from brotrechner.data.seed import (
    ensure_user_database,
    load_seed_ingredients,
    merge_seed_into,
    missing_from_seed,
    seed_path,
)


def legacy_ingredients_file(path: Path, **entries: dict[str, Any]) -> Path:
    """Schreibt eine Zutatendatei im Altformat."""
    path.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    return path


class TestSeedDatabase:
    def test_the_shipped_file_exists(self) -> None:
        assert seed_path().exists()

    def test_it_loads(self) -> None:
        assert len(load_seed_ingredients()) > 90

    def test_it_passes_its_own_validation(self) -> None:
        """Die ausgelieferte Datenbank darf keinen einzigen Bilanzfehler enthalten."""
        findings = validate_database(load_seed_ingredients())
        errors = [f for f in findings if f.severity is Severity.ERROR]
        assert errors == [], "\n".join(str(f) for f in errors)

    def test_no_warnings_either(self) -> None:
        findings = validate_database(load_seed_ingredients())
        warnings = [f for f in findings if f.severity is Severity.WARNING]
        assert warnings == [], "\n".join(str(f) for f in warnings)

    def test_every_ingredient_has_a_price(self) -> None:
        assert all(item.has_price for item in load_seed_ingredients())

    def test_every_ingredient_has_a_price_source(self) -> None:
        assert all(item.price_source for item in load_seed_ingredients())

    def test_manufacturers_are_a_separate_field(self) -> None:
        store = load_seed_ingredients()
        branded = [i for i in store if i.manufacturer]
        assert len(branded) >= 15
        assert all("(" not in i.name or ")" in i.name for i in branded)

    def test_the_known_brands_survived(self) -> None:
        store = load_seed_ingredients()
        assert {i.manufacturer for i in store} >= {
            "Bauck",
            "Spielberger",
            "Alnatura",
            "dm",
            "dm Bio",
            "Aldi",
            "Rewe",
            "Rapunzel",
            "Grünland",
        }

    def test_flours_are_marked_as_flour(self) -> None:
        store = load_seed_ingredients()
        flours = [i for i in store if i.category is Category.FLOUR]
        assert flours and all(i.is_flour for i in flours)

    def test_breadcrumbs_are_not_flour(self) -> None:
        store = load_seed_ingredients()
        crumbs = store.find_by_name("Altbrot (Paniermehl)")
        assert crumbs is not None
        assert not crumbs.is_flour

    def test_keys_are_unique(self) -> None:
        store = load_seed_ingredients()
        assert len({i.key for i in store}) == len(store)


class TestEnsureUserDatabase:
    def test_creates_from_the_seed_when_nothing_exists(self, tmp_path: Path) -> None:
        ingredients = tmp_path / "ingredients.json"
        recipes = tmp_path / "recipes.json"
        result = ensure_user_database(ingredients, recipes)
        assert result.created_ingredients and result.created_recipes
        assert not result.imported_from_legacy
        assert len(load_ingredients(ingredients)[0]) > 90

    def test_does_not_touch_existing_files(self, tmp_path: Path) -> None:
        ingredients = tmp_path / "ingredients.json"
        recipes = tmp_path / "recipes.json"
        ensure_user_database(ingredients, recipes)
        before = ingredients.read_bytes()
        result = ensure_user_database(ingredients, recipes)
        assert not result.created_ingredients
        assert ingredients.read_bytes() == before

    def test_imports_legacy_files(self, tmp_path: Path) -> None:
        legacy = tmp_path / "alt"
        legacy.mkdir()
        legacy_ingredients_file(
            legacy / "brot_zutaten.json",
            **{
                "Eigenes Spezialmehl": {
                    "name": "Eigenes Spezialmehl",
                    "kategorie": "Mehl",
                    "kalorien": 330,
                    "kohlenhydrate": 60.0,
                    "eiweiss": 10.0,
                    "ballaststoffe": 8.0,
                    "fett": 2.0,
                    "wassergehalt": 13.0,
                }
            },
        )
        (legacy / "brot_rezepte.json").write_text(
            json.dumps(
                {
                    "Brot": {
                        "name": "Brot",
                        "zutaten": [["Eigenes Spezialmehl", 500.0]],
                        "gewicht_gebacken": 450.0,
                    }
                }
            ),
            encoding="utf-8",
        )

        result = ensure_user_database(
            tmp_path / "ingredients.json", tmp_path / "recipes.json", legacy_dir=legacy
        )
        assert result.imported_from_legacy
        store, _ = load_ingredients(tmp_path / "ingredients.json")
        assert store.find_by_name("Eigenes Spezialmehl") is not None


class TestSeedMerge:
    """Regeln der einmaligen Zusammenführung beim Übernehmen von Altdaten."""

    @staticmethod
    def _edited(reference: Ingredient) -> Ingredient:
        """Eine Zutat, die erkennbar von Hand gepflegt wurde."""
        own = reference.copy()
        own.notes = "Etikett selbst abgetippt"
        return own

    def test_unedited_ingredients_are_replaced_wholesale(self) -> None:
        """Vorgabewerte der Altversion werden durch die geprüfte Fassung ersetzt."""
        seed = load_seed_ingredients()
        reference = seed.find_by_name("Kürbiskerne")
        assert reference is not None
        own = reference.copy()
        own.nutrients = Nutrients(
            energy_kcal=559, fat=49.0, carbs=10.7, protein=30.2, fiber=6.0, water=5.5
        )
        own.package_price = 0.0
        own.package_size_g = 0.0
        own.notes = ""
        store = IngredientStore([own])

        notes = merge_seed_into(store)
        result = store.find_by_name("Kürbiskerne")
        assert result is not None
        assert result.nutrients.carbs == pytest.approx(4.7)
        assert result.has_price
        assert any("ersetzt" in note for note in notes)

    def test_the_name_of_the_own_entry_is_kept(self) -> None:
        """Auch beim Ersetzen bleibt die eigene Schreibweise erhalten."""
        seed = load_seed_ingredients()
        reference = seed.find_by_name("Kürbiskerne")
        assert reference is not None
        own = reference.copy(name="Kürbiskerne")
        own.package_price = 0.0
        own.package_size_g = 0.0
        store = IngredientStore([own])
        merge_seed_into(store)
        assert store.find_by_name("Kürbiskerne") is not None

    def test_edited_entries_keep_their_plausible_values(self) -> None:
        """Wer eigene, stimmige Etikettwerte gepflegt hat, behält sie."""
        seed = load_seed_ingredients()
        reference = seed.find_by_name("Weizenmehl Type 405")
        assert reference is not None
        own = self._edited(reference)
        own.nutrients = Nutrients(
            energy_kcal=345, fat=1.1, carbs=71.0, protein=10.5, fiber=3.4, water=13.5
        )
        merge_seed_into(IngredientStore([own]))
        assert own.nutrients.protein == pytest.approx(10.5)

    def test_edited_entries_with_broken_values_are_corrected(self) -> None:
        seed = load_seed_ingredients()
        reference = seed.find_by_name("Kürbiskerne")
        assert reference is not None
        own = self._edited(reference)
        own.nutrients = Nutrients(
            energy_kcal=559, fat=49.0, carbs=10.7, protein=30.2, fiber=6.0, water=5.5
        )
        notes = merge_seed_into(IngredientStore([own]))
        assert own.nutrients.carbs == pytest.approx(4.7)
        assert any("korrigiert" in note for note in notes)

    def test_missing_prices_are_filled_for_edited_entries(self) -> None:
        seed = load_seed_ingredients()
        reference = next(i for i in seed if i.has_price)
        own = self._edited(reference)
        own.package_price = 0.0
        own.package_size_g = 0.0
        notes = merge_seed_into(IngredientStore([own]))
        assert own.has_price
        assert any("Preise" in note for note in notes)

    def test_own_prices_are_never_overwritten(self) -> None:
        seed = load_seed_ingredients()
        reference = next(i for i in seed if i.has_price)
        own = reference.copy()
        own.package_price = 42.0
        own.package_size_g = 100.0
        merge_seed_into(IngredientStore([own]))
        assert own.package_price == pytest.approx(42.0)

    def test_a_price_history_marks_an_entry_as_edited(self) -> None:
        from datetime import datetime, timezone

        from brotrechner.core.models import PriceEntry

        seed = load_seed_ingredients()
        reference = seed.find_by_name("Weizenmehl Type 405")
        assert reference is not None
        own = reference.copy()
        own.package_price = 0.0
        own.package_size_g = 0.0
        own.nutrients = Nutrients(energy_kcal=345, carbs=71.0, protein=10.5, fiber=3.4, water=13.5)
        own.price_history = [PriceEntry(datetime.now(timezone.utc), 1.0, 1000.0)]
        merge_seed_into(IngredientStore([own]))
        assert own.nutrients.protein == pytest.approx(10.5)

    def test_unknown_ingredients_are_left_alone(self) -> None:
        own = Ingredient(name="Ganz eigene Erfindung")
        merge_seed_into(IngredientStore([own]))
        assert not own.has_price

    def test_missing_from_seed(self) -> None:
        assert len(missing_from_seed(IngredientStore())) == len(load_seed_ingredients())


class TestCli:
    def test_info(self, data_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert cli.main(["--data-dir", str(data_dir), "info"]) == 0
        out = capsys.readouterr().out
        assert "Datenverzeichnis" in out
        assert "Zutaten" in out

    def test_check_passes_on_the_seed(
        self, data_dir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert cli.main(["--data-dir", str(data_dir), "check"]) == 0
        assert "0 Fehler" in capsys.readouterr().out

    def test_check_strict_still_passes(self, data_dir: Path) -> None:
        assert cli.main(["--data-dir", str(data_dir), "check", "--strict"]) == 0

    def test_check_reports_errors(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        target = tmp_path / "daten"
        target.mkdir()
        (target / paths.INGREDIENTS_FILE).write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "ingredients": [
                        {
                            "name": "Unmöglich",
                            "fat": 2.0,
                            "saturated_fat": 50.0,
                            "package_price": 1,
                            "package_size_g": 100,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (target / paths.RECIPES_FILE).write_text(
            json.dumps({"schema_version": 2, "recipes": []}), encoding="utf-8"
        )
        assert cli.main(["--data-dir", str(target), "check"]) == 1
        assert "Fehler" in capsys.readouterr().out

    def test_export_csv(self, data_dir: Path, tmp_path: Path) -> None:
        target = tmp_path / "export.csv"
        assert cli.main(["--data-dir", str(data_dir), "export-csv", str(target)]) == 0
        assert target.exists()

    def test_export_to_an_impossible_path(self, data_dir: Path, tmp_path: Path) -> None:
        blocked = tmp_path / "keinordner" / "x.csv"
        assert cli.main(["--data-dir", str(data_dir), "export-csv", str(blocked)]) == 2

    def test_broken_database_gives_exit_code_two(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = tmp_path / "daten"
        target.mkdir()
        (target / paths.INGREDIENTS_FILE).write_text("{kaputt", encoding="utf-8")
        assert cli.main(["--data-dir", str(target), "check"]) == 2
        assert "Fehler" in capsys.readouterr().err

    def test_verbose_flag(self, data_dir: Path) -> None:
        assert cli.main(["--data-dir", str(data_dir), "-v", "info"]) == 0

    def test_version(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc:
            cli.main(["--version"])
        assert exc.value.code == 0
        assert "brotrechner" in capsys.readouterr().out
