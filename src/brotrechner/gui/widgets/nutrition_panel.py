"""Nährwerttafel je 100 g mit Ampel, Referenzmenge und Toleranzband.

Ersetzt die frühere Monospace-Textausgabe. Der Aufbau folgt der gesetzlichen
Reihenfolge, damit die Tafel unmittelbar mit dem Etikett vergleichbar ist.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QWidget

from brotrechner.core.nutrients import Nutrients
from brotrechner.core.reference import reference_intake_percent, traffic_light
from brotrechner.core.rounding import as_declarable, declare_energy, declare_nutrient
from brotrechner.core.tolerances import ValueRange
from brotrechner.gui.theme import SPACING, Tokens
from brotrechner.gui.widgets.cards import AmpelDot, IntakeBar
from brotrechner.i18n import NUTRIENT_LABELS, NUTRIENT_ORDER, decimals_for, format_number

__all__ = ["NutritionPanel"]

#: Untergeordnete Zeilen der Deklaration ("davon ...").
_INDENTED = frozenset({"saturated_fat", "sugar"})


class NutritionPanel(QWidget):
    """Tabelle der Nährwerte je 100 g."""

    def __init__(self, tokens: Tokens, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._show_ranges = True

        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(SPACING["sm"])
        grid.setVerticalSpacing(SPACING["xs"])
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(4, 2)
        # Die Bezeichnerspalte darf schrumpfen; abgeschnittener Text ist
        # verständlicher als eine Tafel, die aus dem Fenster läuft.
        grid.setColumnMinimumWidth(0, 120)
        self._grid = grid

        headers = ["Nährstoff", "je 100 g", "Bandbreite", "", "% Referenzmenge"]
        for column, text in enumerate(headers):
            label = QLabel(text)
            label.setObjectName("Muted")
            if column in (1, 2):
                label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if column == 2:
                label.setToolTip(
                    "Zulässige Abweichung eines Laborwerts des fertigen Brots\n"
                    "(EU-Toleranzen, Leitlinie der Kommission von 2012)."
                )
            grid.addWidget(label, 0, column)

        self._value_labels: dict[str, QLabel] = {}
        self._range_labels: dict[str, QLabel] = {}
        self._dots: dict[str, AmpelDot] = {}
        self._bars: dict[str, IntakeBar] = {}
        self._percent_labels: dict[str, QLabel] = {}

        for row, field in enumerate(NUTRIENT_ORDER, start=1):
            name = QLabel(NUTRIENT_LABELS[field])
            if field in _INDENTED:
                name.setObjectName("Muted")
                name.setContentsMargins(SPACING["md"], 0, 0, 0)
            grid.addWidget(name, row, 0)

            value = QLabel("-")
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(value, row, 1)
            self._value_labels[field] = value

            band = QLabel("")
            band.setObjectName("Muted")
            band.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(band, row, 2)
            self._range_labels[field] = band

            dot = AmpelDot(tokens)
            grid.addWidget(dot, row, 3)
            self._dots[field] = dot

            cell = QWidget()
            cell_layout = QGridLayout(cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setSpacing(2)
            bar = IntakeBar(tokens)
            percent = QLabel("")
            percent.setObjectName("StatCaption")
            cell_layout.addWidget(bar, 0, 0)
            cell_layout.addWidget(percent, 0, 1)
            grid.addWidget(cell, row, 4)
            self._bars[field] = bar
            self._percent_labels[field] = percent

        self.clear()

    def set_show_ranges(self, show: bool) -> None:
        """Blendet die Toleranzspalte ein oder aus."""
        self._show_ranges = show
        for label in self._range_labels.values():
            label.setVisible(show)
        header = self._grid.itemAtPosition(0, 2)
        header_widget = header.widget() if header is not None else None
        if header_widget is not None:
            header_widget.setVisible(show)

    def set_tokens(self, tokens: Tokens) -> None:
        """Übernimmt einen neuen Farbsatz."""
        self._tokens = tokens
        for dot in self._dots.values():
            dot.set_tokens(tokens)
        for bar in self._bars.values():
            bar.set_tokens(tokens)

    def clear(self) -> None:
        """Setzt alle Zellen auf den Leerzustand."""
        for field in NUTRIENT_ORDER:
            self._value_labels[field].setText("-")
            self._value_labels[field].setToolTip("")
            self._range_labels[field].setText("")
            self._dots[field].set_level(traffic_light(field, 0.0))
            self._bars[field].set_percent(None)
            self._percent_labels[field].setText("")

    def update_values(
        self,
        nutrients: Nutrients,
        ranges: dict[str, ValueRange] | None = None,
    ) -> None:
        """Füllt die Tafel mit einer Auswertung.

        Args:
            nutrients: Nährwerte je 100 g.
            ranges: Toleranzbänder je Feld; ``None`` blendet die Spalte leer.
        """
        ranges = ranges or {}
        for field in NUTRIENT_ORDER:
            value = getattr(nutrients, field)
            self._value_labels[field].setText(_format_value(field, value))
            self._value_labels[field].setToolTip(
                f"Angabe auf dem Etikett: {declared(field, value)}"
            )

            band = ranges.get(field)
            self._range_labels[field].setText(
                _format_range(field, band) if band is not None else ""
            )

            self._dots[field].set_level(traffic_light(field, value))

            percent = reference_intake_percent(field, value)
            self._bars[field].set_percent(percent)
            self._percent_labels[field].setText(f"{percent:.0f} %" if percent is not None else "")
        # Ballaststoffe haben keine EU-Referenzmenge - das muss sichtbar sein.
        self._percent_labels["fiber"].setToolTip(
            "Verglichen mit dem DGE-Richtwert von 30 g je Tag; "
            "eine EU-Referenzmenge gibt es für Ballaststoffe nicht."
        )


def _format_value(field: str, value: float) -> str:
    """Formatiert einen Nährwert samt Einheit - genauer als auf dem Etikett."""
    if field == "energy_kcal":
        return declare_energy(as_declarable(value))
    return f"{format_number(value, decimals_for(field))} g"


def declared(field: str, value: float) -> str:
    """Die gerundete Angabe, wie sie auf dem Etikett steht."""
    if field == "energy_kcal":
        return declare_energy(as_declarable(value))
    return declare_nutrient(field, as_declarable(value)).text


def _format_range(field: str, band: ValueRange) -> str:
    """Formatiert ein Toleranzband kompakt."""
    if field == "energy_kcal":
        return f"{band.minimum:.0f} - {band.maximum:.0f}"
    decimals = decimals_for(field)
    if band.maximum <= 0:
        return ""
    return f"{format_number(band.minimum, decimals)} - {format_number(band.maximum, decimals)}"
