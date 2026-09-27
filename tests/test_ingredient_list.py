"""Zutatenverzeichnis nach LMIV: Reihenfolge, Wasser, Hervorhebung, "Enthält".

Bisher stand auf dem Etikett der Zutatenname aus der Datenbank, sortiert nach
der Menge im Teig, ohne jede Hervorhebung. Für den Verkauf gelten:

* absteigende Reihenfolge nach Gewicht (Artikel 18),
* zugefügtes Wasser nach seinem Anteil im *fertigen* Erzeugnis - Gewicht des
  Brots abzüglich aller anderen Zutaten (Anhang VII Teil A Nr. 1),
* Allergene hervorgehoben (Artikel 21), ohne Verzeichnis als "Enthält: ...".
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from brotrechner.core.allergens import Allergen
from brotrechner.core.analysis import ResolvedItem, analyze
from brotrechner.core.labeling import build_ingredient_list, contains_statement
from brotrechner.core.models import Category, Ingredient
from brotrechner.core.nutrients import Nutrients


def flour(manufacturer: str = "") -> Ingredient:
    return Ingredient(
        name="Weizenmehl Type 550",
        manufacturer=manufacturer,
        category=Category.FLOUR,
        nutrients=Nutrients(energy_kcal=341, carbs=70.0, protein=11.0, fiber=4.0, water=13.5),
        flour_percent=100.0,
        label_name="*Weizen*mehl Type 550",
        allergens=frozenset({Allergen.WHEAT}),
    )


def rye() -> Ingredient:
    return Ingredient(
        name="Roggenvollkornmehl",
        category=Category.FLOUR,
        nutrients=Nutrients(energy_kcal=317, carbs=60.0, protein=8.5, fiber=14.0, water=13.0),
        flour_percent=100.0,
        label_name="*Roggen*vollkornmehl",
        allergens=frozenset({Allergen.RYE}),
    )


def water() -> Ingredient:
    return Ingredient(name="Wasser", nutrients=Nutrients(water=100.0), allergens=frozenset())


def salt() -> Ingredient:
    return Ingredient(
        name="Salz", nutrients=Nutrients(salt=100.0), label_name="Jodsalz", allergens=frozenset()
    )


def yoghurt(**changes: object) -> Ingredient:
    values: dict[str, object] = {
        "name": "Joghurt",
        "nutrients": Nutrients(energy_kcal=65, fat=3.5, carbs=4.0, protein=3.5, water=87.0),
        "allergens": frozenset({Allergen.MILK}),
    }
    values.update(changes)
    return Ingredient(**values)  # type: ignore[arg-type]


def listing(items: list[tuple[Ingredient, float]], baked: float):  # type: ignore[no-untyped-def]
    result = analyze([ResolvedItem(i, g) for i, g in items], baked_weight_g=baked)
    return build_ingredient_list(result.lines, baked_weight_g=baked)


class TestOrder:
    def test_a_simple_bread(self) -> None:
        result = listing([(flour(), 500), (water(), 350), (salt(), 10)], baked=750)
        assert [e.markup for e in result.entries] == ["*Weizen*mehl Type 550", "Wasser", "Jodsalz"]

    def test_water_counts_with_what_is_left_in_the_bread(self) -> None:
        """450 g Wasser im Teig, aber nur 290 g im Brot - also nach dem Mehl."""
        result = listing([(flour(), 400), (water(), 450), (salt(), 10)], baked=700)
        assert [e.markup for e in result.entries][:2] == ["*Weizen*mehl Type 550", "Wasser"]
        water_entry = result.entries[1]
        assert water_entry.weight_g == pytest.approx(290.0)

    def test_water_that_has_evaporated_is_not_listed(self) -> None:
        """Knäckebrot: Das zugefügte Wasser ist beim Backen ganz verdunstet."""
        result = listing([(flour(), 400), (water(), 300), (salt(), 5)], baked=400)
        assert "Wasser" not in [e.markup for e in result.entries]

    def test_other_ingredients_keep_their_dough_weight(self) -> None:
        result = listing([(flour(), 300), (rye(), 400), (water(), 450)], baked=900)
        assert [e.markup for e in result.entries][:2] == [
            "*Roggen*vollkornmehl",
            "*Weizen*mehl Type 550",
        ]


class TestMerging:
    def test_the_same_list_name_is_listed_once(self) -> None:
        """Drei Mühlen im Teig machen noch keine drei Zutaten auf dem Etikett."""
        result = listing([(flour(), 300), (flour("Aldi"), 300), (water(), 400)], baked=850)
        names = [e.markup for e in result.entries]
        assert names.count("*Weizen*mehl Type 550") == 1
        assert result.entries[0].weight_g == pytest.approx(600.0)

    def test_the_name_is_used_without_a_list_name(self) -> None:
        seeds = Ingredient(
            name="Sonnenblumenkerne",
            nutrients=Nutrients(fat=50.0, water=5.0),
            allergens=frozenset(),
        )
        result = listing([(flour(), 500), (seeds, 50)], baked=500)
        assert result.entries[1].markup == "Sonnenblumenkerne"


class TestEmphasis:
    def test_an_unmarked_allergen_is_emphasised_as_a_whole(self) -> None:
        result = listing([(yoghurt(), 200), (flour(), 500)], baked=620)
        assert "*Joghurt*" in [e.markup for e in result.entries]

    def test_ingredients_without_allergens_stay_plain(self) -> None:
        result = listing([(flour(), 500), (water(), 350)], baked=750)
        assert result.entries[1].markup == "Wasser"

    def test_the_allergens_of_the_recipe(self) -> None:
        result = listing([(flour(), 500), (rye(), 100), (yoghurt(), 100)], baked=650)
        assert result.allergens == frozenset({Allergen.WHEAT, Allergen.RYE, Allergen.MILK})

    def test_unrecorded_ingredients_are_named(self) -> None:
        unknown = Ingredient(name="Margarine", nutrients=Nutrients(fat=80.0, water=16.0))
        result = listing([(flour(), 500), (unknown, 50)], baked=500)
        assert result.unknown == ("Margarine",)
        assert result.entries[1].markup == "Margarine"


class TestContainsStatement:
    def test_in_annex_order(self) -> None:
        text = contains_statement(frozenset({Allergen.MILK, Allergen.RYE, Allergen.WHEAT}))
        assert text == "Enthält: Weizen, Roggen, Milch"

    def test_nothing_to_state(self) -> None:
        assert contains_statement(frozenset()) == ""


class TestPlainText:
    def test_the_list_as_plain_text(self) -> None:
        result = listing([(flour(), 500), (water(), 350), (salt(), 10)], baked=750)
        assert result.plain_text() == "Weizenmehl Type 550, Wasser, Jodsalz"


class TestProperties:
    @given(
        flour_g=st.floats(min_value=1.0, max_value=2000.0),
        rye_g=st.floats(min_value=1.0, max_value=2000.0),
        water_g=st.floats(min_value=1.0, max_value=2000.0),
        loss=st.floats(min_value=0.0, max_value=0.5),
    )
    def test_the_list_is_sorted_by_weight(
        self, flour_g: float, rye_g: float, water_g: float, loss: float
    ) -> None:
        baked = (flour_g + rye_g + water_g) * (1.0 - loss)
        result = listing([(flour(), flour_g), (rye(), rye_g), (water(), water_g)], baked=baked)
        weights = [e.weight_g for e in result.entries]
        assert weights == sorted(weights, reverse=True)
        assert all(w > 0 for w in weights)


# ── Etikett ────────────────────────────────────────────────────────────────


def _draw() -> object:
    from PIL import Image, ImageDraw

    return ImageDraw.Draw(Image.new("RGB", (10, 10)))


def _fonts() -> tuple[object, object]:
    """Normale und fette Schrift in 24 Pixel - einmal geladen, sonst ist Hypothesis langsam."""
    from brotrechner.export.fonts import load_font_set

    font_set = load_font_set()
    return font_set.get(24), font_set.get(24, bold=True)


FONTS = _fonts()


class TestRichTextWrapping:
    def test_bold_parts_keep_their_style(self) -> None:
        from brotrechner.core.labeling import Run
        from brotrechner.export.label import _wrap_runs

        lines = _wrap_runs(_draw(), [Run("Weizen", True), Run("mehl, Wasser")], *FONTS, 10_000)
        assert lines == [[[("Weizen", True), ("mehl,", False)], [("Wasser", False)]]]

    @given(
        words=st.lists(
            st.tuples(st.text(alphabet="abcdefgh", min_size=1, max_size=12), st.booleans()),
            min_size=1,
            max_size=30,
        ),
        width=st.integers(min_value=40, max_value=600),
    )
    def test_no_line_is_wider_than_allowed_and_nothing_is_lost(
        self, words: list[tuple[str, bool]], width: int
    ) -> None:
        from brotrechner.core.labeling import Run
        from brotrechner.export.label import _line_width, _wrap_runs

        runs = []
        for index, (word, bold) in enumerate(words):
            runs.append(Run(word, bold))
            if index < len(words) - 1:
                runs.append(Run(" ", False))
        draw = _draw()
        lines = _wrap_runs(draw, runs, *FONTS, width)
        for line in lines:
            if len(line) > 1 or sum(len(t) for t, _ in line[0]) > 1:
                assert _line_width(draw, line, *FONTS) <= width
        joined = "".join(text for line in lines for word in line for text, _ in word)
        assert joined == "".join(word for word, _ in words)


@pytest.mark.gui
class TestLabelDialog:
    @pytest.fixture
    def dialog(self, qapp: object, tmp_path: Path):  # type: ignore[no-untyped-def]
        del qapp
        from brotrechner.gui.dialogs.label_dialog import LabelDialog

        analysis = analyze(
            [ResolvedItem(flour(), 500), ResolvedItem(water(), 350), ResolvedItem(yoghurt(), 50)],
            baked_weight_g=780,
        )
        widget = LabelDialog(analysis, recipe_name="Probe", default_dir=tmp_path)
        yield widget
        widget.close()

    def test_the_label_gets_the_marked_list(self, dialog: object) -> None:
        options = dialog._options(dpi=110)  # type: ignore[attr-defined]
        assert list(options.ingredients) == ["*Weizen*mehl Type 550", "Wasser", "*Joghurt*"]

    def test_without_the_list_the_label_states_the_allergens(self, dialog: object) -> None:
        dialog.chk_ingredients.setChecked(False)  # type: ignore[attr-defined]
        options = dialog._options(dpi=110)  # type: ignore[attr-defined]
        assert options.allergen_note == "Enthält: Weizen, Milch"

    def test_with_the_list_there_is_no_extra_statement(self, dialog: object) -> None:
        assert dialog._options(dpi=110).allergen_note == ""  # type: ignore[attr-defined]
