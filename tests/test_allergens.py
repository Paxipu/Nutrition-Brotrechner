"""Allergene nach Anhang II und die Bezeichnung im Zutatenverzeichnis.

Für den Verkauf müssen Allergene im Zutatenverzeichnis hervorgehoben sein
(Artikel 21 VO (EU) Nr. 1169/2011). Dafür braucht jede Zutat zwei Angaben:
welche Allergene sie enthält, und unter welcher Bezeichnung sie im Verzeichnis
steht - mit dem Allergen darin in ``*Sternchen*``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from brotrechner.core.allergens import ALLERGEN_GROUPS, Allergen, parse_allergens
from brotrechner.core.labeling import Run, has_emphasis, list_runs, parse_emphasis, plain_text
from brotrechner.core.models import Category, Ingredient
from brotrechner.core.nutrients import Nutrients
from brotrechner.core.validation import Severity, validate_ingredient
from brotrechner.data.repository import IngredientStore, load_ingredients
from brotrechner.data.seed import load_seed_ingredients, load_user_ingredients, merge_seed_into


def wheat_flour(**changes: object) -> Ingredient:
    values: dict[str, object] = {
        "name": "Weizenmehl Type 550",
        "category": Category.FLOUR,
        "nutrients": Nutrients(
            energy_kcal=341, fat=1.0, carbs=70.0, protein=11.0, fiber=4.0, water=13.5
        ),
        "flour_percent": 100.0,
        "label_name": "*Weizen*mehl Type 550",
        "allergens": frozenset({Allergen.WHEAT}),
        "package_price": 0.55,
        "package_size_g": 1000,
    }
    values.update(changes)
    return Ingredient(**values)  # type: ignore[arg-type]


class TestAllergen:
    def test_the_fourteen_groups_of_annex_ii(self) -> None:
        assert len(ALLERGEN_GROUPS) == 14
        assert ALLERGEN_GROUPS[0][0] == "Glutenhaltiges Getreide"
        assert ALLERGEN_GROUPS[7][0] == "Schalenfrüchte"

    def test_every_member_belongs_to_exactly_one_group(self) -> None:
        members = [a for _, group in ALLERGEN_GROUPS for a in group]
        assert sorted(members, key=lambda a: a.value) == sorted(Allergen, key=lambda a: a.value)

    def test_cereals_and_nuts_are_named_individually(self) -> None:
        """Eine "Enthält"-Angabe muss das Getreide bzw. die Nuss nennen."""
        assert Allergen.WHEAT.label == "Weizen"
        assert Allergen.SPELT.label == "Dinkel"
        assert Allergen.WALNUTS.label == "Walnüsse"
        assert Allergen.WHEAT.group == "Glutenhaltiges Getreide"
        assert Allergen.MILK.group == "Milch"

    def test_the_order_follows_the_annex(self) -> None:
        order = list(Allergen)
        assert (
            order.index(Allergen.WHEAT) < order.index(Allergen.MILK) < order.index(Allergen.LUPIN)
        )

    def test_is_not_a_str_subclass(self) -> None:
        """PySide6 würde str-Enums in QVariant zu nackten Zeichenketten machen."""
        assert not issubclass(Allergen, str)

    def test_parsing(self) -> None:
        assert parse_allergens(["milk", "wheat"]) == frozenset({Allergen.MILK, Allergen.WHEAT})

    def test_parsing_ignores_unknown_keys(self) -> None:
        """Eine spätere Programmfassung darf neue Schlüssel schreiben."""
        assert parse_allergens(["wheat", "unbekannt", 3]) == frozenset({Allergen.WHEAT})

    @pytest.mark.parametrize("raw", [None, "wheat", 5, {"a": 1}])
    def test_anything_but_a_list_means_not_recorded(self, raw: object) -> None:
        assert parse_allergens(raw) is None


class TestEmphasis:
    def test_a_single_emphasis(self) -> None:
        assert parse_emphasis("*Weizen*mehl") == (Run("Weizen", True), Run("mehl", False))

    def test_several_emphases(self) -> None:
        runs = parse_emphasis("Sauerteig (*Roggen*mehl, Wasser), *Sesam*")
        assert [r.text for r in runs if r.bold] == ["Roggen", "Sesam"]

    def test_without_markup(self) -> None:
        assert parse_emphasis("Wasser") == (Run("Wasser", False),)
        assert not has_emphasis("Wasser")

    def test_an_unmatched_star_stays_visible(self) -> None:
        assert plain_text("Salz *jodiert") == "Salz *jodiert"

    def test_plain_text_drops_the_markup(self) -> None:
        assert plain_text("*Weizen*mehl Type 550") == "Weizenmehl Type 550"

    def test_empty(self) -> None:
        assert parse_emphasis("") == ()
        assert not has_emphasis("**")

    @given(st.text(alphabet=st.sampled_from("ab *(),"), max_size=40))
    def test_every_character_but_the_stars_survives(self, text: str) -> None:
        """Nichts außer Markierungssternchen geht verloren, die Reihenfolge bleibt."""
        joined = "".join(r.text for r in parse_emphasis(text))
        assert joined.replace("*", "") == text.replace("*", "")

    @given(st.text(alphabet=st.sampled_from("ab *(),"), max_size=40))
    def test_bold_text_never_contains_a_star(self, text: str) -> None:
        assert all("*" not in r.text for r in parse_emphasis(text) if r.bold)

    @given(st.text(max_size=40))
    def test_runs_are_never_empty(self, text: str) -> None:
        assert all(r.text for r in parse_emphasis(text))


class TestListRuns:
    def test_the_marked_part_is_bold(self) -> None:
        runs = list_runs("*Weizen*mehl", {Allergen.WHEAT})
        assert runs == (Run("Weizen", True), Run("mehl", False))

    def test_an_unmarked_allergen_makes_the_whole_name_bold(self) -> None:
        assert list_runs("Joghurt", {Allergen.MILK}) == (Run("Joghurt", True),)

    @pytest.mark.parametrize("allergens", [None, set()])
    def test_without_allergens_nothing_is_added(self, allergens: set[Allergen] | None) -> None:
        assert list_runs("Wasser", allergens) == (Run("Wasser", False),)

    def test_an_empty_label_stays_empty(self) -> None:
        assert list_runs("", {Allergen.MILK}) == ()


class TestIngredientFields:
    def test_allergens_are_not_recorded_by_default(self) -> None:
        """Nicht erfasst ist etwas anderes als allergenfrei."""
        assert Ingredient(name="X").allergens is None

    def test_roundtrip(self) -> None:
        restored = Ingredient.from_dict(wheat_flour().to_dict())
        assert restored.allergens == frozenset({Allergen.WHEAT})
        assert restored.label_name == "*Weizen*mehl Type 550"

    def test_none_is_written_as_null(self) -> None:
        assert wheat_flour(allergens=None).to_dict()["allergens"] is None

    def test_no_allergens_is_an_empty_list(self) -> None:
        data = wheat_flour(allergens=frozenset()).to_dict()
        assert data["allergens"] == []
        assert Ingredient.from_dict(data).allergens == frozenset()

    def test_the_list_is_written_in_annex_order(self) -> None:
        item = wheat_flour(allergens=frozenset({Allergen.SESAME, Allergen.MILK, Allergen.RYE}))
        assert item.to_dict()["allergens"] == ["rye", "milk", "sesame"]

    def test_older_files_mean_not_recorded(self) -> None:
        data = wheat_flour().to_dict()
        del data["allergens"], data["label_name"]
        restored = Ingredient.from_dict(data)
        assert restored.allergens is None
        assert restored.label_name == ""

    def test_the_list_name_falls_back_to_the_name(self) -> None:
        assert wheat_flour(label_name="").list_name == "Weizenmehl Type 550"
        assert wheat_flour().list_name == "*Weizen*mehl Type 550"

    def test_copy_keeps_both(self) -> None:
        copy = wheat_flour().copy()
        assert copy.allergens == frozenset({Allergen.WHEAT})
        assert copy.label_name == "*Weizen*mehl Type 550"


def codes(item: Ingredient) -> dict[str, Severity]:
    return {f.code: f.severity for f in validate_ingredient(item)}


class TestValidation:
    def test_a_clean_flour(self) -> None:
        assert codes(wheat_flour()) == {}

    def test_an_unmatched_star_is_an_error(self) -> None:
        assert codes(wheat_flour(label_name="*Weizen mehl"))["label_markup"] is Severity.ERROR

    def test_an_allergen_without_emphasis_is_a_warning(self) -> None:
        found = codes(wheat_flour(label_name="Weizenmehl Type 550"))
        assert found["allergen_emphasis"] is Severity.WARNING

    def test_an_allergen_without_list_name_is_a_warning(self) -> None:
        assert codes(wheat_flour(label_name=""))["allergen_emphasis"] is Severity.WARNING

    def test_emphasis_without_an_allergen_is_a_warning(self) -> None:
        found = codes(wheat_flour(allergens=frozenset()))
        assert found["emphasis_without_allergen"] is Severity.WARNING

    def test_unrecorded_allergens_are_a_hint(self) -> None:
        found = codes(wheat_flour(allergens=None, label_name=""))
        assert found["allergens_unknown"] is Severity.INFO


class TestSeed:
    @pytest.mark.parametrize(
        ("name", "manufacturer", "expected"),
        [
            ("Weizenmehl Type 550", "", {Allergen.WHEAT}),
            ("Roggenvollkornmehl", "Bauck", {Allergen.RYE}),
            ("Dinkelvollkornmehl", "dm Bio", {Allergen.SPELT}),
            ("Haferflocken", "", {Allergen.OATS}),
            ("Backmalz (inaktiv)", "", {Allergen.BARLEY}),
            ("Sesam", "", {Allergen.SESAME}),
            ("Walnüsse", "", {Allergen.WALNUTS}),
            ("Butter", "", {Allergen.MILK}),
            ("Sojamehl", "", {Allergen.SOY}),
            ("Ei", "", {Allergen.EGGS}),
            ("Sauerteig Anstellgut (Roggen)", "", {Allergen.RYE}),
            ("Buchweizenmehl", "", set()),
            ("Wasser", "", set()),
        ],
    )
    def test_allergens(self, name: str, manufacturer: str, expected: set[Allergen]) -> None:
        item = load_seed_ingredients().find_by_name(name, manufacturer)
        assert item is not None
        assert item.allergens == frozenset(expected)

    @pytest.mark.parametrize("name", ["Margarine", "Essig", "Rosinen"])
    def test_uncertain_products_stay_unrecorded(self, name: str) -> None:
        """Hier hängt es vom gekauften Produkt ab - also Packung prüfen."""
        item = load_seed_ingredients().find_by_name(name)
        assert item is not None
        assert item.allergens is None

    def test_every_seed_ingredient_has_a_list_name(self) -> None:
        assert all(item.label_name for item in load_seed_ingredients())

    def test_the_starter_names_its_parts(self) -> None:
        item = load_seed_ingredients().find_by_name("Sauerteig Anstellgut (Roggen)")
        assert item is not None
        assert plain_text(item.label_name) == "Roggensauerteig (Roggenvollkornmehl, Wasser)"

    def test_salt_is_declared_as_iodised(self) -> None:
        item = load_seed_ingredients().find_by_name("Salz")
        assert item is not None
        assert item.label_name == "Jodsalz"


def _write_v2(path: Path, *entries: dict[str, object]) -> Path:
    path.write_text(
        json.dumps({"schema_version": 2, "ingredients": list(entries)}, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def _as_written_by_5_1(item: Ingredient) -> dict[str, object]:
    data = item.to_dict()
    for key in ("allergens", "label_name", "flour_percent"):
        data.pop(key, None)
    return data


class TestUpgradeOfOlderFiles:
    def test_known_ingredients_get_allergens_and_list_name(self, tmp_path: Path) -> None:
        path = _write_v2(tmp_path / "z.json", _as_written_by_5_1(wheat_flour()))
        store, result = load_user_ingredients(path)
        item = store.find_by_name("Weizenmehl Type 550")
        assert item is not None
        assert item.allergens == frozenset({Allergen.WHEAT})
        assert item.label_name == "*Weizen*mehl Type 550"
        assert any("Allergene" in note for note in result.upgrades)

    def test_it_is_written_back(self, tmp_path: Path) -> None:
        path = _write_v2(tmp_path / "z.json", _as_written_by_5_1(wheat_flour()))
        load_user_ingredients(path)
        again, _ = load_ingredients(path)
        item = again.find_by_name("Weizenmehl Type 550")
        assert item is not None
        assert item.allergens == frozenset({Allergen.WHEAT})

    def test_recorded_allergens_are_never_touched(self, tmp_path: Path) -> None:
        own = wheat_flour(allergens=frozenset(), label_name="Mehl")
        path = _write_v2(tmp_path / "z.json", own.to_dict())
        store, result = load_user_ingredients(path)
        item = store.find_by_name("Weizenmehl Type 550")
        assert item is not None
        assert item.allergens == frozenset()
        assert item.label_name == "Mehl"
        assert not result.upgrades

    def test_own_ingredients_stay_unrecorded(self, tmp_path: Path) -> None:
        own = Ingredient(name="Meine Spezialmischung")
        path = _write_v2(tmp_path / "z.json", _as_written_by_5_1(own))
        store, _ = load_user_ingredients(path)
        item = store.find_by_name("Meine Spezialmischung")
        assert item is not None
        assert item.allergens is None

    def test_legacy_imports_get_them_too(self) -> None:
        own = wheat_flour(allergens=None, label_name="", notes="selbst gepflegt")
        store = IngredientStore([own])
        merge_seed_into(store)
        item = store.find_by_name("Weizenmehl Type 550")
        assert item is not None
        assert item.allergens == frozenset({Allergen.WHEAT})


class TestCsv:
    def test_allergens_and_list_name_have_columns(self, tmp_path: Path) -> None:
        import csv

        from brotrechner.export.table import INGREDIENT_COLUMNS, write_ingredients_csv

        target = tmp_path / "z.csv"
        write_ingredients_csv(target, [wheat_flour(), wheat_flour(name="X", allergens=None)])
        with target.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle, delimiter=";"))
        allergens = list(INGREDIENT_COLUMNS).index("Allergene")
        list_name = list(INGREDIENT_COLUMNS).index("Bezeichnung im Zutatenverzeichnis")
        by_name = {row[0]: row for row in rows[1:]}
        assert by_name["Weizenmehl Type 550"][allergens] == "Weizen"
        assert by_name["Weizenmehl Type 550"][list_name] == "*Weizen*mehl Type 550"
        assert by_name["X"][allergens] == "nicht erfasst"


@pytest.mark.gui
class TestIngredientDialog:
    @pytest.fixture
    def tokens(self, qapp: object) -> object:
        del qapp
        from brotrechner.gui.theme import ThemeMode, resolve_tokens

        return resolve_tokens(ThemeMode.LIGHT)

    def _dialog(self, tokens: object, **kwargs: object) -> object:
        from brotrechner.gui.dialogs.ingredient_dialog import IngredientDialog

        return IngredientDialog(tokens, **kwargs)  # type: ignore[arg-type]

    def test_a_new_ingredient_starts_unrecorded(self, tokens: object) -> None:
        dialog = self._dialog(tokens)
        dialog.txt_name.setText("Neu")  # type: ignore[attr-defined]
        assert not dialog.chk_allergens_checked.isChecked()  # type: ignore[attr-defined]
        assert dialog.result_ingredient().allergens is None  # type: ignore[attr-defined]

    def test_ticking_an_allergen_marks_them_as_checked(self, tokens: object) -> None:
        dialog = self._dialog(tokens)
        dialog.txt_name.setText("Neu")  # type: ignore[attr-defined]
        dialog.allergen_boxes[Allergen.MILK].setChecked(True)  # type: ignore[attr-defined]
        assert dialog.chk_allergens_checked.isChecked()  # type: ignore[attr-defined]
        assert dialog.result_ingredient().allergens == frozenset({Allergen.MILK})  # type: ignore[attr-defined]

    def test_checked_without_any_allergen_means_none(self, tokens: object) -> None:
        dialog = self._dialog(tokens)
        dialog.txt_name.setText("Wasser")  # type: ignore[attr-defined]
        dialog.chk_allergens_checked.setChecked(True)  # type: ignore[attr-defined]
        assert dialog.result_ingredient().allergens == frozenset()  # type: ignore[attr-defined]

    def test_editing_shows_the_stored_values(self, tokens: object) -> None:
        dialog = self._dialog(tokens, ingredient=wheat_flour())
        assert dialog.allergen_boxes[Allergen.WHEAT].isChecked()  # type: ignore[attr-defined]
        assert dialog.txt_label_name.text() == "*Weizen*mehl Type 550"  # type: ignore[attr-defined]
        assert "<b>Weizen</b>mehl" in dialog.lbl_label_preview.text()  # type: ignore[attr-defined]

    def test_edited_values_are_saved(self, tokens: object) -> None:
        dialog = self._dialog(tokens, ingredient=wheat_flour())
        dialog.txt_label_name.setText("*Weizen*mehl")  # type: ignore[attr-defined]
        dialog.allergen_boxes[Allergen.SESAME].setChecked(True)  # type: ignore[attr-defined]
        result = dialog.result_ingredient()  # type: ignore[attr-defined]
        assert result.label_name == "*Weizen*mehl"
        assert result.allergens == frozenset({Allergen.WHEAT, Allergen.SESAME})

    def test_unchecking_forgets_the_allergens(self, tokens: object) -> None:
        dialog = self._dialog(tokens, ingredient=wheat_flour())
        dialog.chk_allergens_checked.setChecked(False)  # type: ignore[attr-defined]
        assert dialog.result_ingredient().allergens is None  # type: ignore[attr-defined]


@pytest.mark.gui
class TestIngredientPages:
    def test_the_detail_view_shows_list_name_and_allergens(self, qapp: object) -> None:
        del qapp
        from brotrechner.gui.pages.ingredients import _detail_html
        from brotrechner.gui.theme import ThemeMode, resolve_tokens

        html = _detail_html(wheat_flour(), resolve_tokens(ThemeMode.LIGHT))
        assert "<b>Weizen</b>mehl Type 550" in html
        assert "Allergene: Weizen" in html

    def test_unrecorded_allergens_are_named_as_such(self, qapp: object) -> None:
        del qapp
        from brotrechner.gui.pages.ingredients import _detail_html
        from brotrechner.gui.theme import ThemeMode, resolve_tokens

        html = _detail_html(wheat_flour(allergens=None), resolve_tokens(ThemeMode.LIGHT))
        assert "Allergene: nicht erfasst" in html

    def test_the_table_tooltip_names_the_allergens(self) -> None:
        from brotrechner.gui.models.ingredient_model import _tooltip

        assert "Allergene: Weizen" in _tooltip(wheat_flour(), None)
