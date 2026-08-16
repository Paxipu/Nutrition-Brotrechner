"""Tabellenmodell der Zutatenliste.

Die Vorgängerversion füllte eine ``ListCtrl`` bei jeder Änderung komplett neu
und hielt die Sortierung von Hand. Hier übernimmt Qts Modell/View-Trennung die
Arbeit: Das Modell liefert die Daten, ein :class:`IngredientFilterProxy`
filtert und sortiert, und die Ansicht muss davon nichts wissen.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QSortFilterProxyModel,
    Qt,
)

from brotrechner.core.models import Category, Ingredient
from brotrechner.core.validation import Severity, validate_ingredient
from brotrechner.i18n import format_number

__all__ = ["COLUMNS", "IngredientFilterProxy", "IngredientTableModel"]

_Index = QModelIndex | QPersistentModelIndex


@dataclass(frozen=True, slots=True)
class Column:
    """Beschreibung einer Tabellenspalte."""

    key: str
    title: str
    width: int
    numeric: bool = False
    tooltip: str = ""


COLUMNS: Final[tuple[Column, ...]] = (
    Column("name", "Zutat", 190),
    Column("manufacturer", "Hersteller", 108),
    Column("category", "Kategorie", 124),
    Column("energy_kcal", "kcal", 54, numeric=True),
    Column("fat", "Fett", 54, numeric=True, tooltip="Fett je 100 g"),
    Column("carbs", "KH", 54, numeric=True, tooltip="Kohlenhydrate je 100 g"),
    Column("protein", "Eiweiß", 58, numeric=True),
    Column("fiber", "Ballast.", 60, numeric=True, tooltip="Ballaststoffe je 100 g"),
    Column("water", "Wasser %", 66, numeric=True),
    Column("package_price", "Preis/Pkg", 74, numeric=True),
    Column("price_per_100g", "€/100 g", 70, numeric=True),
    Column("status", "", 30, tooltip="Befunde der Datenprüfung"),
)

#: Eigene Rolle, über die der Proxy unformatiert sortiert.
SORT_ROLE: Final = int(Qt.ItemDataRole.UserRole) + 1
#: Rolle, über die die Ansicht an die Zutat selbst kommt.
INGREDIENT_ROLE: Final = int(Qt.ItemDataRole.UserRole) + 2


class IngredientTableModel(QAbstractTableModel):
    """Stellt Zutaten als Tabelle bereit."""

    def __init__(self, ingredients: Sequence[Ingredient] = (), parent: QObject | None = None):
        super().__init__(parent)
        self._items: list[Ingredient] = list(ingredients)
        self._severity: dict[str, Severity | None] = {}
        self._recompute_severity()

    # ── Daten setzen ──────────────────────────────────────────────────────

    def set_ingredients(self, ingredients: Sequence[Ingredient]) -> None:
        """Ersetzt den kompletten Inhalt."""
        self.beginResetModel()
        self._items = list(ingredients)
        self._recompute_severity()
        self.endResetModel()

    def ingredient_at(self, row: int) -> Ingredient | None:
        """Zutat einer Zeile, oder ``None`` bei ungültigem Index."""
        if 0 <= row < len(self._items):
            return self._items[row]
        return None

    def severity_of(self, key: str) -> Severity | None:
        """Höchster Befundgrad einer Zutat, oder ``None`` wenn sie sauber ist."""
        return self._severity.get(key)

    def row_of(self, key: str) -> int:
        """Zeilennummer einer Zutat, oder -1."""
        for row, ingredient in enumerate(self._items):
            if ingredient.key == key:
                return row
        return -1

    def _recompute_severity(self) -> None:
        """Bestimmt je Zutat den höchsten Befundgrad (ohne reine Hinweise)."""
        self._severity.clear()
        for ingredient in self._items:
            findings = [
                f for f in validate_ingredient(ingredient) if f.severity is not Severity.INFO
            ]
            self._severity[ingredient.key] = (
                max((f.severity for f in findings), key=lambda s: s.rank) if findings else None
            )

    # ── Qt-Schnittstelle ──────────────────────────────────────────────────

    def rowCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: N802 - Qt-Vertrag
        return 0 if parent.isValid() else len(self._items)

    def columnCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: N802 - Qt-Vertrag
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(  # noqa: N802 - Qt-Vertrag
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if orientation != Qt.Orientation.Horizontal:
            return None
        column = COLUMNS[section]
        if role == Qt.ItemDataRole.DisplayRole:
            return column.title
        if role == Qt.ItemDataRole.ToolTipRole:
            return column.tooltip or column.title
        if role == Qt.ItemDataRole.TextAlignmentRole and column.numeric:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def data(self, index: _Index, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        ingredient = self._items[index.row()]
        column = COLUMNS[index.column()]

        if role == INGREDIENT_ROLE:
            return ingredient
        if role == SORT_ROLE:
            return _sort_value(ingredient, column)
        if role == Qt.ItemDataRole.TextAlignmentRole and column.numeric:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ToolTipRole:
            return _tooltip(ingredient, self._severity.get(ingredient.key))
        if role == Qt.ItemDataRole.DisplayRole:
            return _display_value(ingredient, column, self._severity.get(ingredient.key))
        return None


def _sort_value(ingredient: Ingredient, column: Column) -> Any:
    """Roher, vergleichbarer Wert einer Zelle."""
    key = column.key
    if key == "name":
        return ingredient.name.casefold()
    if key == "manufacturer":
        return ingredient.manufacturer.casefold()
    if key == "category":
        return ingredient.category.label
    if key == "package_price":
        return ingredient.package_price
    if key == "price_per_100g":
        return ingredient.price_per_100g
    if key == "status":
        return 0
    return float(getattr(ingredient.nutrients, key, 0.0))


def _display_value(ingredient: Ingredient, column: Column, severity: Severity | None) -> str:
    """Anzeigetext einer Zelle."""
    key = column.key
    if key == "name":
        return ingredient.name
    if key == "manufacturer":
        return ingredient.manufacturer or "—"
    if key == "category":
        return ingredient.category.label
    if key == "status":
        if severity is Severity.ERROR:
            return "⛔"
        if severity is Severity.WARNING:
            return "⚠"
        return ""
    if key == "package_price":
        return format_number(ingredient.package_price, 2) if ingredient.has_price else "—"
    if key == "price_per_100g":
        return format_number(ingredient.price_per_100g, 3) if ingredient.has_price else "—"
    if key == "energy_kcal":
        return f"{ingredient.nutrients.energy_kcal:.0f}"
    return format_number(float(getattr(ingredient.nutrients, key, 0.0)), 1)


def _tooltip(ingredient: Ingredient, severity: Severity | None) -> str:
    """Mehrzeiliger Tooltip mit Herkunft, Preisstand und Befunden."""
    lines = [f"<b>{ingredient.display_name}</b>"]
    if ingredient.is_flour:
        lines.append("zählt beim Bäckerprozent als Mehl")
    if ingredient.has_price:
        stand = (
            f", Stand {ingredient.price_updated.strftime('%d.%m.%Y')}"
            if ingredient.price_updated
            else ""
        )
        lines.append(
            f"{format_number(ingredient.package_price, 2)} € je "
            f"{ingredient.package_size_g:.0f} g{stand}"
        )
        if ingredient.price_source:
            lines.append(f"Preisquelle: {ingredient.price_source}")
    else:
        lines.append("kein Preis hinterlegt")
    if severity is not None:
        lines.append(f"<i>Datenprüfung: {severity.label}</i>")
    if ingredient.notes:
        lines.append(f"<i>{ingredient.notes}</i>")
    return "<br>".join(lines)


class IngredientFilterProxy(QSortFilterProxyModel):
    """Filtert nach Suchtext, Kategorie, Preis- und Befundstatus."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.setSortRole(SORT_ROLE)
        self.setDynamicSortFilter(True)
        self._search = ""
        self._category: Category | None = None
        self._only_without_price = False
        self._only_with_findings = False

    def set_search(self, text: str) -> None:
        """Filtert über Name und Hersteller."""
        self._search = text.strip().casefold()
        self.invalidateFilter()

    def set_category(self, category: Category | None) -> None:
        """``None`` zeigt alle Kategorien."""
        self._category = category
        self.invalidateFilter()

    def set_only_without_price(self, active: bool) -> None:
        self._only_without_price = active
        self.invalidateFilter()

    def set_only_with_findings(self, active: bool) -> None:
        self._only_with_findings = active
        self.invalidateFilter()

    def filterAcceptsRow(  # noqa: N802 - Qt-Vertrag
        self, source_row: int, source_parent: _Index
    ) -> bool:
        model = self.sourceModel()
        if not isinstance(model, IngredientTableModel):  # pragma: no cover - Fehlkonfiguration
            return True
        del source_parent
        ingredient = model.ingredient_at(source_row)
        if ingredient is None:  # pragma: no cover
            return False

        if self._category is not None and ingredient.category is not self._category:
            return False
        if self._only_without_price and ingredient.has_price:
            return False
        if self._only_with_findings and model.severity_of(ingredient.key) is None:
            return False
        if self._search:
            haystack = f"{ingredient.name} {ingredient.manufacturer}".casefold()
            if self._search not in haystack:
                return False
        return True
