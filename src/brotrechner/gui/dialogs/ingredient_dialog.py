"""Dialog zum Anlegen, Bearbeiten und Duplizieren einer Zutat.

Neu gegenüber der Vorversion:

* **Hersteller als eigenes Feld** mit Vorschlagsliste aus dem Bestand.
* **Mehlanteil** in Prozent statt einer versteckten Namensheuristik: 100 %
  bei Mehl, 50 % bei einem Anstellgut mit TA 200.
* **Sofortige Plausibilitätsprüfung**: Unter den Eingaben steht laufend, ob
  Massenbilanz und Brennwert zusammenpassen - der Fehler fällt beim Eintippen
  auf und nicht erst Wochen später in der Auswertung.
* **Preisherkunft und -stand** werden mitgeführt, damit später nachvollziehbar
  bleibt, woher eine Zahl stammt.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from brotrechner.core.models import Category, Ingredient, Source
from brotrechner.core.nutrients import Nutrients, energy_from_macros
from brotrechner.core.validation import Severity, validate_ingredient
from brotrechner.gui.qt_compat import confirmed
from brotrechner.gui.theme import SPACING, Tokens
from brotrechner.gui.widgets.cards import Card
from brotrechner.i18n import NUTRIENT_LABELS, format_number

__all__ = ["IngredientDialog"]

#: Reihenfolge und Einheit der Eingabefelder.
_FIELDS: tuple[tuple[str, str, float, int], ...] = (
    ("energy_kcal", "kcal", 20_000.0, 0),
    ("fat", "g", 100.0, 1),
    ("saturated_fat", "g", 100.0, 1),
    ("carbs", "g", 100.0, 1),
    ("sugar", "g", 100.0, 1),
    ("fiber", "g", 100.0, 1),
    ("protein", "g", 100.0, 1),
    ("salt", "g", 100.0, 2),
    ("water", "%", 100.0, 1),
)


class IngredientDialog(QDialog):
    """Bearbeitet eine Zutat.

    Args:
        tokens: Farbsatz für die Hinweiszeilen.
        ingredient: Zu bearbeitende Zutat; ``None`` legt eine neue an.
        template: Vorlage zum Duplizieren.
        known_manufacturers: Vorschläge für das Hersteller-Feld.
        taken_keys: Bereits vergebene Schlüssel, damit Dubletten beim
            Speichern auffallen statt still zu überschreiben.
        parent: Elternfenster.
    """

    def __init__(
        self,
        tokens: Tokens,
        *,
        ingredient: Ingredient | None = None,
        template: Ingredient | None = None,
        known_manufacturers: Sequence[str] = (),
        taken_keys: Sequence[str] = (),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._original = ingredient
        self._taken = {k for k in taken_keys if ingredient is None or k != ingredient.key}

        self.setWindowTitle("Zutat bearbeiten" if ingredient else "Neue Zutat")
        self.setMinimumWidth(620)

        self._build_ui(known_manufacturers)
        source = ingredient or template
        if source is not None:
            self._fill(source, duplicate=ingredient is None)
        self._update_hints()

    # ── Aufbau ────────────────────────────────────────────────────────────

    def _build_ui(self, known_manufacturers: Sequence[str]) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(SPACING["md"])

        # Stammdaten
        base_card = Card("Bezeichnung")
        form = QFormLayout()
        form.setSpacing(SPACING["sm"])
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("z. B. Roggenvollkornmehl")
        form.addRow("Zutat", self.txt_name)

        self.cmb_manufacturer = QComboBox()
        self.cmb_manufacturer.setEditable(True)
        self.cmb_manufacturer.addItem("")
        self.cmb_manufacturer.addItems(sorted(known_manufacturers))
        self.cmb_manufacturer.setToolTip(
            "Marke oder Handelsmarke. Leer lassen für allgemeine Tabellenwerte.\n"
            "Derselbe Artikel verschiedener Hersteller kann so getrennt gepflegt werden."
        )
        form.addRow("Hersteller", self.cmb_manufacturer)

        self.cmb_category = QComboBox()
        for category in Category:
            self.cmb_category.addItem(category.label, category)
        form.addRow("Kategorie", self.cmb_category)

        self.spin_flour = QDoubleSpinBox()
        self.spin_flour.setRange(0.0, 100.0)
        self.spin_flour.setDecimals(1)
        self.spin_flour.setSingleStep(5.0)
        self.spin_flour.setSuffix(" %")
        self.spin_flour.setToolTip(
            "Anteil der Zutat, der beim Bäckerprozent und bei der Teigausbeute als\n"
            "Mehl zählt: 100 % bei Mehl, 0 % bei Saaten, Milch oder Paniermehl.\n"
            "Sauerteig und Vorteige: 100 / TA × 100 - also 50 % bei TA 200."
        )
        self.lbl_flour_hint = QLabel()
        self.lbl_flour_hint.setObjectName("Muted")
        flour_row = QHBoxLayout()
        flour_row.addWidget(self.spin_flour)
        flour_row.addWidget(self.lbl_flour_hint, 1)
        form.addRow("Mehlanteil", flour_row)
        base_card.body.addLayout(form)
        layout.addWidget(base_card)

        # Nährwerte
        nutrition_card = Card("Nährwerte je 100 g")
        grid = QGridLayout()
        grid.setHorizontalSpacing(SPACING["lg"])
        grid.setVerticalSpacing(SPACING["sm"])
        self._spins: dict[str, QDoubleSpinBox] = {}
        for index, (field, unit, maximum, decimals) in enumerate(_FIELDS):
            row, column = divmod(index, 2)
            label = QLabel(NUTRIENT_LABELS[field])
            spin = QDoubleSpinBox()
            spin.setRange(0.0, maximum)
            spin.setDecimals(decimals)
            spin.setSuffix(f" {unit}")
            spin.setSingleStep(0.1 if decimals else 1.0)
            spin.valueChanged.connect(self._update_hints)
            self._spins[field] = spin
            grid.addWidget(label, row, column * 2)
            grid.addWidget(spin, row, column * 2 + 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        nutrition_card.body.addLayout(grid)

        self.lbl_energy_hint = QLabel()
        self.lbl_energy_hint.setWordWrap(True)
        self.btn_apply_energy = QLabel()
        nutrition_card.add_widget(self.lbl_energy_hint)
        layout.addWidget(nutrition_card)

        # Preis
        price_card = Card("Preis")
        price_form = QGridLayout()
        price_form.setHorizontalSpacing(SPACING["lg"])
        price_form.setVerticalSpacing(SPACING["sm"])

        self.spin_price = QDoubleSpinBox()
        self.spin_price.setRange(0.0, 10_000.0)
        self.spin_price.setDecimals(2)
        self.spin_price.setSuffix(" €")
        self.spin_size = QDoubleSpinBox()
        self.spin_size.setRange(0.0, 1_000_000.0)
        self.spin_size.setDecimals(0)
        self.spin_size.setSuffix(" g")
        self.spin_size.setToolTip(
            "Inhalt der Packung in Gramm. Bei Flüssigkeiten die Milliliter mit der\n"
            "Dichte umrechnen - 1 l Öl wiegt rund 920 g."
        )
        self.txt_price_source = QLineEdit()
        self.txt_price_source.setPlaceholderText("z. B. Aldi Süd, Kassenbon")
        self.date_price = QDateEdit()
        self.date_price.setCalendarPopup(True)
        self.date_price.setDisplayFormat("dd.MM.yyyy")
        self.date_price.setDate(QDate.currentDate())

        price_form.addWidget(QLabel("Packungspreis"), 0, 0)
        price_form.addWidget(self.spin_price, 0, 1)
        price_form.addWidget(QLabel("Packungsgröße"), 0, 2)
        price_form.addWidget(self.spin_size, 0, 3)
        price_form.addWidget(QLabel("Preisquelle"), 1, 0)
        price_form.addWidget(self.txt_price_source, 1, 1)
        price_form.addWidget(QLabel("Preisstand"), 1, 2)
        price_form.addWidget(self.date_price, 1, 3)
        price_form.setColumnStretch(1, 1)
        price_form.setColumnStretch(3, 1)
        price_card.body.addLayout(price_form)

        self.lbl_unit_price = QLabel()
        self.lbl_unit_price.setObjectName("Muted")
        price_card.add_widget(self.lbl_unit_price)
        self.spin_price.valueChanged.connect(self._update_hints)
        self.spin_size.valueChanged.connect(self._update_hints)
        layout.addWidget(price_card)

        # Notizen
        notes_card = Card("Notiz")
        self.txt_notes = QPlainTextEdit()
        self.txt_notes.setPlaceholderText("Woher stammen die Werte? Besonderheiten des Produkts?")
        self.txt_notes.setFixedHeight(64)
        notes_card.add_widget(self.txt_notes)
        layout.addWidget(notes_card)

        # Befunde
        self.lbl_findings = QLabel()
        self.lbl_findings.setWordWrap(True)
        self.lbl_findings.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.lbl_findings)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        save = buttons.button(QDialogButtonBox.StandardButton.Save)
        save.setText("Speichern")
        save.setProperty("accent", True)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Abbrechen")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.txt_name.textChanged.connect(self._update_hints)
        self.cmb_manufacturer.currentTextChanged.connect(self._update_hints)
        self.cmb_category.currentIndexChanged.connect(self._update_hints)
        self.spin_flour.valueChanged.connect(self._update_hints)

    # ── Befüllen und Auslesen ─────────────────────────────────────────────

    def _fill(self, ingredient: Ingredient, *, duplicate: bool) -> None:
        self.txt_name.setText(f"{ingredient.name} (Kopie)" if duplicate else ingredient.name)
        self.cmb_manufacturer.setCurrentText(ingredient.manufacturer)
        index = self.cmb_category.findData(ingredient.category)
        if index >= 0:
            self.cmb_category.setCurrentIndex(index)
        self.spin_flour.setValue(ingredient.flour_percent)

        for field, spin in self._spins.items():
            spin.setValue(float(getattr(ingredient.nutrients, field)))

        self.spin_price.setValue(ingredient.package_price)
        self.spin_size.setValue(ingredient.package_size_g)
        self.txt_price_source.setText(ingredient.price_source)
        if ingredient.price_updated:
            stand = ingredient.price_updated
            self.date_price.setDate(QDate(stand.year, stand.month, stand.day))
        self.txt_notes.setPlainText(ingredient.notes)

    def _current_nutrients(self) -> Nutrients:
        return Nutrients(**{field: spin.value() for field, spin in self._spins.items()})

    def _build_ingredient(self) -> Ingredient:
        """Baut die Zutat aus den Eingaben; verändert das Original nicht."""
        category = self.cmb_category.currentData() or Category.OTHER
        return Ingredient(
            name=self.txt_name.text().strip(),
            manufacturer=self.cmb_manufacturer.currentText().strip(),
            category=category,
            nutrients=self._current_nutrients(),
            flour_percent=self.spin_flour.value(),
            package_price=self.spin_price.value(),
            package_size_g=self.spin_size.value(),
            price_source=self.txt_price_source.text().strip(),
            price_updated=self._price_date(),
            nutrition_source=(
                self._original.nutrition_source if self._original else Source.UNKNOWN
            ),
            water_source=Source.ESTIMATED,
            notes=self.txt_notes.toPlainText().strip(),
        )

    def _price_date(self) -> date:
        """Preisstand als ``datetime.date``.

        ``QDate.toPython`` ist untypisiert; die Umrechnung über die Einzelteile
        ist eindeutig und unabhängig von der Qt-Version.
        """
        qdate = self.date_price.date()
        return date(qdate.year(), qdate.month(), qdate.day())

    def result_ingredient(self) -> Ingredient:
        """Die bearbeitete Zutat.

        Beim Bearbeiten wird das Original weitergeführt, damit die Preishistorie
        erhalten bleibt und ein Preiswechsel dort landet.
        """
        built = self._build_ingredient()
        if self._original is None:
            return built

        target = self._original
        target.name = built.name
        target.manufacturer = built.manufacturer
        target.category = built.category
        target.nutrients = built.nutrients
        target.flour_percent = built.flour_percent
        target.notes = built.notes
        target.update_price(
            built.package_price,
            built.package_size_g,
            source=built.price_source,
            today=built.price_updated or date.today(),
        )
        return target

    # ── Rückmeldung ───────────────────────────────────────────────────────

    def _update_hints(self) -> None:
        """Aktualisiert Mehlanteil-, Brennwert-, Preis- und Befundzeile."""
        self.lbl_flour_hint.setText(flour_share_hint(self.spin_flour.value()))
        nutrients = self._current_nutrients()

        computed = energy_from_macros(nutrients)
        declared = nutrients.energy_kcal
        difference = declared - computed
        if declared == 0 and computed > 0:
            text = (
                f"Aus den Nährstoffen berechnet: <b>{computed:.0f} kcal</b> je 100 g "
                f"(Anhang XIV VO (EU) Nr. 1169/2011)."
            )
            colour = self._tokens.text_muted
        elif abs(difference) > max(12.0, computed * 0.12):
            text = (
                f"Der Brennwert passt nicht zu den Nährstoffen: berechnet "
                f"<b>{computed:.0f} kcal</b>, eingetragen {declared:.0f} kcal "
                f"({difference:+.0f})."
            )
            colour = self._tokens.warning
        else:
            text = f"Brennwert schlüssig (berechnet {computed:.0f} kcal)."
            colour = self._tokens.text_muted
        self.lbl_energy_hint.setText(f"<span style='color:{colour}'>{text}</span>")

        if self.spin_size.value() > 0 and self.spin_price.value() > 0:
            per_100 = self.spin_price.value() / self.spin_size.value() * 100
            per_kg = per_100 * 10
            self.lbl_unit_price.setText(
                f"Entspricht {format_number(per_100, 3)} € je 100 g "
                f"bzw. {format_number(per_kg, 2)} € je Kilogramm."
            )
        else:
            self.lbl_unit_price.setText("Ohne Preis und Packungsgröße bleibt die Zutat kostenlos.")

        self._render_findings()

    def _render_findings(self) -> None:
        """Zeigt Fehler und Warnungen der Prüfung an."""
        if not self.txt_name.text().strip():
            self.lbl_findings.setText("")
            return

        findings = [
            f
            for f in validate_ingredient(self._build_ingredient())
            if f.severity is not Severity.INFO and f.code != "energy"
        ]
        if not findings:
            self.lbl_findings.setText("")
            return

        items = "".join(f"<li><b>{f.severity.label}:</b> {f.message}</li>" for f in findings[:4])
        colour = (
            self._tokens.danger
            if any(f.severity is Severity.ERROR for f in findings)
            else self._tokens.warning
        )
        self.lbl_findings.setText(
            f"<div style='color:{colour}'><ul style='margin:0'>{items}</ul></div>"
        )

    # ── Speichern ─────────────────────────────────────────────────────────

    def _on_accept(self) -> None:
        """Prüft die Eingaben, bevor der Dialog schließt."""
        name = self.txt_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Name fehlt", "Bitte einen Namen für die Zutat eingeben.")
            self.txt_name.setFocus()
            return

        candidate = self._build_ingredient()
        if candidate.key in self._taken:
            QMessageBox.warning(
                self,
                "Bereits vorhanden",
                f"„{candidate.display_name}“ gibt es schon.\n\n"
                "Bitte den Namen ändern oder einen Hersteller angeben, um die "
                "Einträge zu unterscheiden.",
            )
            self.txt_name.setFocus()
            return

        if self.spin_price.value() > 0 and self.spin_size.value() <= 0:
            QMessageBox.warning(
                self,
                "Packungsgröße fehlt",
                "Zu einem Preis gehört eine Packungsgröße - sonst lässt sich der "
                "Preis je 100 g nicht berechnen.",
            )
            self.spin_size.setFocus()
            return

        errors = [
            f
            for f in validate_ingredient(candidate)
            if f.severity is Severity.ERROR and f.code != "duplicate"
        ]
        if errors:
            details = "\n".join(f"• {f.message}" for f in errors)
            answer = QMessageBox.question(
                self,
                "Werte sind widersprüchlich",
                f"Die Prüfung meldet:\n\n{details}\n\nTrotzdem speichern?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if not confirmed(answer, QMessageBox.StandardButton.Save):
                return

        self.accept()


def flour_share_hint(percent: float) -> str:
    """Erklärt einen Mehlanteil in Bäckersprache.

    Bei einem Teilanteil steht die Teigausbeute daneben, mit der ein Vorteig
    aus Mehl und Wasser genau diesen Anteil hätte - das ist die Zahl, die man
    aus dem Rezept kennt.
    """
    if percent <= 0.0:
        return "zählt nicht als Mehl"
    if percent >= 100.0:
        return "zählt vollständig als Mehl"
    return f"entspricht einem Vorteig mit TA {10_000.0 / percent:.0f}"
