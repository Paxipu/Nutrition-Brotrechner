"""Mehlanteil je Zutat: Sauerteig und Vorteige in Teigausbeute und Bäckerprozent.

Früher kannte eine Zutat nur "ist Mehl" oder "ist kein Mehl". Ein Anstellgut
aus gleichen Teilen Mehl und Wasser zählte damit gar nicht zum Mehl, sein
Wasser aber vollständig zum Schüttwasser - samt der Eigenfeuchte des Mehls.
Ein Roggenbrot mit Sauerteig kam so auf TA 191 statt 170.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from brotrechner.core.analysis import (
    FLOUR_MOISTURE_PERCENT,
    ResolvedItem,
    added_water_percent,
    analyze,
)
from brotrechner.core.models import Category, Ingredient
from brotrechner.core.nutrients import Nutrients
from brotrechner.core.validation import Severity, validate_ingredient
from brotrechner.data.repository import IngredientStore, load_ingredients
from brotrechner.data.seed import load_seed_ingredients, load_user_ingredients, merge_seed_into


def rye_flour() -> Ingredient:
    """Roggenmehl mit 13 % Eigenfeuchte."""
    return Ingredient(
        name="Roggenmehl Type 1150",
        category=Category.FLOUR,
        nutrients=Nutrients(
            energy_kcal=321, fat=1.2, carbs=65.0, protein=8.0, fiber=9.0, water=13.0
        ),
        flour_percent=100.0,
    )


def water() -> Ingredient:
    return Ingredient(name="Wasser", category=Category.BASICS, nutrients=Nutrients(water=100.0))


def salt() -> Ingredient:
    return Ingredient(name="Salz", category=Category.BASICS, nutrients=Nutrients(salt=100.0))


def starter(*, flour_percent: float = 50.0) -> Ingredient:
    """Anstellgut TA 200: 100 g Mehl (13 % Feuchte) und 100 g Wasser."""
    return Ingredient(
        name="Sauerteig Anstellgut (Roggen)",
        category=Category.LEAVENING,
        nutrients=Nutrients(
            energy_kcal=149, fat=0.9, carbs=27.5, protein=4.3, fiber=7.0, water=56.5
        ),
        flour_percent=flour_percent,
    )


class TestModel:
    def test_default_is_no_flour(self) -> None:
        assert Ingredient(name="Sesam").flour_percent == 0.0

    @pytest.mark.parametrize(
        ("percent", "is_flour"), [(0.0, False), (50.0, False), (99.9, False), (100.0, True)]
    )
    def test_is_flour_means_pure_flour(self, percent: float, is_flour: bool) -> None:
        assert Ingredient(name="X", flour_percent=percent).is_flour is is_flour

    @pytest.mark.parametrize(("percent", "fraction"), [(-5.0, 0.0), (50.0, 0.5), (140.0, 1.0)])
    def test_the_fraction_is_clamped(self, percent: float, fraction: float) -> None:
        """Ein kaputter Wert darf die Rechnung nicht ins Negative treiben."""
        assert Ingredient(name="X", flour_percent=percent).flour_fraction == fraction

    def test_roundtrip(self) -> None:
        restored = Ingredient.from_dict(starter().to_dict())
        assert restored.flour_percent == 50.0

    def test_older_versions_still_find_their_flag(self) -> None:
        """Version 5.1 liest nur ``is_flour``; reines Mehl muss dort Mehl bleiben."""
        assert rye_flour().to_dict()["is_flour"] is True
        assert starter().to_dict()["is_flour"] is False

    @pytest.mark.parametrize(("flag", "percent"), [(True, 100.0), (False, 0.0)])
    def test_files_of_older_versions_are_read(self, flag: bool, percent: float) -> None:
        data = rye_flour().to_dict()
        del data["flour_percent"]
        data["is_flour"] = flag
        assert Ingredient.from_dict(data).flour_percent == percent

    def test_the_share_wins_over_the_old_flag(self) -> None:
        data = starter().to_dict()
        data["is_flour"] = True
        assert Ingredient.from_dict(data).flour_percent == 50.0

    def test_a_null_share_falls_back_to_the_flag(self) -> None:
        data = rye_flour().to_dict()
        data["flour_percent"] = None
        assert Ingredient.from_dict(data).flour_percent == 100.0

    def test_a_non_numeric_share_is_rejected(self) -> None:
        data = rye_flour().to_dict()
        data["flour_percent"] = "viel"
        with pytest.raises(ValueError, match="Zahlenwert"):
            Ingredient.from_dict(data)

    def test_copy_keeps_the_share(self) -> None:
        assert starter().copy().flour_percent == 50.0


class TestAddedWater:
    """Welcher Teil des Zutatenwassers ist Schüttwasser?"""

    def test_the_moisture_constant(self) -> None:
        assert FLOUR_MOISTURE_PERCENT == 13.0

    def test_pure_flour_adds_none(self) -> None:
        assert added_water_percent(rye_flour()) == 0.0

    def test_moist_flour_still_adds_none(self) -> None:
        wet = rye_flour()
        wet.nutrients = wet.nutrients.with_values(water=15.5)
        assert added_water_percent(wet) == 0.0

    def test_water_adds_everything(self) -> None:
        assert added_water_percent(water()) == 100.0

    def test_milk_adds_its_water(self) -> None:
        milk = Ingredient(name="Milch", nutrients=Nutrients(water=87.5))
        assert added_water_percent(milk) == 87.5

    def test_a_starter_adds_the_water_it_was_made_with(self) -> None:
        """56,5 % Wasser, davon 6,5 Punkte Eigenfeuchte des Mehlanteils."""
        assert added_water_percent(starter()) == pytest.approx(50.0)

    def test_a_dry_preferment_never_goes_negative(self) -> None:
        powder = Ingredient(
            name="Sauerteigpulver", nutrients=Nutrients(water=8.0), flour_percent=90
        )
        assert added_water_percent(powder) == 0.0


class TestSourdoughBread:
    """Das Beispiel aus der Fehlermeldung, nachgerechnet wie in der Backstube."""

    @pytest.fixture
    def bread(self) -> list[ResolvedItem]:
        return [
            ResolvedItem(rye_flour(), 400.0),
            ResolvedItem(starter(), 200.0),
            ResolvedItem(water(), 250.0),
            ResolvedItem(salt(), 10.0),
        ]

    def test_the_flour_of_the_starter_counts(self, bread: list[ResolvedItem]) -> None:
        assert analyze(bread, baked_weight_g=750).flour_mass_g == pytest.approx(500.0)

    def test_only_the_added_water_counts(self, bread: list[ResolvedItem]) -> None:
        assert analyze(bread, baked_weight_g=750).water_mass_g == pytest.approx(350.0)

    def test_dough_yield(self, bread: list[ResolvedItem]) -> None:
        result = analyze(bread, baked_weight_g=750)
        assert result.dough_yield == pytest.approx(170.0)
        assert result.hydration_percent == pytest.approx(70.0)

    def test_salt_relates_to_the_whole_flour(self, bread: list[ResolvedItem]) -> None:
        salt_line = analyze(bread, baked_weight_g=750).lines[3]
        assert salt_line.baker_percent == pytest.approx(2.0)

    def test_a_starter_without_share_behaves_like_before(self) -> None:
        """Wer den Anteil bewusst auf 0 setzt, bekommt das alte Verhalten."""
        result = analyze(
            [ResolvedItem(rye_flour(), 400.0), ResolvedItem(starter(flour_percent=0.0), 200.0)],
            baked_weight_g=500,
        )
        assert result.flour_mass_g == pytest.approx(400.0)
        assert result.water_mass_g == pytest.approx(113.0)

    def test_a_starter_alone_has_its_own_dough_yield(self) -> None:
        result = analyze([ResolvedItem(starter(), 200.0)], baked_weight_g=150)
        assert result.dough_yield == pytest.approx(200.0)

    @given(
        flour_g=st.floats(min_value=50.0, max_value=5000.0),
        water_g=st.floats(min_value=0.0, max_value=5000.0),
        pre_flour_g=st.floats(min_value=10.0, max_value=2000.0),
        pre_water_g=st.floats(min_value=0.0, max_value=2000.0),
    )
    def test_a_preferment_counts_like_its_parts(
        self, flour_g: float, water_g: float, pre_flour_g: float, pre_water_g: float
    ) -> None:
        """Ein Vorteig als eine Zutat ergibt dieselbe TA wie seine Einzelteile.

        Der Vorteig wird genau so zusammengesetzt, wie ihn ein Bäcker ansetzt:
        Mehl mit seiner Eigenfeuchte und Wasser. Ob man dann Mehl und Wasser
        einzeln einträgt oder den fertigen Vorteig mit seinem Mehlanteil, darf
        an Mehlmenge und Schüttwasser nichts ändern.
        """
        mass = pre_flour_g + pre_water_g
        moisture = pre_flour_g * FLOUR_MOISTURE_PERCENT / 100.0
        preferment = Ingredient(
            name="Vorteig",
            nutrients=Nutrients(water=(pre_water_g + moisture) / mass * 100.0),
            flour_percent=pre_flour_g / mass * 100.0,
        )
        whole = analyze(
            [
                ResolvedItem(rye_flour(), flour_g),
                ResolvedItem(water(), water_g),
                ResolvedItem(preferment, mass),
            ],
            baked_weight_g=flour_g,
        )
        parts = analyze(
            [
                ResolvedItem(rye_flour(), flour_g + pre_flour_g),
                ResolvedItem(water(), water_g + pre_water_g),
            ],
            baked_weight_g=flour_g,
        )
        assert whole.flour_mass_g == pytest.approx(parts.flour_mass_g, rel=1e-9)
        assert whole.water_mass_g == pytest.approx(parts.water_mass_g, rel=1e-9, abs=1e-9)
        assert whole.dough_yield == pytest.approx(parts.dough_yield, rel=1e-9)

    @given(percent=st.floats(min_value=-50.0, max_value=200.0), grams=st.floats(0.0, 5000.0))
    def test_the_flour_mass_never_exceeds_the_dough(self, percent: float, grams: float) -> None:
        item = Ingredient(name="X", nutrients=Nutrients(water=40.0), flour_percent=percent)
        result = analyze([ResolvedItem(item, grams)], baked_weight_g=100.0)
        assert 0.0 <= result.flour_mass_g <= grams + 1e-9
        assert result.water_mass_g >= 0.0


class TestHostileValues:
    """Von Hand bearbeitete Dateien können alles enthalten."""

    @given(
        percent=st.floats(allow_nan=True, allow_infinity=True),
        water_percent=st.floats(allow_nan=True, allow_infinity=True),
    )
    def test_the_added_water_stays_within_the_ingredient(
        self, percent: float, water_percent: float
    ) -> None:
        item = Ingredient(name="X", nutrients=Nutrients(water=water_percent), flour_percent=percent)
        added = added_water_percent(item)
        assert 0.0 <= added <= 100.0
        assert 0.0 <= item.flour_fraction <= 1.0

    @pytest.mark.parametrize("raw", ["NaN", "Infinity", "-Infinity"])
    def test_non_finite_shares_are_reported(self, raw: str) -> None:
        data = json.loads(f'{{"name": "X", "flour_percent": {raw}}}')
        item = Ingredient.from_dict(data)
        assert any(f.code == "flour_range" for f in validate_ingredient(item))


class TestValidation:
    @pytest.mark.parametrize("percent", [-0.1, 100.1, 250.0])
    def test_a_share_outside_the_range_is_an_error(self, percent: float) -> None:
        findings = validate_ingredient(Ingredient(name="X", flour_percent=percent))
        codes = {f.code: f for f in findings}
        assert "flour_range" in codes
        assert codes["flour_range"].severity is Severity.ERROR

    @pytest.mark.parametrize("percent", [0.0, 50.0, 100.0])
    def test_shares_inside_the_range_are_fine(self, percent: float) -> None:
        findings = validate_ingredient(Ingredient(name="X", flour_percent=percent))
        assert all(f.code != "flour_range" for f in findings)


class TestSeed:
    def test_the_starter_is_half_flour(self) -> None:
        item = load_seed_ingredients().find_by_name("Sauerteig Anstellgut (Roggen)")
        assert item is not None
        assert item.flour_percent == 50.0

    def test_lievito_madre_is_two_thirds_flour(self) -> None:
        item = load_seed_ingredients().find_by_name("Lievito Madre (Weizensauer)")
        assert item is not None
        assert item.flour_percent == pytest.approx(66.7)

    def test_the_starter_adds_the_water_of_its_recipe(self) -> None:
        item = load_seed_ingredients().find_by_name("Sauerteig Anstellgut (Roggen)")
        assert item is not None
        assert added_water_percent(item) == pytest.approx(50.0)

    def test_every_seed_flour_is_pure_flour(self) -> None:
        flours = [i for i in load_seed_ingredients() if i.category is Category.FLOUR]
        assert flours
        assert all(i.flour_percent == 100.0 for i in flours)


def _write_v2(path: Path, *entries: dict[str, object]) -> Path:
    """Schreibt eine Zutatendatei, wie sie Version 5.1 hinterlassen hat."""
    payload = {"schema_version": 2, "ingredients": list(entries)}
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _as_written_by_5_1(item: Ingredient) -> dict[str, object]:
    data = item.to_dict()
    del data["flour_percent"]
    return data


class TestUpgradeOfOlderFiles:
    """Nutzerdateien aus Version 5.1 kennen keinen Mehlanteil."""

    def test_a_known_preferment_gets_the_share_of_the_seed(self, tmp_path: Path) -> None:
        path = _write_v2(
            tmp_path / "ingredients.json",
            _as_written_by_5_1(starter(flour_percent=0.0)),
            _as_written_by_5_1(rye_flour()),
        )
        store, result = load_user_ingredients(path)
        item = store.find_by_name("Sauerteig Anstellgut (Roggen)")
        assert item is not None
        assert item.flour_percent == 50.0
        assert any("Mehlanteil" in note for note in result.upgrades)

    def test_the_upgrade_is_written_back(self, tmp_path: Path) -> None:
        path = _write_v2(
            tmp_path / "ingredients.json", _as_written_by_5_1(starter(flour_percent=0))
        )
        load_user_ingredients(path)
        again, _ = load_ingredients(path)
        item = again.find_by_name("Sauerteig Anstellgut (Roggen)")
        assert item is not None
        assert item.flour_percent == 50.0

    def test_an_explicit_share_is_never_touched(self, tmp_path: Path) -> None:
        """Wer den Anteil selbst auf 0 gesetzt hat, meint 0."""
        path = _write_v2(tmp_path / "ingredients.json", starter(flour_percent=0.0).to_dict())
        store, result = load_user_ingredients(path)
        item = store.find_by_name("Sauerteig Anstellgut (Roggen)")
        assert item is not None
        assert item.flour_percent == 0.0
        assert not result.upgrades

    def test_own_ingredients_without_a_seed_entry_stay_as_they_are(self, tmp_path: Path) -> None:
        own = Ingredient(name="Mein Vorteig", nutrients=Nutrients(water=50.0))
        path = _write_v2(tmp_path / "ingredients.json", _as_written_by_5_1(own))
        store, _ = load_user_ingredients(path)
        item = store.find_by_name("Mein Vorteig")
        assert item is not None
        assert item.flour_percent == 0.0

    def test_pure_flour_keeps_its_flag(self, tmp_path: Path) -> None:
        path = _write_v2(tmp_path / "ingredients.json", _as_written_by_5_1(rye_flour()))
        store, _ = load_user_ingredients(path)
        item = store.find_by_name("Roggenmehl Type 1150")
        assert item is not None
        assert item.flour_percent == 100.0

    def test_a_missing_file_gives_an_empty_store(self, tmp_path: Path) -> None:
        store, result = load_user_ingredients(tmp_path / "fehlt.json")
        assert len(store) == 0
        assert not result.upgrades

    def test_a_failed_write_back_still_loads_the_upgrade(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Ein schreibgeschütztes Verzeichnis darf das Laden nicht verhindern."""
        from brotrechner.data import seed as seed_module
        from brotrechner.data.repository import RepositoryError

        def refuse(*_args: object) -> None:
            raise RepositoryError("schreibgeschützt")

        path = _write_v2(
            tmp_path / "ingredients.json", _as_written_by_5_1(starter(flour_percent=0))
        )
        monkeypatch.setattr(seed_module, "save_ingredients", refuse)
        store, result = load_user_ingredients(path)
        item = store.find_by_name("Sauerteig Anstellgut (Roggen)")
        assert item is not None
        assert item.flour_percent == 50.0
        assert any("nicht gespeichert" in note for note in result.upgrades)

    def test_legacy_imports_adopt_the_share_for_edited_starters(self) -> None:
        """Beim Übernehmen aus dem Altprogramm gilt dieselbe Regel."""
        own = starter(flour_percent=0.0)
        own.notes = "selbst gepflegt"
        store = IngredientStore([own])
        merge_seed_into(store)
        item = store.find_by_name("Sauerteig Anstellgut (Roggen)")
        assert item is not None
        assert item.flour_percent == 50.0


