"""Zutaten-Seite: Liste, Detailansicht und Pflegefunktionen.

Gegenüber der Vorversion kommen dazu:

* **Hersteller als eigene Spalte** samt Filter,
* **Import und Export einzelner Zutaten** als eigenständige JSON-Dateien,
* **Datenprüfung** direkt in der Liste - fehlerhafte Einträge tragen ein
  Zeichen in der letzten Spalte und lassen sich darüber filtern,
* eine **Detailspalte**, die alle Werte einer Zutat zeigt, ohne dass man den
  Bearbeiten-Dialog öffnen muss.
"""

from __future__ import annotations

from collections.abc import Sequence
from html import escape

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from brotrechner.core.allergens import describe_allergens
from brotrechner.core.labeling import list_runs
from brotrechner.core.models import Category, Ingredient
from brotrechner.core.validation import Severity, validate_ingredient
from brotrechner.gui.models.ingredient_model import (
    COLUMNS,
    IngredientFilterProxy,
    IngredientTableModel,
)
from brotrechner.gui.theme import SPACING, Tokens
from brotrechner.gui.widgets.cards import Card
from brotrechner.i18n import NUTRIENT_LABELS, NUTRIENT_ORDER, decimals_for, format_number

__all__ = ["IngredientsPage"]


class IngredientsPage(QWidget):
    """Verwaltung der Zutatendatenbank."""

    create_requested = Signal()
    edit_requested = Signal(str)
    duplicate_requested = Signal(str)
    delete_requested = Signal(str)
    import_requested = Signal()
    export_requested = Signal(list)
    csv_requested = Signal()
    validate_requested = Signal()

    def __init__(self, tokens: Tokens, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._model = IngredientTableModel([], self)
        self._proxy = IngredientFilterProxy(self)
        self._proxy.setSourceModel(self._model)

        self._build_ui()
        self._connect()

    # ── Aufbau ────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING["md"])

        # Filterzeile
        filters = QHBoxLayout()
        filters.setSpacing(SPACING["sm"])
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Suchen in Zutat und Hersteller …")
        self.txt_search.setClearButtonEnabled(True)
        self.txt_search.setMinimumWidth(260)

        self.cmb_category = QComboBox()
        self.cmb_category.addItem("Alle Kategorien", None)
        for category in Category:
            self.cmb_category.addItem(category.label, category)

        self.chk_no_price = QCheckBox("ohne Preis")
        self.chk_findings = QCheckBox("mit Befunden")
        self.chk_findings.setToolTip("Zeigt nur Zutaten, bei denen die Datenprüfung anschlägt.")

        self.lbl_count = QLabel()
        self.lbl_count.setObjectName("Muted")

        filters.addWidget(self.txt_search, 1)
        filters.addWidget(self.cmb_category)
        filters.addWidget(self.chk_no_price)
        filters.addWidget(self.chk_findings)
        filters.addStretch(1)
        filters.addWidget(self.lbl_count)
        layout.addLayout(filters)

        # Liste und Detail
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        self.table = QTableView()
        self.table.setModel(self._proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.table.verticalHeader().setVisible(False)
        for column, spec in enumerate(COLUMNS):
            self.table.setColumnWidth(column, spec.width)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        splitter.addWidget(self.table)

        self.detail = Card("Details")
        self.lbl_detail = QLabel("Keine Zutat ausgewählt.")
        self.lbl_detail.setWordWrap(True)
        self.lbl_detail.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_detail.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.detail.add_widget(self.lbl_detail, 1)
        self.detail.setMinimumWidth(280)
        splitter.addWidget(self.detail)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

        # Schaltflächen
        buttons = QHBoxLayout()
        buttons.setSpacing(SPACING["sm"])
        self.btn_new = QPushButton("Neu")
        self.btn_new.setProperty("accent", True)
        self.btn_edit = QPushButton("Bearbeiten")
        self.btn_duplicate = QPushButton("Duplizieren")
        self.btn_delete = QPushButton("Löschen")
        self.btn_delete.setProperty("danger", True)
        self.btn_import = QPushButton("Importieren …")
        self.btn_export = QPushButton("Exportieren …")
        self.btn_csv = QPushButton("CSV")
        self.btn_validate = QPushButton("Datenprüfung …")

        for button in (
            self.btn_new,
            self.btn_edit,
            self.btn_duplicate,
            self.btn_delete,
        ):
            buttons.addWidget(button)
        buttons.addStretch(1)
        for button in (self.btn_import, self.btn_export, self.btn_csv, self.btn_validate):
            buttons.addWidget(button)
        layout.addLayout(buttons)

    def _connect(self) -> None:
        self.txt_search.textChanged.connect(self._proxy.set_search)
        self.txt_search.textChanged.connect(lambda _: self._update_count())
        self.cmb_category.currentIndexChanged.connect(self._on_category_changed)
        self.chk_no_price.toggled.connect(self._proxy.set_only_without_price)
        self.chk_no_price.toggled.connect(lambda _: self._update_count())
        self.chk_findings.toggled.connect(self._proxy.set_only_with_findings)
        self.chk_findings.toggled.connect(lambda _: self._update_count())

        self.table.selectionModel().selectionChanged.connect(lambda *_: self._update_detail())
        self.table.doubleClicked.connect(lambda *_: self._emit_edit())

        self.btn_new.clicked.connect(self.create_requested)
        self.btn_edit.clicked.connect(self._emit_edit)
        self.btn_duplicate.clicked.connect(self._emit_duplicate)
        self.btn_delete.clicked.connect(self._emit_delete)
        self.btn_import.clicked.connect(self.import_requested)
        self.btn_export.clicked.connect(self._emit_export)
        self.btn_csv.clicked.connect(self.csv_requested)
        self.btn_validate.clicked.connect(self.validate_requested)

    # ── Daten ─────────────────────────────────────────────────────────────

    def set_ingredients(self, ingredients: Sequence[Ingredient]) -> None:
        """Übernimmt den Datenbestand und stellt die Auswahl wieder her."""
        selected = [i.key for i in self.selected_ingredients()]
        self._model.set_ingredients(ingredients)
        self._update_count()
        if selected:
            self.select_key(selected[0])
        else:
            self._update_detail()

    def select_key(self, key: str) -> None:
        """Wählt eine Zutat aus und scrollt sie ins Bild."""
        source_row = self._model.row_of(key)
        if source_row < 0:
            return
        index = self._proxy.mapFromSource(self._model.index(source_row, 0))
        if not index.isValid():
            return
        self.table.selectRow(index.row())
        self.table.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter)

    def selected_ingredients(self) -> list[Ingredient]:
        """Alle markierten Zutaten in Anzeigereihenfolge."""
        result: list[Ingredient] = []
        for index in self.table.selectionModel().selectedRows():
            source = self._proxy.mapToSource(index)
            ingredient = self._model.ingredient_at(source.row())
            if ingredient is not None:
                result.append(ingredient)
        return result

    def _selected_one(self) -> Ingredient | None:
        selected = self.selected_ingredients()
        return selected[0] if len(selected) == 1 else None

    # ── Signale ───────────────────────────────────────────────────────────

    def _emit_edit(self) -> None:
        ingredient = self._selected_one()
        if ingredient is None:
            self._warn_selection("bearbeiten")
            return
        self.edit_requested.emit(ingredient.key)

    def _emit_duplicate(self) -> None:
        ingredient = self._selected_one()
        if ingredient is None:
            self._warn_selection("duplizieren")
            return
        self.duplicate_requested.emit(ingredient.key)

    def _emit_delete(self) -> None:
        ingredient = self._selected_one()
        if ingredient is None:
            self._warn_selection("löschen")
            return
        self.delete_requested.emit(ingredient.key)

    def _emit_export(self) -> None:
        selected = self.selected_ingredients()
        if not selected:
            QMessageBox.information(
                self,
                "Nichts ausgewählt",
                "Bitte mindestens eine Zutat markieren. Mit Strg oder Umschalt lassen "
                "sich mehrere gleichzeitig auswählen.",
            )
            return
        self.export_requested.emit(selected)

    def _warn_selection(self, action: str) -> None:
        QMessageBox.information(
            self, "Auswahl nötig", f"Bitte genau eine Zutat auswählen, um sie zu {action}."
        )

    # ── Anzeige ───────────────────────────────────────────────────────────

    def _on_category_changed(self, index: int) -> None:
        self._proxy.set_category(self.cmb_category.itemData(index))
        self._update_count()

    def _update_count(self) -> None:
        shown = self._proxy.rowCount()
        total = self._model.rowCount()
        self.lbl_count.setText(
            f"{shown} von {total} Zutaten" if shown != total else f"{total} Zutaten"
        )

    def _update_detail(self) -> None:
        selected = self.selected_ingredients()
        if len(selected) > 1:
            names = "<br>".join(f"• {i.display_name}" for i in selected[:12])
            more = f"<br>… und {len(selected) - 12} weitere" if len(selected) > 12 else ""
            self.lbl_detail.setText(f"<b>{len(selected)} Zutaten markiert</b><br><br>{names}{more}")
            return
        if not selected:
            self.lbl_detail.setText("Keine Zutat ausgewählt.")
            return
        self.lbl_detail.setText(_detail_html(selected[0], self._tokens))


def flour_share_text(percent: float) -> str:
    """Zusatz für die Detailzeile: Zählt die Zutat (anteilig) als Mehl?"""
    if percent >= 100.0:
        return " · zählt als Mehl"
    if percent > 0.0:
        return f" · Mehlanteil {format_number(percent, 1)} %"
    return ""


def _labeling_html(ingredient: Ingredient, tokens: Tokens) -> str:
    """Bezeichnung im Zutatenverzeichnis und Allergene."""
    runs = "".join(
        f"<b>{escape(run.text)}</b>" if run.bold else escape(run.text)
        for run in list_runs(ingredient.list_name, ingredient.allergens)
    )
    allergens = describe_allergens(ingredient.allergens)
    colour = tokens.warning if ingredient.allergens is None else tokens.text_muted
    return (
        f"<p style='margin-top:10px'><b>Zutatenverzeichnis</b><br>{runs}<br>"
        f"<span style='color:{colour}'>Allergene: {allergens}</span></p>"
    )


def _detail_html(ingredient: Ingredient, tokens: Tokens) -> str:
    """Baut die Detailansicht einer Zutat."""
    n = ingredient.nutrients
    rows = "".join(
        f"<tr><td style='padding:1px 8px 1px 0'>{NUTRIENT_LABELS[field]}</td>"
        f"<td align='right'>{format_number(getattr(n, field), decimals_for(field))}"
        f"{' kcal' if field == 'energy_kcal' else ' g'}</td></tr>"
        for field in NUTRIENT_ORDER
    )
    rows += (
        f"<tr><td style='padding:1px 8px 1px 0'>{NUTRIENT_LABELS['water']}</td>"
        f"<td align='right'>{format_number(n.water, 1)} %</td></tr>"
    )

    parts = [
        f"<b style='font-size:12pt'>{ingredient.name}</b>",
        f"<span style='color:{tokens.text_muted}'>"
        f"{ingredient.manufacturer or 'ohne Herstellerangabe'} · "
        f"{ingredient.category.label}"
        f"{flour_share_text(ingredient.flour_percent)}</span>",
        f"<table width='100%' cellspacing='0' style='margin-top:8px'>{rows}</table>",
        _labeling_html(ingredient, tokens),
    ]

    if ingredient.has_price:
        stand = (
            f", Stand {ingredient.price_updated.strftime('%d.%m.%Y')}"
            if ingredient.price_updated
            else ""
        )
        parts.append(
            f"<p style='margin-top:10px'><b>Preis</b><br>"
            f"{format_number(ingredient.package_price, 2)} € je "
            f"{ingredient.package_size_g:.0f} g<br>"
            f"<b>{format_number(ingredient.price_per_100g, 3)} € je 100 g</b>"
            f"<span style='color:{tokens.text_muted}'>{stand}</span></p>"
        )
        if ingredient.price_source:
            parts.append(
                f"<p style='color:{tokens.text_muted};margin:0'>"
                f"Quelle: {ingredient.price_source}</p>"
            )
    else:
        parts.append(
            f"<p style='margin-top:10px;color:{tokens.warning}'>Kein Preis hinterlegt - "
            f"diese Zutat geht mit 0 € in jede Kalkulation ein.</p>"
        )

    if len(ingredient.price_history) > 0:
        parts.append(
            f"<p style='color:{tokens.text_muted};margin:0'>"
            f"{len(ingredient.price_history)} frühere Preisstände gespeichert</p>"
        )

    findings = [f for f in validate_ingredient(ingredient) if f.severity is not Severity.INFO]
    if findings:
        colour = (
            tokens.danger if any(f.severity is Severity.ERROR for f in findings) else tokens.warning
        )
        items = "".join(f"<li>{f.message}</li>" for f in findings)
        parts.append(
            f"<p style='margin-top:10px;color:{colour}'><b>Datenprüfung</b>"
            f"<ul style='margin:4px 0 0 0'>{items}</ul></p>"
        )

    if ingredient.notes:
        parts.append(
            f"<p style='margin-top:10px;color:{tokens.text_muted}'><i>{ingredient.notes}</i></p>"
        )

    return "".join(parts)
