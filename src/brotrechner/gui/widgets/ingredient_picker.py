"""Zutatenauswahl mit sichtbarem Hersteller.

Genau hier zahlt sich das eigene Hersteller-Feld aus: Die Vorschlagsliste ist
eine zweispaltige Tabelle mit Zutat und Hersteller, statt beides in einen
Namen zu pressen. Gesucht wird über beide Spalten und an beliebiger Stelle im
Wort - "bauck" findet damit alle Bauck-Artikel.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QSize, Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QHeaderView,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QWidget,
)

from brotrechner.core.models import Ingredient

__all__ = ["IngredientPicker"]

_KEY_ROLE = int(Qt.ItemDataRole.UserRole) + 1

#: Eigene Gestaltung der Klappliste. Der abgerundete Rahmen des allgemeinen
#: Stylesheets schneidet bei nur einer Zeile sichtbar in den Text. Die
#: Zeilenhöhe kommt nicht von hier, sondern aus :class:`_RowHeightDelegate` -
#: siehe die Begründung dort.
_POPUP_STYLE = """
QTableView { border-radius: 0; }
QTableView::item { padding: 0 8px; }
"""

#: Zugabe zur Schrifthöhe für die Zeilen der Klappliste.
_ROW_PADDING = 12


class _RowHeightDelegate(QStyledItemDelegate):
    """Legt die Zeilenhöhe der Klappliste verbindlich fest.

    QCompleter berechnet die Höhe seiner Klappliste aus ``sizeHintForRow``,
    gezeichnet wird aber mit der Zeilenhöhe des Kopfbereichs. Stammen beide aus
    verschiedenen Quellen, laufen sie auseinander: Bei einem einzigen Treffer
    fehlten die Unterlängen von "g" und "ß", bei mehreren erschien ein
    Rollbalken für Zeilen, die eigentlich Platz gehabt hätten.

    Über einen Delegaten kommt beides aus derselben Zahl.
    """

    def __init__(self, height: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._height = height

    def sizeHint(  # noqa: N802 - Qt-Vertrag
        self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> QSize:
        """Übernimmt die Breite von Qt und setzt die Höhe fest."""
        size = super().sizeHint(option, index)
        return QSize(size.width(), self._height)


class IngredientPicker(QComboBox):
    """Eingabefeld mit Vervollständigung über Zutat *und* Hersteller."""

    ingredient_chosen = Signal(str)
    """Wird mit dem Zutatenschlüssel ausgelöst, wenn eine Zutat gewählt wurde."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setMinimumWidth(260)
        editor = self.lineEdit()
        if editor is not None:
            editor.setPlaceholderText("Zutat suchen - Name oder Hersteller …")

        self._model = QStandardItemModel(0, 2, self)
        self._model.setHorizontalHeaderLabels(["Zutat", "Hersteller"])
        self.setModel(self._model)
        self.setModelColumn(0)

        self._completer = QCompleter(self._model, self)
        self._completer.setCompletionColumn(0)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)

        popup = QTableView(self)
        popup.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        popup.setShowGrid(False)
        popup.verticalHeader().setVisible(False)
        popup.horizontalHeader().setVisible(False)
        popup.setAlternatingRowColors(True)
        popup.setMinimumWidth(420)
        # Ohne das bricht ein langer Zutatenname auf zwei Zeilen um, sobald die
        # Zeilenhöhe dem Inhalt folgt - die Liste sähe dann zerrissen aus.
        popup.setWordWrap(False)

        row_height = self.fontMetrics().height() + _ROW_PADDING
        popup.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        popup.verticalHeader().setDefaultSectionSize(row_height)
        popup.setStyleSheet(_POPUP_STYLE)
        self._completer.setPopup(popup)

        # Erst *nach* setPopup: QCompleter hängt der Klappliste dort einen
        # eigenen Delegaten an und würde einen vorher gesetzten verwerfen.
        popup.setItemDelegate(_RowHeightDelegate(row_height, popup))
        self.setCompleter(self._completer)

        self._completer.activated.connect(self._on_completer_activated)
        self.activated.connect(self._on_activated)

    def set_ingredients(self, ingredients: Sequence[Ingredient]) -> None:
        """Füllt die Auswahl neu und stellt den bisherigen Text wieder her."""
        current = self.currentText()
        self._model.removeRows(0, self._model.rowCount())

        for ingredient in sorted(ingredients, key=lambda i: i.name.casefold()):
            name_item = QStandardItem(ingredient.name)
            name_item.setData(ingredient.key, _KEY_ROLE)
            name_item.setEditable(False)
            manufacturer_item = QStandardItem(ingredient.manufacturer or "—")
            manufacturer_item.setEditable(False)
            manufacturer_item.setData(ingredient.key, _KEY_ROLE)
            self._model.appendRow([name_item, manufacturer_item])

        popup = self._completer.popup()
        if isinstance(popup, QTableView):
            popup.resizeColumnsToContents()
            # Der Name bekommt den Platz, den er braucht; der Hersteller füllt
            # den Rest. Sonst quetscht sich der längste Name in eine Spalte,
            # die für den kürzesten bemessen wurde.
            header = popup.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.setCurrentIndex(-1)
        self.setEditText(current)

    def current_key(self) -> str | None:
        """Schlüssel der aktuell gewählten Zutat, sonst ``None``.

        Ist nichts ausgewählt, wird der eingetippte Text als eindeutige
        Teilübereinstimmung interpretiert - aber nur, wenn sie *eindeutig* ist.
        Die Vorversion nahm bei mehreren Treffern kommentarlos den ersten.
        """
        index = self.currentIndex()
        if index >= 0:
            item = self._model.item(index, 0)
            if item is not None and item.text() == self.currentText():
                key = item.data(_KEY_ROLE)
                return str(key) if key else None

        text = self.currentText().strip().casefold()
        if not text:
            return None

        matches: list[str] = []
        for row in range(self._model.rowCount()):
            name = self._model.item(row, 0).text()
            manufacturer = self._model.item(row, 1).text()
            key = str(self._model.item(row, 0).data(_KEY_ROLE))
            if name.casefold() == text:
                return key
            if text in f"{name} {manufacturer}".casefold():
                matches.append(key)

        return matches[0] if len(matches) == 1 else None

    def select_key(self, key: str) -> bool:
        """Wählt eine Zutat per Schlüssel aus."""
        for row in range(self._model.rowCount()):
            item = self._model.item(row, 0)
            if item is not None and item.data(_KEY_ROLE) == key:
                self.setCurrentIndex(row)
                return True
        return False

    def _on_activated(self, index: int) -> None:
        item = self._model.item(index, 0)
        if item is not None:
            self.ingredient_chosen.emit(str(item.data(_KEY_ROLE)))

    def _on_completer_activated(self, chosen: object) -> None:
        del chosen
        key = self.current_key()
        if key:
            self.ingredient_chosen.emit(key)
