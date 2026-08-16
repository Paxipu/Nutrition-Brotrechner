"""Rezepte-Seite: Liste links, Vorschau rechts.

Die Vorschau zeigt jetzt neben Zutaten und Bäckerprozent auch die Nährwerte je
100 g und die Kosten - mit den *aktuellen* Preisen aus der Zutatendatenbank.
Damit sieht man auf einen Blick, was ein altes Rezept heute kosten würde.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt, Signal, SignalInstance
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from brotrechner.core.analysis import analyze, resolve_items
from brotrechner.core.models import Ingredient, Recipe
from brotrechner.gui.models.recipe_model import RecipeListModel
from brotrechner.gui.theme import SPACING, Tokens
from brotrechner.gui.widgets.cards import Card
from brotrechner.i18n import format_currency, format_number

__all__ = ["RecipesPage"]


class RecipesPage(QWidget):
    """Übersicht und Verwaltung gespeicherter Rezepte."""

    load_requested = Signal(str)
    scale_requested = Signal(str)
    rename_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, tokens: Tokens, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._ingredients: dict[str, Ingredient] = {}
        self._model = RecipeListModel([], self)
        self._all: list[Recipe] = []

        self._build_ui()
        self._connect()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING["md"])

        top = QHBoxLayout()
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Rezept suchen …")
        self.txt_search.setClearButtonEnabled(True)
        self.txt_search.setMaximumWidth(320)
        self.lbl_count = QLabel()
        self.lbl_count.setObjectName("Muted")
        top.addWidget(self.txt_search)
        top.addStretch(1)
        top.addWidget(self.lbl_count)
        layout.addLayout(top)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        self.table = QTableView()
        self.table.setModel(self._model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        for column, (_, width) in enumerate(RecipeListModel.COLUMNS):
            self.table.setColumnWidth(column, width)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        splitter.addWidget(self.table)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        preview_holder = QWidget()
        preview_layout = QVBoxLayout(preview_holder)
        preview_layout.setContentsMargins(0, 0, SPACING["xs"], 0)
        self.preview = Card("Vorschau")
        self.lbl_preview = QLabel("Kein Rezept ausgewählt.")
        self.lbl_preview.setWordWrap(True)
        self.lbl_preview.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_preview.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.preview.add_widget(self.lbl_preview, 1)
        preview_layout.addWidget(self.preview)
        preview_layout.addStretch(1)
        scroll.setWidget(preview_holder)
        scroll.setMinimumWidth(320)
        splitter.addWidget(scroll)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

        buttons = QHBoxLayout()
        self.btn_load = QPushButton("In den Rechner laden")
        self.btn_load.setProperty("accent", True)
        self.btn_scale = QPushButton("Skalieren …")
        self.btn_rename = QPushButton("Umbenennen …")
        self.btn_delete = QPushButton("Löschen")
        self.btn_delete.setProperty("danger", True)
        for button in (self.btn_load, self.btn_scale, self.btn_rename):
            buttons.addWidget(button)
        buttons.addStretch(1)
        buttons.addWidget(self.btn_delete)
        layout.addLayout(buttons)

    def _connect(self) -> None:
        self.table.selectionModel().selectionChanged.connect(lambda *_: self._update_preview())
        self.table.doubleClicked.connect(lambda *_: self._emit(self.load_requested, "laden"))
        self.txt_search.textChanged.connect(self._apply_filter)
        self.btn_load.clicked.connect(lambda: self._emit(self.load_requested, "laden"))
        self.btn_scale.clicked.connect(lambda: self._emit(self.scale_requested, "skalieren"))
        self.btn_rename.clicked.connect(lambda: self._emit(self.rename_requested, "umbenennen"))
        self.btn_delete.clicked.connect(lambda: self._emit(self.delete_requested, "löschen"))

    # ── Daten ─────────────────────────────────────────────────────────────

    def set_data(self, recipes: Sequence[Recipe], ingredients: Sequence[Ingredient]) -> None:
        """Übernimmt Rezepte und die für die Vorschau nötigen Zutaten."""
        self._all = list(recipes)
        self._ingredients = {i.key: i for i in ingredients}
        self._apply_filter(self.txt_search.text())

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().casefold()
        shown = [r for r in self._all if not needle or needle in r.name.casefold()]
        self._model.set_recipes(shown)
        self.lbl_count.setText(
            f"{len(shown)} von {len(self._all)} Rezepten"
            if len(shown) != len(self._all)
            else f"{len(self._all)} Rezepte"
        )
        self._update_preview()

    def select_recipe(self, name: str) -> bool:
        """Markiert ein Rezept und scrollt es ins Bild.

        Wird nach dem Speichern aufgerufen, damit der frische Eintrag nicht
        irgendwo in einer langen Liste gesucht werden muss.
        """
        self.txt_search.clear()
        for row in range(self._model.rowCount()):
            recipe = self._model.recipe_at(row)
            if recipe is not None and recipe.name == name:
                self.table.selectRow(row)
                self.table.scrollTo(
                    self._model.index(row, 0),
                    QAbstractItemView.ScrollHint.PositionAtCenter,
                )
                self.table.setFocus()
                return True
        return False

    def selected_recipe(self) -> Recipe | None:
        """Aktuell markiertes Rezept."""
        rows = self.table.selectionModel().selectedRows()
        return self._model.recipe_at(rows[0].row()) if rows else None

    def _emit(self, signal: SignalInstance, action: str) -> None:
        recipe = self.selected_recipe()
        if recipe is None:
            QMessageBox.information(
                self, "Auswahl nötig", f"Bitte ein Rezept auswählen, um es zu {action}."
            )
            return
        signal.emit(recipe.name)

    # ── Vorschau ──────────────────────────────────────────────────────────

    def _update_preview(self) -> None:
        recipe = self.selected_recipe()
        if recipe is None:
            self.lbl_preview.setText("Kein Rezept ausgewählt.")
            self.preview.set_title("Vorschau")
            return
        self.preview.set_title(recipe.name)
        self.lbl_preview.setText(self._preview_html(recipe))

    def _preview_html(self, recipe: Recipe) -> str:
        """Baut die Rezeptvorschau mit aktuellen Preisen."""
        resolved, missing = resolve_items(recipe.items, self._ingredients)
        analysis = analyze(
            resolved,
            baked_weight_g=recipe.baked_weight_g,
            dough_weight_g=recipe.dough_weight_g,
            energy_kwh=recipe.energy_kwh,
        )
        t = self._tokens

        head = (
            f"<p style='color:{t.text_muted};margin:0'>"
            f"angelegt am {recipe.created_at.strftime('%d.%m.%Y')} · "
            f"{recipe.baked_weight_g:.0f} g gebacken"
            + (f" · TA {analysis.dough_yield:.0f}" if analysis.dough_yield else "")
            + "</p>"
        )

        def ingredient_cell(name: str, manufacturer: str) -> str:
            if not manufacturer:
                return name
            return f"{name} <span style='color:{t.text_muted}'>({manufacturer})</span>"

        rows = "".join(
            "<tr><td style='padding:1px 8px 1px 0'>"
            + ingredient_cell(line.ingredient.name, line.ingredient.manufacturer)
            + f"</td><td align='right'>{format_number(line.amount_g, 0)} g</td>"
            + f"<td align='right' style='color:{t.text_muted}'>"
            + f"{line.baker_percent:.0f} %</td></tr>"
            for line in analysis.lines
        )
        table = (
            "<p style='margin:10px 0 2px 0'><b>Zutaten</b> "
            f"<span style='color:{t.text_muted}'>(Menge · Bäckerprozent)</span></p>"
            f"<table width='100%' cellspacing='0'>{rows}</table>"
        )

        nutrition = ""
        if analysis.baked_weight_g > 0:
            n = analysis.per_100g
            nutrition = (
                "<p style='margin:12px 0 2px 0'><b>Je 100 g gebacken</b></p>"
                f"<p style='margin:0'>{n.energy_kcal:.0f} kcal · "
                f"Fett {format_number(n.fat)} g · "
                f"Kohlenhydrate {format_number(n.carbs)} g · "
                f"Eiweiß {format_number(n.protein)} g · "
                f"Ballaststoffe {format_number(n.fiber)} g · "
                f"Salz {format_number(n.salt, 2)} g</p>"
            )

        cost = (
            "<p style='margin:12px 0 2px 0'><b>Kosten zu heutigen Preisen</b></p>"
            f"<p style='margin:0'>{format_currency(analysis.total_cost)} gesamt · "
            f"{format_currency(analysis.cost_per_kg)} je Kilogramm</p>"
        )
        if not analysis.has_complete_prices:
            cost += (
                f"<p style='margin:2px 0 0 0;color:{t.warning}'>"
                f"Unvollständig: {len(analysis.lines_without_price)} Zutaten ohne Preis.</p>"
            )

        warning = ""
        if missing:
            names = ", ".join(item.display_name for item in missing)
            warning = (
                f"<p style='margin-top:10px;color:{t.danger}'>"
                f"Nicht mehr in der Datenbank: {names}</p>"
            )

        notes = (
            f"<p style='margin-top:10px;color:{t.text_muted}'><i>{recipe.notes}</i></p>"
            if recipe.notes
            else ""
        )
        return head + table + nutrition + cost + warning + notes
