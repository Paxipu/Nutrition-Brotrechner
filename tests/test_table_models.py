"""Die Tabellenmodelle der Zutatenliste und der Rezeptliste."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import pytest

from brotrechner.core.models import Category, Ingredient, Recipe, RecipeItem
from brotrechner.core.nutrients import Nutrients

pytestmark = pytest.mark.gui

FLOUR = Ingredient(
    name="Weizenmehl 550",
    manufacturer="Aurora",
    category=Category.FLOUR,
    nutrients=Nutrients(energy_kcal=341, fat=1.2, carbs=71, protein=10, fiber=4, water=13.5),
    flour_percent=100.0,
    package_price=0.99,
    package_size_g=1000.0,
    price_source="Supermarkt",
    price_updated=date(2026, 9, 1),
    notes="Standardmehl",
)
STARTER = Ingredient(
    name="Anstellgut",
    category=Category.LEAVENING,
    nutrients=Nutrients(energy_kcal=170, carbs=36, protein=4, water=56.5),
    flour_percent=50.0,
)
BROKEN = Ingredient(name="Kaputt", nutrients=Nutrients(carbs=80.0, water=30.0))
ODD = Ingredient(name="Seltsam", category=Category.FLOUR, nutrients=Nutrients(water=40.0))


def _column(key: str) -> int:
    from brotrechner.gui.models.ingredient_model import COLUMNS

    return [column.key for column in COLUMNS].index(key)


@pytest.fixture
def model(qapp: object):  # type: ignore[no-untyped-def]
    del qapp
    from brotrechner.gui.models.ingredient_model import IngredientTableModel

    return IngredientTableModel([FLOUR, STARTER, BROKEN, ODD])


def _cell(model: Any, row: int, key: str, role: Any = None) -> Any:
    from PySide6.QtCore import Qt

    index = model.index(row, _column(key))
    return model.data(index, Qt.ItemDataRole.DisplayRole if role is None else role)


class TestIngredientCells:
    def test_text(self, model: Any) -> None:
        assert _cell(model, 0, "name") == "Weizenmehl 550"
        assert _cell(model, 0, "manufacturer") == "Aurora"
        assert _cell(model, 1, "manufacturer") == "—"
        assert _cell(model, 0, "category") == "Mehl"

    def test_numbers(self, model: Any) -> None:
        assert _cell(model, 0, "energy_kcal") == "341"
        assert _cell(model, 0, "fat") == "1,2"
        assert _cell(model, 0, "water") == "13,5"

    def test_prices(self, model: Any) -> None:
        assert _cell(model, 0, "package_price") == "0,99"
        assert _cell(model, 0, "price_per_100g") == "0,099"
        assert _cell(model, 1, "package_price") == "—"
        assert _cell(model, 1, "price_per_100g") == "—"

    def test_findings(self, model: Any) -> None:
        from brotrechner.core.validation import Severity

        assert model.severity_of(BROKEN.key) is Severity.ERROR
        assert _cell(model, 2, "status") == "⛔"
        assert model.severity_of(FLOUR.key) is None
        assert _cell(model, 0, "status") == ""

    def test_a_warning(self, model: Any) -> None:
        from brotrechner.core.validation import Severity

        assert model.severity_of(ODD.key) is Severity.WARNING
        assert _cell(model, 3, "status") == "⚠"

    def test_numbers_are_right_aligned(self, model: Any) -> None:
        from PySide6.QtCore import Qt

        role = Qt.ItemDataRole.TextAlignmentRole
        assert _cell(model, 0, "fat", role) & int(Qt.AlignmentFlag.AlignRight)
        assert _cell(model, 0, "name", role) is None

    def test_the_ingredient_itself(self, model: Any) -> None:
        from brotrechner.gui.models.ingredient_model import INGREDIENT_ROLE

        assert _cell(model, 1, "name", INGREDIENT_ROLE) is STARTER


class TestIngredientTooltip:
    def _tooltip(self, model: Any, row: int) -> str:
        from PySide6.QtCore import Qt

        return str(_cell(model, row, "name", Qt.ItemDataRole.ToolTipRole))

    def test_flour_with_price(self, model: Any) -> None:
        text = self._tooltip(model, 0)
        assert "zählt beim Bäckerprozent als Mehl" in text
        assert "0,99 € je 1000 g, Stand 01.09.2026" in text
        assert "Preisquelle: Supermarkt" in text
        assert "<i>Standardmehl</i>" in text

    def test_partly_flour_without_price(self, model: Any) -> None:
        text = self._tooltip(model, 1)
        assert "zählt zu 50,0 % als Mehl" in text
        assert "kein Preis hinterlegt" in text
        assert "Allergene: nicht erfasst" in text

    def test_findings_are_mentioned(self, model: Any) -> None:
        assert "Datenprüfung: Fehler" in self._tooltip(model, 2)


class TestIngredientHeader:
    def test_titles_and_hints(self, model: Any) -> None:
        from PySide6.QtCore import Qt

        horizontal = Qt.Orientation.Horizontal
        fat = _column("fat")
        assert model.headerData(fat, horizontal) == "Fett"
        assert model.headerData(fat, horizontal, Qt.ItemDataRole.ToolTipRole) == "Fett je 100 g"
        name = _column("name")
        assert model.headerData(name, horizontal, Qt.ItemDataRole.ToolTipRole) == "Zutat"
        assert model.headerData(0, Qt.Orientation.Vertical) is None

    def test_lookups(self, model: Any) -> None:
        assert model.row_of(STARTER.key) == 1
        assert model.row_of("gibt|es nicht") == -1
        assert model.ingredient_at(9) is None


class TestSorting:
    @pytest.fixture
    def proxy(self, model: Any):  # type: ignore[no-untyped-def]
        from brotrechner.gui.models.ingredient_model import IngredientFilterProxy

        widget = IngredientFilterProxy()
        widget.setSourceModel(model)
        return widget

    def _names(self, proxy: Any) -> list[str]:
        return [proxy.index(row, _column("name")).data() for row in range(proxy.rowCount())]

    def test_by_energy(self, proxy: Any) -> None:
        from PySide6.QtCore import Qt

        proxy.sort(_column("energy_kcal"), Qt.SortOrder.DescendingOrder)
        assert self._names(proxy)[:2] == ["Weizenmehl 550", "Anstellgut"]

    def test_by_price(self, proxy: Any) -> None:
        from PySide6.QtCore import Qt

        proxy.sort(_column("package_price"), Qt.SortOrder.DescendingOrder)
        assert self._names(proxy)[0] == "Weizenmehl 550"

    def test_by_findings(self, proxy: Any) -> None:
        """Fehler zuerst, dann Warnungen - bisher sortierte die Spalte gar nicht."""
        from PySide6.QtCore import Qt

        proxy.sort(_column("status"), Qt.SortOrder.DescendingOrder)
        assert self._names(proxy)[:2] == ["Kaputt", "Seltsam"]

    def test_by_manufacturer_and_category(self, proxy: Any) -> None:
        from PySide6.QtCore import Qt

        proxy.sort(_column("manufacturer"), Qt.SortOrder.DescendingOrder)
        assert self._names(proxy)[0] == "Weizenmehl 550"
        proxy.sort(_column("category"), Qt.SortOrder.AscendingOrder)
        assert self._names(proxy)[0] == "Weizenmehl 550", "„Mehl“ vor „Sonstiges“ und „Triebmittel“"


class TestFilter:
    @pytest.fixture
    def proxy(self, model: Any):  # type: ignore[no-untyped-def]
        from brotrechner.gui.models.ingredient_model import IngredientFilterProxy

        widget = IngredientFilterProxy()
        widget.setSourceModel(model)
        return widget

    def _names(self, proxy: Any) -> set[str]:
        return {proxy.index(row, 0).data() for row in range(proxy.rowCount())}

    def test_search_covers_name_and_manufacturer(self, proxy: Any) -> None:
        proxy.set_search("  aurora ")
        assert self._names(proxy) == {"Weizenmehl 550"}
        proxy.set_search("ANSTELL")
        assert self._names(proxy) == {"Anstellgut"}

    def test_category(self, proxy: Any) -> None:
        proxy.set_category(Category.FLOUR)
        assert self._names(proxy) == {"Weizenmehl 550", "Seltsam"}
        proxy.set_category(None)
        assert len(self._names(proxy)) == 4

    def test_only_without_price(self, proxy: Any) -> None:
        proxy.set_only_without_price(True)
        assert "Weizenmehl 550" not in self._names(proxy)

    def test_only_with_findings(self, proxy: Any) -> None:
        proxy.set_only_with_findings(True)
        assert self._names(proxy) == {"Kaputt", "Seltsam"}

    def test_filters_combine(self, proxy: Any) -> None:
        proxy.set_only_with_findings(True)
        proxy.set_category(Category.FLOUR)
        assert self._names(proxy) == {"Seltsam"}


class TestRecipeList:
    @pytest.fixture
    def recipes(self, qapp: object):  # type: ignore[no-untyped-def]
        del qapp
        from brotrechner.gui.models.recipe_model import RecipeListModel

        return RecipeListModel(
            [
                Recipe(
                    name="Roggenbrot",
                    items=[RecipeItem("k", "Mehl", "", 500.0), RecipeItem("w", "Wasser", "", 1)],
                    baked_weight_g=812.4,
                    notes="Ofen heißer",
                    created_at=datetime(2026, 3, 5, 10, 0, tzinfo=timezone.utc),
                ),
                Recipe(name="Leer"),
            ]
        )

    def _cell(self, recipes: Any, row: int, column: int, role: Any = None) -> Any:
        from PySide6.QtCore import Qt

        index = recipes.index(row, column)
        return recipes.data(index, Qt.ItemDataRole.DisplayRole if role is None else role)

    def test_the_columns(self, recipes: Any) -> None:
        from PySide6.QtCore import Qt

        titles = [
            recipes.headerData(c, Qt.Orientation.Horizontal) for c in range(recipes.columnCount())
        ]
        assert titles == ["Rezept", "Datum", "Gebacken", "Zutaten"]
        assert recipes.headerData(0, Qt.Orientation.Vertical) is None

    def test_the_cells(self, recipes: Any) -> None:
        assert [self._cell(recipes, 0, c) for c in range(4)] == [
            "Roggenbrot",
            "05.03.2026",
            "812 g",
            "2",
        ]

    def test_the_tooltip_shows_the_notes(self, recipes: Any) -> None:
        from PySide6.QtCore import Qt

        assert self._cell(recipes, 0, 0, Qt.ItemDataRole.ToolTipRole) == "Ofen heißer"
        assert self._cell(recipes, 1, 0, Qt.ItemDataRole.ToolTipRole) == "Leer"

    def test_numbers_are_right_aligned(self, recipes: Any) -> None:
        from PySide6.QtCore import Qt

        role = Qt.ItemDataRole.TextAlignmentRole
        assert self._cell(recipes, 0, 2, role) & int(Qt.AlignmentFlag.AlignRight)
        assert self._cell(recipes, 0, 0, role) is None

    def test_lookups(self, recipes: Any) -> None:
        assert recipes.recipe_at(1).name == "Leer"
        assert recipes.recipe_at(5) is None
        assert recipes.rowCount() == 2
