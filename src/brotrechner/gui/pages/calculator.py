"""Rechner-Seite: Rezept links, Auswertung rechts.

Neugliederung gegenüber der Vorversion
--------------------------------------
Früher war der Rechner eine einzige, von oben nach unten gewachsene Spalte:
Eingabezeile, Liste, Prozessfelder, ein großer BERECHNEN-Knopf und darunter ein
verschachteltes Register mit vier Monospace-Textfeldern. Man musste den Knopf
drücken, um überhaupt etwas zu sehen, und die Ergebnisse lagen hinter Reitern
versteckt.

Jetzt gilt:

* **Zwei Spalten.** Links wird eingegeben, rechts steht das Ergebnis - beides
  gleichzeitig sichtbar.
* **Keine Rechnen-Taste.** Jede Änderung löst nach kurzer Verzögerung eine
  Neuberechnung aus. Der frühere Zustand "Zahlen auf dem Schirm passen nicht
  mehr zur Eingabe" kann nicht mehr auftreten.
* **Karten statt Textblöcke.** Kennzahlen, Nährwerte, Kosten und Bäckerprozent
  haben je eine eigene Fläche und sind untereinander lesbar, statt in vier
  Reiter zu zerfallen.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from html import escape

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from brotrechner.core.analysis import (
    DEFAULT_ENERGY_PRICE_EUR_PER_KWH,
    RecipeAnalysis,
    ResolvedItem,
    analyze,
)
from brotrechner.core.models import Ingredient, Recipe, RecipeItem
from brotrechner.core.plausibility import ProcessFinding, check_process, has_errors
from brotrechner.core.portions import MAX_NAME_LENGTH, MAX_WEIGHT_G, SUGGESTED_NAMES, Portion
from brotrechner.core.validation import Severity
from brotrechner.gui.models.recipe_model import RECIPE_COLUMNS, RecipeItemsModel
from brotrechner.gui.theme import SPACING, Tokens
from brotrechner.gui.widgets.cards import Card, StatCard
from brotrechner.gui.widgets.ingredient_picker import IngredientPicker
from brotrechner.gui.widgets.nutrition_panel import NutritionPanel
from brotrechner.i18n import format_currency, format_number

__all__ = ["CalculatorPage"]

#: Wartezeit nach der letzten Eingabe, bevor neu gerechnet wird. Kurz genug,
#: dass es unmittelbar wirkt, lang genug, dass Tippen nicht ruckelt.
_RECALC_DELAY_MS = 180

#: Überschrift der Nährwertkarte, solange sie Werte je 100 g zeigt.
_NUTRITION_TITLE = "Nährwerte je 100 g gebacken"


class CalculatorPage(QWidget):
    """Zusammenstellen und Auswerten eines Rezepts."""

    analysis_changed = Signal(object)
    """Meldet die neue :class:`RecipeAnalysis` an das Hauptfenster."""

    status_message = Signal(str)

    def __init__(self, tokens: Tokens, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._ingredients: dict[str, Ingredient] = {}
        self._analysis = RecipeAnalysis()
        self._items_model = RecipeItemsModel(self)

        self._recalc_timer = QTimer(self)
        self._recalc_timer.setSingleShot(True)
        self._recalc_timer.setInterval(_RECALC_DELAY_MS)
        self._recalc_timer.timeout.connect(self._recalculate)

        self._build_ui()
        # Fingerabdruck des zuletzt geladenen, gespeicherten oder geleerten
        # Stands; weicht der Rechner davon ab, ginge beim Leeren etwas verloren.
        self._saved_state: tuple[object, ...] = ()
        self._connect()
        self._recalculate()

    # ── Aufbau ────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(SPACING["md"])

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_input_column())
        splitter.addWidget(self._build_result_column())
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        # Ausdrückliche Startbreiten: Streckfaktoren allein greifen erst beim
        # Vergrößern, sodass die Auswertung sonst auf einen Streifen zusammenfällt.
        splitter.setSizes([560, 620])
        outer.addWidget(splitter, 1)

    def _build_input_column(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING["md"])

        # Rezeptname
        name_card = Card("Rezept")
        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("Name des Rezepts, z. B. Roggenmischbrot")
        name_card.add_widget(self.txt_name)
        layout.addWidget(name_card)

        # Zusammenstellung
        mix_card = Card("Zutaten")
        row = QHBoxLayout()
        row.setSpacing(SPACING["sm"])
        self.picker = IngredientPicker()
        self.spin_amount = QDoubleSpinBox()
        self.spin_amount.setRange(0.0, 100_000.0)
        self.spin_amount.setDecimals(1)
        self.spin_amount.setSuffix(" g")
        self.spin_amount.setValue(0.0)
        self.spin_amount.setFixedWidth(110)
        self.spin_amount.setToolTip("Einwaage dieser Zutat")
        self.btn_add = QPushButton("Hinzufügen")
        self.btn_add.setProperty("accent", True)
        row.addWidget(self.picker, 1)
        row.addWidget(self.spin_amount)
        row.addWidget(self.btn_add)
        mix_card.body.addLayout(row)

        self.table = QTableView()
        self.table.setModel(self._items_model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.table.setMinimumHeight(190)
        self.table.setMinimumWidth(380)
        header = self.table.horizontalHeader()
        for column, (_, width, _) in enumerate(RECIPE_COLUMNS):
            self.table.setColumnWidth(column, width)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        mix_card.add_widget(self.table, 1)

        self.lbl_summary = QLabel()
        self.lbl_summary.setObjectName("Muted")
        mix_card.add_widget(self.lbl_summary)

        buttons = QHBoxLayout()
        self.btn_remove = QPushButton("Entfernen")
        self.btn_clear = QPushButton("Alles leeren")
        buttons.addWidget(self.btn_remove)
        buttons.addWidget(self.btn_clear)
        buttons.addStretch(1)
        mix_card.body.addLayout(buttons)
        layout.addWidget(mix_card, 1)

        # Prozessdaten
        process_card = Card("Backprozess")
        form = QGridLayout()
        form.setHorizontalSpacing(SPACING["lg"])
        form.setVerticalSpacing(SPACING["sm"])

        self.spin_dough = _weight_spin("optional - gemessener Rohteig")
        self.spin_baked = _weight_spin("Pflicht - Bezug aller Werte je 100 g")
        self.spin_kwh = QDoubleSpinBox()
        self.spin_kwh.setRange(0.0, 100.0)
        self.spin_kwh.setDecimals(2)
        self.spin_kwh.setSuffix(" kWh")
        self.spin_price = QDoubleSpinBox()
        self.spin_price.setRange(0.0, 10.0)
        self.spin_price.setDecimals(2)
        self.spin_price.setSingleStep(0.01)
        self.spin_price.setSuffix(" €/kWh")
        self.spin_price.setValue(DEFAULT_ENERGY_PRICE_EUR_PER_KWH)

        for column, (label, widget, tip) in enumerate(
            [
                (
                    "Rohteig",
                    self.spin_dough,
                    "Gewogenes Teiggewicht. Weicht es von der Einwaage ab, werden alle "
                    "Mengen entsprechend skaliert - so wirkt sich Teig aus, der in der "
                    "Schüssel bleibt.",
                ),
                (
                    "Gebacken",
                    self.spin_baked,
                    "Gewicht des fertigen Brots. Alle Nährwerte je 100 g beziehen sich darauf.",
                ),
                ("Backenergie", self.spin_kwh, "Stromverbrauch des Backvorgangs."),
                ("Strompreis", self.spin_price, "Arbeitspreis inklusive Grundgebühranteil."),
            ]
        ):
            caption = QLabel(label)
            caption.setObjectName("Muted")
            widget.setToolTip(tip)
            form.addWidget(caption, 0, column)
            form.addWidget(widget, 1, column)
            form.setColumnStretch(column, 1)
        self._build_portion_row(form)
        process_card.body.addLayout(form)

        # Befunde der Plausibilitätsprüfung: Ein Tippfehler beim Brotgewicht
        # verzerrt jede Angabe je 100 g und soll sofort auffallen.
        self.lbl_process = QLabel()
        self.lbl_process.setWordWrap(True)
        self.lbl_process.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_process.setVisible(False)
        process_card.add_widget(self.lbl_process)
        layout.addWidget(process_card)

        return container

    def _build_portion_row(self, form: QGridLayout) -> None:
        """Portion: Bezeichnung und Gewicht, darunter im Raster des Backprozesses."""
        self.cmb_portion = QComboBox()
        self.cmb_portion.setEditable(True)
        self.cmb_portion.addItems(SUGGESTED_NAMES)
        self.cmb_portion.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        edit = self.cmb_portion.lineEdit()
        if edit is not None:
            edit.setMaxLength(MAX_NAME_LENGTH)
        self.cmb_portion.setToolTip(
            "Bezeichnung einer Portion, etwa Scheibe oder Brötchen - aus der Liste\n"
            "oder frei eingetragen."
        )
        self.spin_portion = QDoubleSpinBox()
        self.spin_portion.setRange(0.0, MAX_WEIGHT_G)
        self.spin_portion.setDecimals(1)
        self.spin_portion.setSuffix(" g")
        self.spin_portion.setSpecialValueText("—")
        self.spin_portion.setToolTip(
            "Gewicht einer Portion des fertigen Brots. Mit einem Gewicht zeigen\n"
            "Rechner, Bericht und Etikett die Werte zusätzlich je Portion."
        )
        self.lbl_portion = QLabel()
        self.lbl_portion.setObjectName("Muted")

        for column, text in enumerate(("Portion", "Gewicht je Portion")):
            caption = QLabel(text)
            caption.setObjectName("Muted")
            form.addWidget(caption, 2, column)
        form.addWidget(self.cmb_portion, 3, 0)
        form.addWidget(self.spin_portion, 3, 1)
        form.addWidget(self.lbl_portion, 3, 2, 1, 2)

    def _build_basis_row(self) -> QWidget:
        """Umschalter zwischen Werten je 100 g und je Portion.

        Eine eigene Spalte je Portion machte die Tafel breiter, als die
        Auswertungsspalte ist. Sichtbar nur, wenn eine Portion eingetragen ist.
        """
        self.basis_row = QWidget()
        row = QHBoxLayout(self.basis_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(SPACING["md"])
        caption = QLabel("Bezug")
        caption.setObjectName("Muted")
        self.rb_per_100g = QRadioButton("je 100 g")
        self.rb_per_100g.setChecked(True)
        self.rb_per_portion = QRadioButton("je Portion")
        self.rb_per_portion.setToolTip(
            "Werte und Referenzmenge je Portion. Ampel und Bandbreite gelten\n"
            "immer je 100 g - einen anderen Bezug gibt es für sie nicht."
        )
        group = QButtonGroup(self.basis_row)
        for button in (self.rb_per_100g, self.rb_per_portion):
            group.addButton(button)
        row.addWidget(caption)
        row.addWidget(self.rb_per_100g)
        row.addWidget(self.rb_per_portion)
        row.addStretch(1)
        self.basis_row.setVisible(False)
        return self.basis_row

    def _build_result_column(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(400)
        # Bewusst "bei Bedarf": Auf einem schmalen Bildschirm ist eine Bildlaufleiste
        # allemal besser, als Zahlen am rechten Rand abzuschneiden.
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, SPACING["xs"], 0)
        layout.setSpacing(SPACING["md"])

        # Kennzahlen
        stats = QGridLayout()
        stats.setSpacing(SPACING["sm"])
        self.stat_energy = StatCard("Brennwert je 100 g", "—")
        self.stat_weight = StatCard("Gebacken", "—")
        self.stat_yield = StatCard("Teigausbeute", "—")
        self.stat_cost = StatCard("Kosten je kg", "—")
        # Zwei Spalten statt vier: bei schmaler Auswertungsspalte würde die
        # vierte Karte sonst aus dem sichtbaren Bereich laufen.
        for index, card in enumerate(
            [self.stat_energy, self.stat_weight, self.stat_yield, self.stat_cost]
        ):
            stats.addWidget(card, index // 2, index % 2)
        stats.setColumnStretch(0, 1)
        stats.setColumnStretch(1, 1)
        layout.addLayout(stats)

        # Nährwerte
        nutrition_card = Card(_NUTRITION_TITLE)
        self.nutrition_card = nutrition_card
        self.chk_ranges = QCheckBox("Toleranzen")
        self.chk_ranges.setChecked(True)
        self.chk_ranges.setToolTip(
            "Zeigt, wie weit ein Laborwert des fertigen Brots von der Angabe\n"
            "abweichen darf, ohne dass sie als falsch gilt - nach Tabelle 1 der\n"
            "Leitlinie der EU-Kommission zu Toleranzen (Dezember 2012)."
        )
        nutrition_card.add_header_widget(self.chk_ranges)
        nutrition_card.add_widget(self._build_basis_row())
        self.nutrition = NutritionPanel(self._tokens)
        nutrition_card.add_widget(self.nutrition)
        layout.addWidget(nutrition_card)

        # Backtechnik
        self.baking_card = Card("Backtechnik")
        self.lbl_baking = QLabel()
        self.lbl_baking.setWordWrap(True)
        self.baking_card.add_widget(self.lbl_baking)
        layout.addWidget(self.baking_card)

        # Kosten
        self.cost_card = Card("Kosten")
        self.lbl_cost = QLabel()
        self.lbl_cost.setWordWrap(True)
        self.lbl_cost.setTextFormat(Qt.TextFormat.RichText)
        self.cost_card.add_widget(self.lbl_cost)
        layout.addWidget(self.cost_card)

        layout.addStretch(1)
        scroll.setWidget(content)
        return scroll

    def _connect(self) -> None:
        self.btn_add.clicked.connect(self._on_add)
        picker_edit = self.picker.lineEdit()
        if picker_edit is not None:
            picker_edit.returnPressed.connect(self._focus_amount)
        self.spin_amount.editingFinished.connect(self._on_amount_return)
        self.btn_remove.clicked.connect(self._on_remove)
        self.btn_clear.clicked.connect(self.clear)
        self.chk_ranges.toggled.connect(self.nutrition.set_show_ranges)

        self._items_model.dataChanged.connect(lambda *_: self._schedule())
        self._items_model.rowsInserted.connect(lambda *_: self._schedule())
        self._items_model.rowsRemoved.connect(lambda *_: self._schedule())
        self._items_model.modelReset.connect(self._schedule)

        for spin in (
            self.spin_dough,
            self.spin_baked,
            self.spin_kwh,
            self.spin_price,
            self.spin_portion,
        ):
            spin.valueChanged.connect(lambda *_: self._schedule())
        self.cmb_portion.editTextChanged.connect(lambda *_: self._schedule())
        self.rb_per_portion.toggled.connect(lambda *_: self._render_nutrition(self._analysis))

    # ── Zustand ───────────────────────────────────────────────────────────

    @property
    def analysis(self) -> RecipeAnalysis:
        """Aktuelle Auswertung."""
        return self._analysis

    @property
    def recipe_name(self) -> str:
        """Eingetragener Rezeptname, oder ein Ersatzname."""
        return self.txt_name.text().strip() or "Unbenanntes Rezept"

    @property
    def portion(self) -> Portion | None:
        """Eingetragene Portion; ohne Gewicht gibt es keine."""
        weight = self.spin_portion.value()
        if weight <= 0:
            return None
        return Portion(self.cmb_portion.currentText(), weight)

    def set_ingredients(self, ingredients: Sequence[Ingredient]) -> None:
        """Übernimmt eine geänderte Zutatendatenbank.

        Zutaten im aktuellen Rezept werden dabei auf ihre neue Fassung
        umgehängt, damit ein soeben geänderter Preis sofort wirkt.
        """
        self._ingredients = {i.key: i for i in ingredients}
        self.picker.set_ingredients(ingredients)

        refreshed: list[ResolvedItem] = []
        for item in self._items_model.items:
            current = self._ingredients.get(item.ingredient.key, item.ingredient)
            refreshed.append(replace(item, ingredient=current))
        if refreshed:
            self._items_model.set_items(refreshed)
        self._schedule()

    def set_tokens(self, tokens: Tokens) -> None:
        """Übernimmt einen neuen Farbsatz."""
        self._tokens = tokens
        self.nutrition.set_tokens(tokens)

    def load_recipe(self, recipe: Recipe) -> list[RecipeItem]:
        """Lädt ein Rezept in den Rechner.

        Returns:
            Zeilen, zu denen keine Zutat gefunden wurde. Sie werden nicht
            stillschweigend verschluckt, sondern vom Aufrufer gemeldet.
        """
        self.txt_name.setText(recipe.name)
        self.spin_baked.setValue(recipe.baked_weight_g)
        self.spin_dough.setValue(recipe.dough_weight_g)
        self.spin_kwh.setValue(recipe.energy_kwh)
        self._show_portion(recipe.portion)

        resolved: list[ResolvedItem] = []
        missing: list[RecipeItem] = []
        for item in recipe.items:
            ingredient = self._ingredients.get(item.ingredient_key)
            if ingredient is None:
                missing.append(item)
                continue
            resolved.append(ResolvedItem(ingredient, item.amount_g, item.stage))

        self._items_model.set_items(resolved)
        self._recalculate()
        self.mark_saved()
        return missing

    def to_recipe(self) -> Recipe:
        """Baut aus dem aktuellen Zustand ein speicherbares Rezept."""
        return Recipe(
            name=self.recipe_name,
            items=[
                RecipeItem(
                    ingredient_key=item.ingredient.key,
                    name=item.ingredient.name,
                    manufacturer=item.ingredient.manufacturer,
                    amount_g=item.amount_g,
                    stage=item.stage,
                )
                for item in self._items_model.items
            ],
            baked_weight_g=self.spin_baked.value(),
            dough_weight_g=self.spin_dough.value(),
            energy_kwh=self.spin_kwh.value(),
            portion=self.portion,
        )

    def clear(self) -> None:
        """Setzt die Seite in den Ausgangszustand zurück."""
        self._items_model.clear()
        self.txt_name.clear()
        self.spin_baked.setValue(0.0)
        self.spin_dough.setValue(0.0)
        self.spin_kwh.setValue(0.0)
        self._show_portion(None)
        self._recalculate()
        self.mark_saved()

    def _show_portion(self, portion: Portion | None) -> None:
        """Trägt eine Portion ein; ``None`` leert das Gewicht."""
        self.cmb_portion.setEditText(portion.name if portion else SUGGESTED_NAMES[0])
        self.spin_portion.setValue(portion.weight_g if portion else 0.0)

    @property
    def has_unsaved_changes(self) -> bool:
        """Ginge beim Leeren etwas verloren?

        Ein Rechner ohne Zutaten hat nichts zu verlieren - ein Rezept ohne
        Zutaten lässt sich ohnehin nicht speichern.
        """
        return bool(self._items_model.items) and self._state() != self._saved_state

    def mark_saved(self) -> None:
        """Merkt sich den jetzigen Stand als gespeichert."""
        self._saved_state = self._state()

    def _state(self) -> tuple[object, ...]:
        """Fingerabdruck dessen, was ein Speichern festhielte."""
        return (
            self.txt_name.text().strip(),
            tuple(
                (item.ingredient.key, item.amount_g, item.stage) for item in self._items_model.items
            ),
            self.spin_baked.value(),
            self.spin_dough.value(),
            self.spin_kwh.value(),
            self.portion,
        )

    # ── Bedienung ─────────────────────────────────────────────────────────

    def _focus_amount(self) -> None:
        """Enter im Suchfeld springt in die Mengeneingabe."""
        self.spin_amount.setFocus()
        self.spin_amount.selectAll()

    def _on_amount_return(self) -> None:
        if self.spin_amount.value() > 0 and self.picker.current_key():
            self._on_add()

    def _on_add(self) -> None:
        key = self.picker.current_key()
        if key is None:
            self.status_message.emit(
                "Keine eindeutige Zutat gefunden - bitte aus der Vorschlagsliste wählen."
            )
            return
        ingredient = self._ingredients.get(key)
        if ingredient is None:  # pragma: no cover - Datenbank geändert
            self.status_message.emit("Diese Zutat existiert nicht mehr.")
            return

        amount = self.spin_amount.value()
        if amount <= 0:
            self.status_message.emit("Bitte eine Menge größer als 0 g eingeben.")
            self.spin_amount.setFocus()
            return

        self._items_model.add_item(ingredient, amount)
        self.spin_amount.setValue(0.0)
        self.picker.setCurrentIndex(-1)
        self.picker.clearEditText()
        self.picker.setFocus()

    def _on_remove(self) -> None:
        rows = {index.row() for index in self.table.selectionModel().selectedRows()}
        if not rows:
            self.status_message.emit("Bitte zuerst eine Zeile auswählen.")
            return
        self._items_model.remove_rows(sorted(rows))

    # ── Berechnung ────────────────────────────────────────────────────────

    def _schedule(self) -> None:
        """Stößt eine verzögerte Neuberechnung an."""
        self._recalc_timer.start()

    def _recalculate(self) -> None:
        items = self._items_model.items
        self._analysis = analyze(
            items,
            baked_weight_g=self.spin_baked.value(),
            dough_weight_g=self.spin_dough.value(),
            energy_kwh=self.spin_kwh.value(),
            energy_price=self.spin_price.value(),
            portion=self.portion,
        )
        self._items_model.set_analysis(self._analysis)
        self._render(self._analysis)
        self.analysis_changed.emit(self._analysis)

    def _render(self, analysis: RecipeAnalysis) -> None:
        """Überträgt die Auswertung in die rechte Spalte."""
        findings = check_process(analysis)
        self._render_summary(analysis)
        self._render_stats(analysis, findings)

        self._render_nutrition(analysis)
        self.lbl_portion.setText(_portion_text(analysis))

        self.lbl_baking.setText(_baking_text(analysis))
        self.lbl_cost.setText(_cost_html(analysis))
        self._render_process(findings)

    def _render_nutrition(self, analysis: RecipeAnalysis) -> None:
        """Nährwerttafel je 100 g - oder je Portion, wenn so gewählt."""
        portion = analysis.portion
        per_portion = analysis.per_portion
        self.basis_row.setVisible(per_portion is not None)
        if portion is not None:
            self.rb_per_portion.setText(f"je {portion.title}")
        if analysis.is_empty or analysis.baked_weight_g <= 0:
            self.nutrition_card.set_title(_NUTRITION_TITLE)
            self.chk_ranges.setEnabled(True)
            self.nutrition.clear()
            return
        if portion is not None and per_portion is not None and self.rb_per_portion.isChecked():
            basis = f"je {portion.title}"
            self.nutrition_card.set_title(f"Nährwerte {basis}")
            self.chk_ranges.setEnabled(False)
            self.nutrition.update_values(per_portion, basis=basis, levels=analysis.per_100g)
            return
        self.nutrition_card.set_title(_NUTRITION_TITLE)
        self.chk_ranges.setEnabled(True)
        self.nutrition.update_values(analysis.per_100g, analysis.ranges_per_100g)

    def _render_process(self, findings: Sequence[ProcessFinding]) -> None:
        """Zeigt die Befunde der Plausibilitätsprüfung, ohne Befund nichts."""
        self.lbl_process.setVisible(bool(findings))
        self.lbl_process.setText(findings_html(findings, self._tokens))

    def _render_summary(self, analysis: RecipeAnalysis) -> None:
        if analysis.is_empty:
            self.lbl_summary.setText("Noch keine Zutaten - oben eine Zutat auswählen.")
            return
        parts = [
            f"Einwaage {analysis.weighed_mass_g:.0f} g",
            f"Mehl {analysis.flour_mass_g:.0f} g",
            f"Wasser {analysis.water_mass_g:.0f} g",
        ]
        if analysis.dough_yield > 0:
            parts.append(f"TA {analysis.dough_yield:.0f}")
        if abs(analysis.scale_factor - 1.0) > 0.005:
            parts.append(f"Skalierung ×{format_number(analysis.scale_factor, 3)}")
        self.lbl_summary.setText("   ·   ".join(parts))

    def _render_stats(self, analysis: RecipeAnalysis, findings: Sequence[ProcessFinding]) -> None:
        if analysis.is_empty or analysis.baked_weight_g <= 0:
            for card in (self.stat_energy, self.stat_weight, self.stat_yield, self.stat_cost):
                card.set_value("—")
            self.stat_weight.set_value("—", "Gewicht gebacken eintragen")
            return

        self.stat_energy.set_value(
            f"{analysis.per_100g.energy_kcal:.0f} kcal",
            f"{analysis.per_100g.energy_kj:.0f} kJ",
        )
        self.stat_weight.set_value(
            f"{analysis.baked_weight_g:.0f} g",
            "⚠ unmöglich - siehe Backprozess"
            if has_errors(findings)
            else f"Backverlust {format_number(analysis.water_loss_percent, 1)} %",
        )
        yield_hint = (
            f"Hydration {analysis.hydration_percent:.0f} %"
            if analysis.dough_yield
            else "kein Mehl im Rezept"
        )
        self.stat_yield.set_value(
            f"{analysis.dough_yield:.0f}" if analysis.dough_yield else "—", yield_hint
        )
        hint = "" if analysis.has_complete_prices else "unvollständig - Preise fehlen"
        self.stat_cost.set_value(format_currency(analysis.cost_per_kg), hint)


def findings_html(findings: Sequence[ProcessFinding], tokens: Tokens) -> str:
    """Befunde als farbige Liste: Fehler rot, Warnungen orange."""
    items = "".join(
        f"<li style='color:{tokens.danger if f.severity is Severity.ERROR else tokens.warning}'>"
        f"{escape(f.message)}</li>"
        for f in findings
    )
    return f"<ul style='margin:0; padding-left:14px'>{items}</ul>" if items else ""


def _weight_spin(tooltip: str) -> QDoubleSpinBox:
    """Gewichtseingabe in Gramm."""
    spin = QDoubleSpinBox()
    spin.setRange(0.0, 200_000.0)
    spin.setDecimals(0)
    spin.setSuffix(" g")
    spin.setSpecialValueText("—")
    spin.setToolTip(tooltip)
    return spin


def _portion_text(analysis: RecipeAnalysis) -> str:
    """Wie viele Portionen das Brot ergibt - leer, solange es keine sinnvolle Zahl gibt.

    Ist die Portion schwerer als das Brot, sagt das die Plausibilitätsprüfung.
    """
    portion = analysis.portion
    if portion is None or analysis.portion_count is None:
        return ""
    if not portion.fits_into(analysis.baked_weight_g):
        return ""
    return f"ergibt {portion.count_text(analysis.baked_weight_g)}"


def _baking_text(analysis: RecipeAnalysis) -> str:
    """Fließtext zu Teigausbeute und Bäckerprozent."""
    if analysis.is_empty:
        return "Sobald Zutaten eingetragen sind, stehen hier Teigausbeute und Bäckerprozent."
    if analysis.flour_mass_g <= 0:
        return (
            "Keine der Zutaten ist als Mehl markiert - Bäckerprozent und Teigausbeute "
            "lassen sich deshalb nicht berechnen. Die Markierung lässt sich in der "
            "Zutatenverwaltung setzen."
        )

    lines = [
        f"Mehlmenge {analysis.flour_mass_g:.0f} g entspricht 100 % Bäckerprozent. "
        f"Die einzelnen Anteile stehen in der Spalte „Bäcker%“ links.",
        f"Teigausbeute {analysis.dough_yield:.0f} bei "
        f"{analysis.water_mass_g:.0f} g Schüttwasser - {analysis.dough_yield_description}.",
    ]
    salt = sum(line.amount_g * line.ingredient.nutrients.salt / 100.0 for line in analysis.lines)
    if salt > 0:
        lines.append(
            f"Salz {format_number(salt / analysis.flour_mass_g * 100, 1)} % vom Mehl "
            f"({format_number(salt, 1)} g gesamt). Üblich sind 1,8 bis 2,2 %."
        )
    return "\n\n".join(lines)


def _cost_html(analysis: RecipeAnalysis) -> str:
    """Kostenübersicht als kleine HTML-Tabelle."""
    if analysis.is_empty:
        return "Noch keine Zutaten eingetragen."

    rows = [
        ("Materialkosten", format_currency(analysis.material_cost)),
        (
            f"Energie ({format_number(analysis.energy_kwh, 2)} kWh × "
            f"{format_number(analysis.energy_price, 2)} €/kWh)",
            format_currency(analysis.energy_cost),
        ),
        ("<b>Gesamtkosten</b>", f"<b>{format_currency(analysis.total_cost)}</b>"),
        ("Preis je 100 g", format_currency(analysis.cost_per_100g)),
        ("Preis je Kilogramm", format_currency(analysis.cost_per_kg)),
    ]
    if analysis.portion is not None and analysis.cost_per_portion is not None:
        rows.append(
            (
                f"Preis je {escape(analysis.portion.title)}",
                format_currency(analysis.cost_per_portion),
            )
        )
    body = "".join(
        f"<tr><td style='padding:2px 0'>{label}</td>"
        f"<td align='right' style='padding:2px 0'>{value}</td></tr>"
        for label, value in rows
    )
    html = f"<table width='100%' cellspacing='0'>{body}</table>"

    missing = analysis.lines_without_price
    if missing:
        names = ", ".join(line.ingredient.display_name for line in missing)
        html += (
            f"<p style='margin-top:8px'><i>Ohne Preis und daher nicht in der Summe "
            f"enthalten: {names}.</i></p>"
        )
    return html
