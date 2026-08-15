"""Tabellenmodelle für die Rezeptzusammenstellung und die Rezeptliste."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Final

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, QPersistentModelIndex, Qt

from brotrechner.core.analysis import RecipeAnalysis, ResolvedItem
from brotrechner.core.models import Ingredient, Recipe
from brotrechner.i18n import format_number

__all__ = ["RECIPE_COLUMNS", "RecipeItemsModel", "RecipeListModel"]

_Index = QModelIndex | QPersistentModelIndex

#: Spalten der Zusammenstellung. Nur die Menge ist bearbeitbar - Namen ändert
#: man in der Zutatenverwaltung, nicht im Rezept.
RECIPE_COLUMNS: Final[tuple[tuple[str, int, bool], ...]] = (
    ("Zutat", 190, False),
    ("Hersteller", 120, False),
    ("Menge (g)", 90, True),
    ("Anteil", 70, False),
    ("Bäcker%", 76, False),
    ("Kosten", 82, False),
)

_COL_NAME, _COL_MANUFACTURER, _COL_AMOUNT, _COL_SHARE, _COL_BAKER, _COL_COST = range(6)


class RecipeItemsModel(QAbstractTableModel):
    """Zutaten des aktuellen Rezepts mit direkt editierbarer Menge.

    Das Modell hält nur Zutat und Menge. Die abgeleiteten Spalten (Anteil,
    Bäckerprozent, Kosten) kommen aus einer :class:`RecipeAnalysis`, die von
    außen gesetzt wird - so gibt es genau *eine* Stelle, an der gerechnet wird.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._items: list[ResolvedItem] = []
        self._analysis: RecipeAnalysis | None = None

    # ── Inhalt ────────────────────────────────────────────────────────────

    @property
    def items(self) -> list[ResolvedItem]:
        """Aktuelle Zutatenzeilen (Kopie der internen Liste)."""
        return list(self._items)

    def set_items(self, items: Sequence[ResolvedItem]) -> None:
        """Ersetzt alle Zeilen."""
        self.beginResetModel()
        self._items = list(items)
        self.endResetModel()

    def add_item(self, ingredient: Ingredient, amount_g: float) -> None:
        """Fügt eine Zutat an oder erhöht die Menge, wenn sie schon enthalten ist.

        Zweimal dieselbe Zutat einzutragen war in der Vorversion möglich und
        führte zu zwei Zeilen, die sich beim Bäckerprozent gegenseitig
        verwässerten. Das Zusammenfassen ist das erwartbarere Verhalten.
        """
        for row, item in enumerate(self._items):
            if item.ingredient.key == ingredient.key:
                self._items[row] = ResolvedItem(ingredient, item.amount_g + amount_g)
                index = self.index(row, _COL_AMOUNT)
                self.dataChanged.emit(self.index(row, 0), self.index(row, len(RECIPE_COLUMNS) - 1))
                del index
                return

        position = len(self._items)
        self.beginInsertRows(QModelIndex(), position, position)
        self._items.append(ResolvedItem(ingredient, amount_g))
        self.endInsertRows()

    def remove_rows(self, rows: Sequence[int]) -> None:
        """Entfernt mehrere Zeilen (von hinten, damit Indizes gültig bleiben)."""
        for row in sorted(set(rows), reverse=True):
            if not 0 <= row < len(self._items):
                continue
            self.beginRemoveRows(QModelIndex(), row, row)
            del self._items[row]
            self.endRemoveRows()

    def clear(self) -> None:
        """Leert die Zusammenstellung."""
        self.set_items([])

    def set_analysis(self, analysis: RecipeAnalysis | None) -> None:
        """Hinterlegt die Auswertung für die abgeleiteten Spalten."""
        self._analysis = analysis
        if self._items:
            self.dataChanged.emit(
                self.index(0, _COL_SHARE),
                self.index(len(self._items) - 1, _COL_COST),
            )

    # ── Qt-Schnittstelle ──────────────────────────────────────────────────

    def rowCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: N802 - Qt-Vertrag
        return 0 if parent.isValid() else len(self._items)

    def columnCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: N802 - Qt-Vertrag
        return 0 if parent.isValid() else len(RECIPE_COLUMNS)

    def headerData(  # noqa: N802 - Qt-Vertrag
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if orientation is Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return RECIPE_COLUMNS[section][0]
        return None

    def flags(self, index: _Index) -> Qt.ItemFlag:
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.isValid() and RECIPE_COLUMNS[index.column()][2]:
            return base | Qt.ItemFlag.ItemIsEditable
        return base

    def data(self, index: _Index, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        item = self._items[index.row()]
        column = index.column()

        if role == Qt.ItemDataRole.TextAlignmentRole and column >= _COL_AMOUNT:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        if role == Qt.ItemDataRole.EditRole and column == _COL_AMOUNT:
            return item.amount_g

        if role == Qt.ItemDataRole.ToolTipRole:
            if column == _COL_COST and not item.ingredient.has_price:
                return "Für diese Zutat ist kein Preis hinterlegt."
            if column == _COL_BAKER and not item.ingredient.is_flour:
                return "Bezogen auf die gesamte Mehlmenge des Rezepts."
            return item.ingredient.display_name

        if role != Qt.ItemDataRole.DisplayRole:
            return None

        if column == _COL_NAME:
            return item.ingredient.name
        if column == _COL_MANUFACTURER:
            return item.ingredient.manufacturer or "—"
        if column == _COL_AMOUNT:
            return format_number(item.amount_g, 1)

        line = self._line_for(index.row())
        if line is None:
            return "—"
        if column == _COL_SHARE:
            return f"{line.share_percent:.1f} %"
        if column == _COL_BAKER:
            return f"{line.baker_percent:.0f} %" if line.baker_percent else "—"
        if column == _COL_COST:
            return f"{format_number(line.cost, 2)} €" if line.has_price else "—"
        return None

    def setData(  # noqa: N802 - Qt-Vertrag
        self, index: _Index, value: Any, role: int = Qt.ItemDataRole.EditRole
    ) -> bool:
        if not index.isValid() or role != Qt.ItemDataRole.EditRole:
            return False
        if index.column() != _COL_AMOUNT:
            return False
        try:
            amount = float(value)
        except (TypeError, ValueError):
            return False
        if amount < 0:
            return False

        row = index.row()
        self._items[row] = ResolvedItem(self._items[row].ingredient, amount)
        self.dataChanged.emit(index, self.index(row, len(RECIPE_COLUMNS) - 1))
        return True

    def _line_for(self, row: int) -> Any:
        """Ausgewertete Zeile aus der hinterlegten Analyse."""
        if self._analysis is None or row >= len(self._analysis.lines):
            return None
        return self._analysis.lines[row]


class RecipeListModel(QAbstractTableModel):
    """Übersicht der gespeicherten Rezepte."""

    COLUMNS: Final[tuple[tuple[str, int], ...]] = (
        ("Rezept", 220),
        ("Datum", 100),
        ("Gebacken", 90),
        ("Zutaten", 70),
    )

    def __init__(self, recipes: Sequence[Recipe] = (), parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._recipes: list[Recipe] = list(recipes)

    def set_recipes(self, recipes: Sequence[Recipe]) -> None:
        """Ersetzt die Liste."""
        self.beginResetModel()
        self._recipes = list(recipes)
        self.endResetModel()

    def recipe_at(self, row: int) -> Recipe | None:
        """Rezept einer Zeile."""
        if 0 <= row < len(self._recipes):
            return self._recipes[row]
        return None

    def rowCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: N802 - Qt-Vertrag
        return 0 if parent.isValid() else len(self._recipes)

    def columnCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: N802 - Qt-Vertrag
        return 0 if parent.isValid() else len(self.COLUMNS)

    def headerData(  # noqa: N802 - Qt-Vertrag
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if orientation is Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.COLUMNS[section][0]
        return None

    def data(self, index: _Index, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        recipe = self._recipes[index.row()]
        column = index.column()

        if role == Qt.ItemDataRole.TextAlignmentRole and column >= 2:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ToolTipRole:
            return recipe.notes or recipe.name
        if role != Qt.ItemDataRole.DisplayRole:
            return None

        if column == 0:
            return recipe.name
        if column == 1:
            return recipe.created_at.strftime("%d.%m.%Y")
        if column == 2:
            return f"{recipe.baked_weight_g:.0f} g"
        return str(len(recipe.items))