class TestCsv:
    def test_the_share_has_its_own_column(self, tmp_path: Path) -> None:
        import csv

        from brotrechner.export.table import INGREDIENT_COLUMNS, write_ingredients_csv

        target = tmp_path / "zutaten.csv"
        write_ingredients_csv(target, [starter()])
        with target.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle, delimiter=";"))
        column = list(INGREDIENT_COLUMNS).index("Mehlanteil (%)")
        assert rows[0][column] == "Mehlanteil (%)"
        assert rows[1][column] == "50,0"


@pytest.mark.gui
class TestIngredientDialog:
    @pytest.fixture
    def tokens(self, qapp: object) -> object:
        del qapp
        from brotrechner.gui.theme import ThemeMode, resolve_tokens

        return resolve_tokens(ThemeMode.LIGHT)

    def test_the_share_is_shown_in_percent(self, tokens: object) -> None:
        from brotrechner.gui.dialogs.ingredient_dialog import IngredientDialog

        dialog = IngredientDialog(tokens, ingredient=starter())  # type: ignore[arg-type]
        assert dialog.spin_flour.value() == pytest.approx(50.0)
        dialog.close()

    def test_an_edited_share_is_saved(self, tokens: object) -> None:
        from brotrechner.gui.dialogs.ingredient_dialog import IngredientDialog

        dialog = IngredientDialog(tokens, ingredient=starter())  # type: ignore[arg-type]
        dialog.spin_flour.setValue(66.7)
        assert dialog.result_ingredient().flour_percent == pytest.approx(66.7)
        dialog.close()

    @pytest.mark.parametrize(
        ("percent", "expected"),
        [(0.0, "zählt nicht als Mehl"), (100.0, "zählt vollständig"), (50.0, "TA 200")],
    )
    def test_the_hint_explains_the_share(
        self, tokens: object, percent: float, expected: str
    ) -> None:
        from brotrechner.gui.dialogs.ingredient_dialog import IngredientDialog

        dialog = IngredientDialog(tokens)  # type: ignore[arg-type]
        dialog.spin_flour.setValue(percent)
        assert expected in dialog.lbl_flour_hint.text()
        dialog.close()


@pytest.mark.gui
class TestStartupMessage:
    def test_the_upgrade_is_announced_once(
        self,
        qapp: object,
        data_dir: Path,
        dialogs: dict[str, object],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        del qapp, dialogs
        from PySide6.QtWidgets import QMessageBox

        from brotrechner.gui.main_window import MainWindow

        _write_v2(data_dir / "ingredients.json", _as_written_by_5_1(starter(flour_percent=0)))
        shown: list[str] = []
        monkeypatch.setattr(
            QMessageBox, "information", lambda _parent, title, *_rest: shown.append(title)
        )

        first = MainWindow(data_dir=data_dir)
        first.close()
        second = MainWindow(data_dir=data_dir)
        second.close()

        assert shown.count("Zutatendatenbank ergänzt") == 1
