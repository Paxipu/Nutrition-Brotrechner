"""Karte „Druck“ im Etikettdialog: Druckart, Anzahl und Bogenraster.

Die Karte kennt nur Einstellungen und die daraus folgende Lage der Etiketten
(:mod:`brotrechner.export.printing`). Ob und wie gedruckt wird, entscheidet
der Dialog.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QWidget,
)

from brotrechner.export.printing import (
    A4_MM,
    Placement,
    PrintMode,
    SheetLayout,
    fitted_sheet,
    one_per_page,
    sheet_placements,
)
from brotrechner.gui.theme import SPACING
from brotrechner.gui.widgets.cards import Card

__all__ = ["PrintSettingsCard"]

#: Höchstzahl an Etiketten in einem Druckauftrag - ein Tippfehler wie 5000
#: statt 50 soll nicht hundert Bögen verschwenden.
MAX_COUNT = 500


class PrintSettingsCard(Card):
    """Wie das Etikett aufs Papier kommt.

    Signals:
        changed: Eine Einstellung hat sich geändert.
    """

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Druck", parent)
        self.cmb_mode = QComboBox()
        for mode in PrintMode:
            self.cmb_mode.addItem(mode.label, mode)
        self.cmb_mode.setToolTip(
            "Einzeln: ein Etikett mitten auf jedem Blatt.\n"
            "Etikettendrucker: je Etikett eine Seite in Etikettgröße.\n"
            "Etikettenbogen: Raster nach den Maßen auf der Verpackung.\n"
            "Mehrere auf A4: so viele, wie auf ein Blatt passen, zum Ausschneiden."
        )
        self.spin_count = QSpinBox()
        self.spin_count.setRange(1, MAX_COUNT)
        self.spin_count.setToolTip("Wie viele Etiketten gedruckt werden.")

        self.chk_rotate = QCheckBox("um 90° gedreht")
        self.chk_rotate.setToolTip(
            "Für Etikettendrucker, die das Etikett quer einziehen - die Seite\n"
            "ist dann so breit, wie das Etikett hoch ist."
        )

        self.spin_columns = _count_spin(1, 12, 2, "Etiketten nebeneinander")
        self.spin_rows = _count_spin(1, 40, 4, "Etiketten untereinander")
        self.spin_margin_left = _distance_spin("Rand links bis zum ersten Etikett")
        self.spin_margin_top = _distance_spin("Rand oben bis zum ersten Etikett")
        self.spin_gap_x = _distance_spin("Abstand zwischen zwei Etiketten nebeneinander")
        self.spin_gap_y = _distance_spin("Abstand zwischen zwei Etiketten untereinander")
        self.spin_first = QSpinBox()
        self.spin_first.setToolTip(
            "Erstes freies Etikett auf dem Bogen, zeilenweise von links oben gezählt -\n"
            "so lässt sich ein angebrochener Bogen weiterverwenden."
        )

        self.lbl_summary = QLabel()
        self.lbl_summary.setObjectName("Muted")
        self.lbl_summary.setWordWrap(True)

        self._form = QFormLayout()
        self._form.setSpacing(SPACING["sm"])
        self._form.addRow("Druckart", self.cmb_mode)
        self._form.addRow("Anzahl", self.spin_count)
        self._form.addRow("", self.chk_rotate)
        # Maße je in eine eigene Zeile: Zwei Felder mit "mm" nebeneinander
        # passen nicht in die schmale Seitenspalte.
        self._grid_row = _pair(self.spin_columns, "×", self.spin_rows)
        self._sheet_rows: tuple[QWidget, ...] = (
            self._grid_row,
            self.spin_margin_left,
            self.spin_margin_top,
            self.spin_gap_x,
            self.spin_gap_y,
            self.spin_first,
        )
        self._form.addRow("Raster", self._grid_row)
        self._form.addRow("Rand links", self.spin_margin_left)
        self._form.addRow("Rand oben", self.spin_margin_top)
        self._form.addRow("Abstand ↔", self.spin_gap_x)
        self._form.addRow("Abstand ↕", self.spin_gap_y)
        self._form.addRow("Beginnen bei", self.spin_first)
        self.body.addLayout(self._form)
        self.add_widget(self.lbl_summary)

        self.cmb_mode.currentIndexChanged.connect(self._on_changed)
        self.chk_rotate.toggled.connect(self._on_changed)
        for spin in (self.spin_count, self.spin_columns, self.spin_rows, self.spin_first):
            spin.valueChanged.connect(self._on_changed)
        for distance in (
            self.spin_margin_left,
            self.spin_margin_top,
            self.spin_gap_x,
            self.spin_gap_y,
        ):
            distance.valueChanged.connect(self._on_changed)
        self._update_fields()

    # ── Einstellungen ─────────────────────────────────────────────────────

    def mode(self) -> PrintMode:
        """Die gewählte Druckart."""
        mode = self.cmb_mode.currentData()
        return mode if isinstance(mode, PrintMode) else PrintMode.SINGLE

    def rotated(self) -> bool:
        """Am Etikettendrucker um 90° gedreht?"""
        return self.mode() == PrintMode.LABEL_PRINTER and self.chk_rotate.isChecked()

    def sheet_layout(self) -> SheetLayout:
        """Das eingestellte Raster des Etikettenbogens."""
        return SheetLayout(
            columns=self.spin_columns.value(),
            rows=self.spin_rows.value(),
            margin_left_mm=self.spin_margin_left.value(),
            margin_top_mm=self.spin_margin_top.value(),
            gap_x_mm=self.spin_gap_x.value(),
            gap_y_mm=self.spin_gap_y.value(),
        )

    def layout_for(self, label_mm: tuple[float, float]) -> SheetLayout | None:
        """Das Raster der Druckart - ``None``, wenn je Seite ein Etikett steht."""
        if self.mode() == PrintMode.SHEET:
            return self.sheet_layout()
        if self.mode() == PrintMode.CUT_SHEET:
            return fitted_sheet(label_mm)
        return None

    def placements(
        self, label_mm: tuple[float, float], paper_mm: tuple[float, float]
    ) -> list[Placement]:
        """Wo die Etiketten landen.

        Args:
            label_mm: Breite und Höhe des Etiketts.
            paper_mm: Das Papier im Drucker - maßgeblich, wenn je Seite ein
                Etikett mittig steht. Ein Bogenraster rechnet ab der linken
                oberen Papierkante.
        """
        count = self.spin_count.value()
        layout = self.layout_for(label_mm)
        if layout is None:
            return one_per_page(label_mm, paper_mm, count=count, rotated=self.rotated())
        first = self.spin_first.value() if self.mode() == PrintMode.SHEET else 1
        return sheet_placements(layout, label_mm, count=count, first=first)

    def problems(self, label_mm: tuple[float, float]) -> list[str]:
        """Was dem Druck im Weg steht - leer, wenn alles aufs Papier passt."""
        layout = self.layout_for(label_mm)
        return [] if layout is None else layout.problems(label_mm)

    def update_summary(self, label_mm: tuple[float, float]) -> None:
        """Zeigt, was gedruckt wird - oder was am Raster nicht stimmt."""
        problems = self.problems(label_mm)
        if problems:
            self.lbl_summary.setText("\n".join(problems))
            return
        layout = self.layout_for(label_mm)
        count = self.spin_count.value()
        if layout is None:
            unit = "Seite" if self.mode() == PrintMode.LABEL_PRINTER else "Blatt"
            self.lbl_summary.setText(f"{_labels(count)}, eines je {unit}")
            return
        pages = self.placements(label_mm, A4_MM)[-1].page + 1
        # Dativ: auf einem Bogen / Blatt, auf zwei Bögen / Blättern.
        sheet, sheets = (
            ("Bogen", "Bögen") if self.mode() == PrintMode.SHEET else ("Blatt", "Blättern")
        )
        self.lbl_summary.setText(
            f"{_labels(count)} auf {pages} {sheet if pages == 1 else sheets} "
            f"({layout.per_page} je {sheet})"
        )

    # ── Intern ────────────────────────────────────────────────────────────

    def _on_changed(self) -> None:
        self._update_fields()
        self.changed.emit()

    def _update_fields(self) -> None:
        """Zeigt nur die Felder der gewählten Druckart."""
        mode = self.mode()
        sheet = mode == PrintMode.SHEET
        self._form.setRowVisible(self.chk_rotate, mode == PrintMode.LABEL_PRINTER)
        for row in self._sheet_rows:
            self._form.setRowVisible(row, sheet)
        # Das erste freie Etikett muss auf dem Bogen liegen.
        self.spin_first.setRange(1, max(1, self.spin_columns.value() * self.spin_rows.value()))


def _labels(count: int) -> str:
    return "1 Etikett" if count == 1 else f"{count} Etiketten"


def _count_spin(low: int, high: int, value: int, tooltip: str) -> QSpinBox:
    spin = QSpinBox()
    spin.setRange(low, high)
    spin.setValue(value)
    spin.setToolTip(tooltip)
    return spin


def _distance_spin(tooltip: str) -> QDoubleSpinBox:
    """Ein Maß auf dem Bogen in Millimetern."""
    spin = QDoubleSpinBox()
    spin.setRange(0.0, 150.0)
    spin.setDecimals(1)
    spin.setSingleStep(0.5)
    spin.setSuffix(" mm")
    spin.setToolTip(tooltip)
    return spin


def _pair(first: QWidget, separator: str, second: QWidget) -> QWidget:
    """Zwei Eingaben nebeneinander in einer Formularzeile."""
    holder = QWidget()
    row = QHBoxLayout(holder)
    row.setContentsMargins(0, 0, 0, 0)
    row.addWidget(first, 1)
    row.addWidget(QLabel(separator))
    row.addWidget(second, 1)
    return holder
