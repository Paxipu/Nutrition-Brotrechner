"""Rezeptstufen: Sauerteig, Vorteig, Brühstück, Quellstück, Kochstück, Hauptteig.

Bisher war ein Rezept eine flache Zutatenliste. Wer einen Sauerteig am
Vorabend ansetzt, musste sich selbst merken, welches Mehl und welches Wasser
dorthin gehören - und die Teigausbeute des Sauerteigs von Hand ausrechnen.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from brotrechner.core.analysis import ResolvedItem, analyze, resolve_items
from brotrechner.core.labeling import build_ingredient_list
from brotrechner.core.models import Ingredient, Recipe, RecipeItem, Stage
from brotrechner.core.nutrients import Nutrients

FLOUR = Ingredient(
    name="Roggenmehl 1150",
    nutrients=Nutrients(energy_kcal=330, carbs=67, protein=8, water=13.0),
    flour_percent=100.0,
    label_name="*Roggen*mehl",
    allergens=frozenset(),
)
WATER = Ingredient(name="Wasser", nutrients=Nutrients(water=100.0), allergens=frozenset())
SALT = Ingredient(name="Salz", nutrients=Nutrients(salt=100.0), allergens=frozenset())
SEEDS = Ingredient(name="Sonnenblumenkerne", nutrients=Nutrients(energy_kcal=580, fat=50))


def _sourdough_bread() -> list[ResolvedItem]:
    """Roggenbrot: Sauerteig aus 200 g Mehl und 200 g Wasser, Rest im Hauptteig."""
    return [
        ResolvedItem(FLOUR, 300.0),
        ResolvedItem(WATER, 150.0),
        ResolvedItem(SALT, 10.0),
        ResolvedItem(FLOUR, 200.0, Stage.SOURDOUGH),
        ResolvedItem(WATER, 200.0, Stage.SOURDOUGH),
    ]


class TestStage:
    def test_the_usual_order(self) -> None:
        assert [stage.label for stage in Stage] == [
            "Sauerteig",
            "Vorteig",
            "Brühstück",
            "Quellstück",
            "Kochstück",
            "Hauptteig",
        ]

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("sourdough", Stage.SOURDOUGH),
            ("Brühstück", Stage.SCALD),
            ("vorteig", Stage.PREFERMENT),
            (Stage.SOAKER, Stage.SOAKER),
            ("Teigling", Stage.MAIN),
            (None, Stage.MAIN),
            (42, Stage.MAIN),
        ],
    )
    def test_parsing(self, value: object, expected: Stage) -> None:
        assert Stage.parse(value) is expected


class TestRecipeItem:
    def test_the_main_dough_by_default(self) -> None:
        assert RecipeItem("k", "Mehl", "", 100.0).stage is Stage.MAIN

    def test_it_is_saved_and_read(self) -> None:
        item = RecipeItem("k", "Mehl", "", 100.0, Stage.SCALD)
        data = item.to_dict()
        assert data["stage"] == "scald"
        assert RecipeItem.from_dict(data) == item

    def test_older_files_are_main_dough(self) -> None:
        data = RecipeItem("k", "Mehl", "", 100.0).to_dict()
        del data["stage"]
        assert RecipeItem.from_dict(data).stage is Stage.MAIN

    def test_an_unknown_stage_is_main_dough(self) -> None:
        data = {"ingredient_key": "k", "name": "Mehl", "amount_g": 1, "stage": "Zauberteig"}
        assert RecipeItem.from_dict(data).stage is Stage.MAIN

    def test_scaling_keeps_the_stage(self) -> None:
        recipe = Recipe(name="R", items=[RecipeItem("k", "Mehl", "", 100.0, Stage.SOURDOUGH)])
        assert recipe.scaled(2.0).items[0].stage is Stage.SOURDOUGH

    def test_resolving_keeps_the_stage(self) -> None:
        item = RecipeItem(FLOUR.key, FLOUR.name, FLOUR.manufacturer, 100.0, Stage.PREFERMENT)
        resolved, missing = resolve_items([item], {FLOUR.key: FLOUR})
        assert missing == []
        assert resolved[0].stage is Stage.PREFERMENT


class TestStageSummaries:
    def test_each_stage_in_baking_order(self) -> None:
        analysis = analyze(_sourdough_bread(), baked_weight_g=750.0)
        assert [summary.stage for summary in analysis.stages] == [Stage.SOURDOUGH, Stage.MAIN]
        assert analysis.has_stages

    def test_sourdough_figures(self) -> None:
        sourdough = analyze(_sourdough_bread(), baked_weight_g=750.0).stages[0]
        assert sourdough.weight_g == pytest.approx(400.0)
        assert sourdough.flour_g == pytest.approx(200.0)
        assert sourdough.water_g == pytest.approx(200.0)
        assert sourdough.dough_yield == pytest.approx(200.0)
        assert sourdough.flour_share_percent == pytest.approx(40.0)

    def test_main_dough_figures(self) -> None:
        main = analyze(_sourdough_bread(), baked_weight_g=750.0).stages[1]
        assert main.weight_g == pytest.approx(460.0)
        assert main.dough_yield == pytest.approx(150.0)
        assert main.flour_share_percent == pytest.approx(60.0)

    def test_the_lines_know_their_stage(self) -> None:
        analysis = analyze(_sourdough_bread(), baked_weight_g=750.0)
        assert [line.stage for line in analysis.lines][-2:] == [Stage.SOURDOUGH] * 2

    def test_a_stage_without_flour_has_no_dough_yield(self) -> None:
        items = [
            ResolvedItem(FLOUR, 500.0),
            ResolvedItem(SEEDS, 100.0, Stage.SCALD),
            ResolvedItem(WATER, 100.0, Stage.SCALD),
        ]
        scald = analyze(items, baked_weight_g=650.0).stages[0]
        assert scald.stage is Stage.SCALD
        assert scald.flour_g == 0.0
        assert scald.dough_yield == 0.0
        assert scald.flour_share_percent == 0.0

    def test_only_main_dough_is_no_staging(self) -> None:
        analysis = analyze([ResolvedItem(FLOUR, 500.0)], baked_weight_g=400.0)
        assert not analysis.has_stages
        assert [summary.stage for summary in analysis.stages] == [Stage.MAIN]

    def test_what_is_weighed_counts_not_the_scaled_dough(self) -> None:
        """Die Stufen sagen, was abzuwiegen ist - der Teigrest in der Schüssel ändert das nicht."""
        plain = analyze(_sourdough_bread(), baked_weight_g=750.0)
        scaled = analyze(_sourdough_bread(), baked_weight_g=750.0, dough_weight_g=800.0)
        assert scaled.stages == plain.stages

    def test_an_empty_recipe_has_no_stages(self) -> None:
        assert analyze([], baked_weight_g=0.0).stages == ()

    @given(
        amounts=st.lists(
            st.tuples(
                st.sampled_from([FLOUR, WATER, SALT, SEEDS]),
                st.floats(min_value=0.1, max_value=2000.0),
                st.sampled_from(list(Stage)),
            ),
            min_size=1,
            max_size=12,
        )
    )
    def test_the_stages_add_up(self, amounts: list[tuple[Ingredient, float, Stage]]) -> None:
        items = [ResolvedItem(ingredient, grams, stage) for ingredient, grams, stage in amounts]
        analysis = analyze(items, baked_weight_g=100.0)
        assert sum(s.weight_g for s in analysis.stages) == pytest.approx(analysis.weighed_mass_g)
        assert sum(s.flour_g for s in analysis.stages) == pytest.approx(analysis.flour_mass_g)
        assert sum(s.water_g for s in analysis.stages) == pytest.approx(analysis.water_mass_g)
        if analysis.flour_mass_g > 0:
            shares = sum(s.flour_share_percent for s in analysis.stages)
            assert shares == pytest.approx(100.0)


class TestIngredientList:
    def test_the_same_flour_in_two_stages_is_one_entry(self) -> None:
        analysis = analyze(_sourdough_bread(), baked_weight_g=750.0)
        listing = build_ingredient_list(analysis.lines, baked_weight_g=750.0)
        flour = [entry for entry in listing.entries if "mehl" in entry.markup]
        assert len(flour) == 1
        assert flour[0].weight_g == pytest.approx(500.0)

    def test_an_ingredient_without_allergens_is_named_once(self) -> None:
        items = [ResolvedItem(SEEDS, 50.0), ResolvedItem(SEEDS, 50.0, Stage.SOAKER)]
        analysis = analyze(items, baked_weight_g=90.0)
        listing = build_ingredient_list(analysis.lines, baked_weight_g=90.0)
        assert listing.unknown == ("Sonnenblumenkerne",)
