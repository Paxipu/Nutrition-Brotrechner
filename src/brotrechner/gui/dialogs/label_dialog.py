"""Etikett-Vorschau mit Speichern, Speichern unter und Drucken.

Die Vorversion kannte nur einen Knopf, der sofort eine PNG-Datei in einen
festen Ordner schrieb - ohne dass man vorher sah, was entsteht. Hier wird das
Etikett zuerst angezeigt und laufend neu gezeichnet, sobald eine Einstellung
geändert wird. Erst danach entscheidet man, was damit geschehen soll:

* **Speichern** legt die Datei im Standardordner ab,
* **Speichern unter …** öffnet einen Dateidialog,
* **Drucken …** geht direkt in den Druckdialog des Systems - Umweg über eine
  Datei entfällt.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap, QResizeEvent
from PySide6.QtPrintSupport import QPrintDialog, QPrinter, QPrintPreviewDialog
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from brotrechner.core.analysis import RecipeAnalysis
from brotrechner.core.plausibility import check_process
from brotrechner.core.validation import Severity
from brotrechner.export.label import LabelOptions, LabelSize, LabelTheme, render_label
from brotrechner.gui.qt_compat import confirmed
from brotrechner.gui.theme import SPACING
from brotrechner.gui.widgets.cards import Card

__all__ = ["LabelDialog", "pil_to_qimage"]

#: Auflösungen zur Auswahl. 300 dpi ist der übliche Druckstandard, 150 reicht
#: für Aufkleber vom Tintenstrahler, 600 für Etikettendrucker.
_DPI_CHOICES: tuple[tuple[str, int], ...] = (
    ("150 dpi - Entwurf", 150),
    ("300 dpi - Druckqualität", 300),
    ("600 dpi - Etikettendrucker", 600),
)

#: Auflösung der Bildschirmvorschau. Bewusst niedrig, damit das Neuzeichnen
#: bei jeder Änderung sofort wirkt.
_PREVIEW_DPI = 110

#: Voreingestellte Haltbarkeit eines frisch gebackenen Brots.
_DEFAULT_SHELF_LIFE_DAYS = 7


def _to_date(value: QDate) -> date:
    """Wandelt ein ``QDate`` in ein Python-Datum."""
    return date(value.year(), value.month(), value.day())


def pil_to_qimage(image: Image.Image) -> QImage:
    """Wandelt ein Pillow-Bild in ein ``QImage``.

    Die Kopie am Ende ist wichtig: ``QImage`` übernimmt den Puffer nicht,
    sondern verweist darauf. Ohne ``copy()`` zeigt das Bild auf Speicher, den
    Python jederzeit freigeben darf.
    """
    rgb = image.convert("RGB")
    data = rgb.tobytes("raw", "RGB")
    qimage = QImage(data, rgb.width, rgb.height, rgb.width * 3, QImage.Format.Format_RGB888)
    return qimage.copy()


class LabelDialog(QDialog):
    """Vorschau und Ausgabe des Nährwert-Etiketts."""

    def __init__(
        self,
        analysis: RecipeAnalysis,
        *,
        recipe_name: str,
        default_dir: Path,
        last_baked_on: date | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._analysis = analysis
        self._default_dir = default_dir
        self._last_baked_on = last_baked_on
        # Mit einem unmöglichen Backgewicht stünden falsche Nährwerte auf dem
        # Etikett. Solche Fehler sperren Speichern und Drucken.
        self._process_findings = check_process(analysis)
        # Verhindert eine Rückkopplung: setPixmap ändert den Größenhinweis des
        # Labels, was ein resizeEvent auslösen kann, das erneut zeichnen würde.
        self._rendering = False
        # Haltbarkeit in Tagen. Sie ist die eigentlich gemeinte Größe: Wer die
        # Mindesthaltbarkeit von Hand setzt, legt damit eine Spanne fest, die
        # auch für den nächsten Backtag gelten soll.
        self._shelf_life_days = _DEFAULT_SHELF_LIFE_DAYS
        # Sperre gegen gegenseitiges Auslösen der beiden Datumsfelder.
        self._syncing_dates = False
        # Erst wenn ein Etikett wirklich entstanden ist, gilt der Tag als
        # Backtag. Das bloße Öffnen des Dialogs darf kein Rezept umdatieren.
        self._label_was_created = False

        self.setWindowTitle("Etikett")
        # Die Höhe richtet sich nach der Seitenspalte: Sie muss Gestaltung,
        # Inhalt *und* alle Schaltflächen ungestaucht zeigen können.
        self.setMinimumSize(880, 680)

        self._build_ui(recipe_name)
        self._refresh()

    # ── Ergebnis für den Aufrufer ─────────────────────────────────────────

    @property
    def label_was_created(self) -> bool:
        """Wurde ein Etikett gespeichert oder gedruckt?"""
        return self._label_was_created

    @property
    def baked_on(self) -> date:
        """Das im Dialog eingestellte Backdatum."""
        return _to_date(self.date_baked.date())

    @property
    def best_before(self) -> date | None:
        """Mindesthaltbarkeit, sofern angehakt."""
        return self._best_before()

    # ── Aufbau ────────────────────────────────────────────────────────────

    def _build_ui(self, recipe_name: str) -> None:
        layout = QHBoxLayout(self)
        layout.setSpacing(SPACING["md"])

        # Vorschau
        preview_card = Card("Vorschau")
        self.lbl_preview = QLabel()
        self.lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview.setMinimumSize(320, 320)
        # "Ignored" heißt: Der Inhalt bestimmt die Größe des Labels nicht mit.
        # Ohne das würde jedes neue Vorschaubild das Layout verschieben.
        self.lbl_preview.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        preview_card.add_widget(self.lbl_preview, 1)
        self.lbl_dimensions = QLabel()
        self.lbl_dimensions.setObjectName("Muted")
        self.lbl_dimensions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_card.add_widget(self.lbl_dimensions)
        layout.addWidget(preview_card, 3)

        # Einstellungen
        side = QVBoxLayout()
        side.setSpacing(SPACING["md"])

        settings = Card("Gestaltung")
        form = QFormLayout()
        form.setSpacing(SPACING["sm"])

        self.txt_title = QLineEdit(recipe_name)
        self.txt_subtitle = QLineEdit()
        self.txt_subtitle.setPlaceholderText("optionaler Untertitel")
        self.txt_footer = QLineEdit("Mit Liebe gebacken")

        self.cmb_size = QComboBox()
        for size in LabelSize:
            self.cmb_size.addItem(size.label, size)
        self.cmb_size.setCurrentIndex(list(LabelSize).index(LabelSize.MEDIUM))

        self.cmb_theme = QComboBox()
        for theme in LabelTheme:
            self.cmb_theme.addItem(theme.label, theme)

        self.cmb_dpi = QComboBox()
        for caption, value in _DPI_CHOICES:
            self.cmb_dpi.addItem(caption, value)
        self.cmb_dpi.setCurrentIndex(1)
        self.cmb_dpi.setToolTip("Auflösung der gespeicherten und gedruckten Datei.")

        form.addRow("Titel", self.txt_title)
        form.addRow("Untertitel", self.txt_subtitle)
        form.addRow("Fußzeile", self.txt_footer)
        form.addRow("Format", self.cmb_size)
        form.addRow("Farbe", self.cmb_theme)
        form.addRow("Auflösung", self.cmb_dpi)
        settings.body.addLayout(form)
        side.addWidget(settings)

        content = Card("Inhalt")
        self.chk_date = QCheckBox("Backdatum anzeigen")
        self.chk_date.setChecked(True)

        # Der Kalender beginnt bewusst immer beim heutigen Tag, auch wenn das
        # Rezept zuletzt vor Monaten gebacken wurde: Sonst müsste man sich zum
        # Nachbacken monateweise nach vorn klicken. Der alte Backtag steht
        # stattdessen als Hinweis darunter.
        self.date_baked = QDateEdit(QDate.currentDate())
        self.date_baked.setCalendarPopup(True)
        self.date_baked.setDisplayFormat("dd.MM.yyyy")
        self.date_baked.setToolTip(
            "Tag des Backens. Wird das Etikett später erstellt, hier den\n"
            "tatsächlichen Backtag eintragen."
        )
        self.lbl_last_baked = QLabel()
        self.lbl_last_baked.setObjectName("Muted")
        if self._last_baked_on is not None:
            self.lbl_last_baked.setText(
                f"zuletzt gebacken am {self._last_baked_on.strftime('%d.%m.%Y')}"
            )
        else:
            # Eine leere Beschriftung belegt trotzdem Zeilenhöhe. In der engen
            # Seitenspalte ist das der Platz, der den Schaltflächen fehlt.
            self.lbl_last_baked.setVisible(False)

        self.chk_best_before = QCheckBox("Mindesthaltbarkeitsdatum")
        self.date_best_before = QDateEdit(QDate.currentDate().addDays(_DEFAULT_SHELF_LIFE_DAYS))
        self.date_best_before.setCalendarPopup(True)
        self.date_best_before.setDisplayFormat("dd.MM.yyyy")
        self.date_best_before.setEnabled(False)
        self.date_best_before.setMinimumDate(QDate.currentDate())
        self.date_best_before.setToolTip(
            "Verschiebt sich mit dem Backdatum. Wird es von Hand gesetzt,\n"
            "bleibt die gewählte Spanne auch für den nächsten Backtag erhalten."
        )
        self.chk_ingredients = QCheckBox("Zutatenverzeichnis")
        self.chk_ingredients.setChecked(True)
        self.chk_ingredients.setToolTip(
            "Zutaten in absteigender Reihenfolge ihres Anteils - so verlangt es\n"
            "die Kennzeichnungsverordnung für abgegebene Lebensmittel."
        )
        self.chk_fiber = QCheckBox("Ballaststoffe ausweisen")
        self.chk_fiber.setChecked(True)
        self.chk_reference = QCheckBox("Hinweis auf die Referenzmenge")
        self.chk_reference.setChecked(True)

        for widget in (
            self.chk_date,
            self.date_baked,
            self.lbl_last_baked,
            self.chk_best_before,
            self.date_best_before,
            self.chk_ingredients,
            self.chk_fiber,
            self.chk_reference,
        ):
            content.add_widget(widget)
        side.addWidget(content)
        side.addStretch(1)

        self.lbl_issues = QLabel()
        self.lbl_issues.setWordWrap(True)
        self.lbl_issues.setObjectName(
            "Danger"
            if any(f.severity is Severity.ERROR for f in self._process_findings)
            else "Warning"
        )
        self.lbl_issues.setText("\n".join(f"• {f.message}" for f in self._process_findings))
        self.lbl_issues.setVisible(bool(self._process_findings))
        side.addWidget(self.lbl_issues)

        # Aktionen
        actions = QVBoxLayout()
        actions.setSpacing(SPACING["sm"])
        self.btn_save = QPushButton("Speichern")
        self.btn_save.setProperty("accent", True)
        self.btn_save.setToolTip(f"Legt die Datei in {self._default_dir} ab.")
        self.btn_save_as = QPushButton("Speichern unter …")
        self.btn_print = QPushButton("Drucken …")
        self.btn_preview_print = QPushButton("Druckvorschau …")
        self.btn_close = QPushButton("Schließen")

        for button in (
            self.btn_save,
            self.btn_save_as,
            self.btn_print,
            self.btn_preview_print,
            self.btn_close,
        ):
            actions.addWidget(button)
        side.addLayout(actions)

        holder = QWidget()
        holder.setLayout(side)
        holder.setFixedWidth(320)
        layout.addWidget(holder)

        # Verdrahtung
        for line_edit in (self.txt_title, self.txt_subtitle, self.txt_footer):
            line_edit.textChanged.connect(self._refresh)
        for combo in (self.cmb_size, self.cmb_theme):
            combo.currentIndexChanged.connect(self._refresh)
        for check in (
            self.chk_date,
            self.chk_ingredients,
            self.chk_fiber,
            self.chk_reference,
            self.chk_best_before,
        ):
            check.toggled.connect(self._refresh)
        self.chk_best_before.toggled.connect(self.date_best_before.setEnabled)
        self.chk_date.toggled.connect(self.date_baked.setEnabled)
        self.date_baked.dateChanged.connect(self._on_baked_changed)
        self.date_best_before.dateChanged.connect(self._on_best_before_changed)
        self.cmb_dpi.currentIndexChanged.connect(self._update_dimensions)

        self.btn_save.clicked.connect(self._on_save)
        self.btn_save_as.clicked.connect(self._on_save_as)
        self.btn_print.clicked.connect(self._on_print)
        self.btn_preview_print.clicked.connect(self._on_print_preview)
        self.btn_close.clicked.connect(self.reject)

    # ── Datumskopplung ────────────────────────────────────────────────────

    def _on_baked_changed(self, baked: QDate) -> None:
        """Zieht die Mindesthaltbarkeit mit dem Backdatum mit.

        Die Richtung ist Absicht und gilt nur hier: Das Backdatum bestimmt,
        wann das Brot verdirbt - nicht umgekehrt. Verschoben wird um die
        zuletzt gewählte Haltbarkeitsspanne, damit eine von Hand gesetzte
        Haltbarkeit von zum Beispiel 21 Tagen auch beim nächsten Backtag noch
        21 Tage bedeutet.
        """
        if self._syncing_dates:
            return
        self._syncing_dates = True
        try:
            # Die Untergrenze zuerst: Sonst stutzt Qt den neuen Wert am alten
            # Minimum zurecht, wenn der Backtag nach vorn wandert.
            self.date_best_before.setMinimumDate(baked)
            self.date_best_before.setDate(baked.addDays(self._shelf_life_days))
        finally:
            self._syncing_dates = False
        self._refresh()

    def _on_best_before_changed(self, best_before: QDate) -> None:
        """Merkt sich die von Hand gewählte Haltbarkeitsspanne.

        Das Backdatum bleibt dabei ausdrücklich unangetastet - ein Automatismus
        in diese Richtung würde die eben getroffene Wahl wieder zunichtemachen.
        """
        if self._syncing_dates:
            return
        self._shelf_life_days = max(0, self.date_baked.date().daysTo(best_before))
        self._refresh()

    # ── Optionen und Vorschau ─────────────────────────────────────────────

    def _options(self, *, dpi: int) -> LabelOptions:
        """Baut die Renderoptionen aus den Bedienelementen."""
        return LabelOptions(
            title=self.txt_title.text().strip() or "Hausgemachtes Brot",
            subtitle=self.txt_subtitle.text().strip(),
            size=self.cmb_size.currentData(),
            theme=self.cmb_theme.currentData(),
            dpi=dpi,
            show_date=self.chk_date.isChecked(),
            show_ingredients=self.chk_ingredients.isChecked(),
            show_fiber=self.chk_fiber.isChecked(),
            show_reference_hint=self.chk_reference.isChecked(),
            footer=self.txt_footer.text().strip(),
            best_before=self._best_before(),
            baked_on=_to_date(self.date_baked.date()),
            ingredients=self._ingredient_names(),
            net_weight_g=self._analysis.baked_weight_g,
        )

    def _best_before(self) -> date | None:
        """Mindesthaltbarkeitsdatum, sofern angehakt."""
        if not self.chk_best_before.isChecked():
            return None
        return _to_date(self.date_best_before.date())

    def _ingredient_names(self) -> tuple[str, ...]:
        """Zutatennamen, absteigend nach Anteil sortiert.

        Gleichnamige Zutaten verschiedener Hersteller werden zusammengefasst
        und ihre Mengen addiert. Auf dem Etikett zählt das Lebensmittel, nicht
        die Einkaufsquelle - "Roggenvollkornmehl" dreimal aufzuführen, nur weil
        drei Mühlen im Teig sind, wäre irreführend.
        """
        totals: dict[str, float] = {}
        for line in self._analysis.lines:
            totals[line.ingredient.name] = totals.get(line.ingredient.name, 0.0) + line.amount_g
        return tuple(
            name for name, _ in sorted(totals.items(), key=lambda item: item[1], reverse=True)
        )

    def _refresh(self) -> None:
        """Zeichnet die Vorschau neu."""
        if self._rendering:
            return
        self._rendering = True
        try:
            preview = render_label(self._analysis.per_100g, self._options(dpi=_PREVIEW_DPI))
            pixmap = QPixmap.fromImage(pil_to_qimage(preview))
            box = self.lbl_preview.contentsRect().size()
            self.lbl_preview.setPixmap(
                pixmap.scaled(
                    max(120, box.width()),
                    max(120, box.height()),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            self._update_dimensions()
        finally:
            self._rendering = False

    def _update_dimensions(self) -> None:
        options = self._options(dpi=self.cmb_dpi.currentData())
        width, height = options.pixel_size()
        mm_w, mm_h = options.size.millimeters
        self.lbl_dimensions.setText(
            f"{mm_w:.0f} × {mm_h:.0f} mm · {width} × {height} Pixel bei {options.dpi} dpi"
        )

    def _render_output(self) -> Image.Image:
        """Rendert das Etikett in voller Auflösung."""
        return render_label(self._analysis.per_100g, self._options(dpi=self.cmb_dpi.currentData()))

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt-Vertrag
        """Passt die Vorschau an die neue Fenstergröße an."""
        super().resizeEvent(event)
        self._refresh()

    # ── Ausgabe ───────────────────────────────────────────────────────────

    def _suggested_name(self) -> str:
        """Dateiname aus Titel und Datum, ohne Sonderzeichen."""
        stem = (
            "".join(
                char if char.isalnum() or char in " -_" else "_"
                for char in self.txt_title.text().strip()
            ).strip()
            or "Etikett"
        )
        return f"{stem}_{_to_date(self.date_baked.date()):%Y-%m-%d}.png"

    def _write(self, path: Path) -> bool:
        """Schreibt das Etikett; meldet Fehler statt sie zu verschlucken."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            image = self._render_output()
            dpi = self.cmb_dpi.currentData()
            image.save(path, format="PNG", dpi=(dpi, dpi))
        except (OSError, ValueError) as exc:
            QMessageBox.critical(
                self,
                "Speichern fehlgeschlagen",
                f"{path}\n\nkonnte nicht geschrieben werden:\n{exc}",
            )
            return False
        self._label_was_created = True
        return True

    def _output_blocked(self) -> bool:
        """Verweigert Speichern und Drucken, solange ein Fehler vorliegt."""
        errors = [f for f in self._process_findings if f.severity is Severity.ERROR]
        if not errors:
            return False
        QMessageBox.warning(
            self,
            "Etikett nicht erstellt",
            "Mit diesen Angaben stünden falsche Nährwerte auf dem Etikett:\n\n"
            + "\n".join(f"• {f.message}" for f in errors)
            + "\n\nBitte die Gewichte im Rechner korrigieren.",
        )
        return True

    def _on_save(self) -> None:
        if self._output_blocked():
            return
        path = self._default_dir / self._suggested_name()
        if path.exists():
            answer = QMessageBox.question(
                self,
                "Datei überschreiben?",
                f"{path.name} existiert bereits in\n{path.parent}\n\nÜberschreiben?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if not confirmed(answer):
                return
        if self._write(path):
            QMessageBox.information(self, "Gespeichert", f"Etikett gespeichert:\n{path}")

    def _on_save_as(self) -> None:
        if self._output_blocked():
            return
        target, _ = QFileDialog.getSaveFileName(
            self,
            "Etikett speichern unter",
            str(self._default_dir / self._suggested_name()),
            "PNG-Bild (*.png)",
        )
        if not target:
            return
        path = Path(target)
        if path.suffix.lower() != ".png":
            path = path.with_suffix(".png")
        if self._write(path):
            QMessageBox.information(self, "Gespeichert", f"Etikett gespeichert:\n{path}")

    def _paint_to_printer(self, printer: QPrinter) -> None:
        """Zeichnet das Etikett seitenfüllend und maßstabsgetreu auf die Seite."""
        image = pil_to_qimage(self._render_output())
        painter = QPainter()
        if not painter.begin(printer):  # pragma: no cover - Druckerfehler
            QMessageBox.critical(self, "Drucken", "Der Drucker konnte nicht geöffnet werden.")
            return
        try:
            target = printer.pageRect(QPrinter.Unit.DevicePixel)
            scaled = image.scaled(
                target.size().toSize(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            # Mittig platzieren; ein Etikett soll nicht in der Ecke kleben.
            x = target.x() + (target.width() - scaled.width()) / 2
            y = target.y() + (target.height() - scaled.height()) / 2
            painter.drawImage(int(x), int(y), scaled)
        finally:
            painter.end()

    def _on_print(self) -> None:
        if self._output_blocked():
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle("Etikett drucken")
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._paint_to_printer(printer)
            # Die Druckvorschau zählt bewusst nicht: Erst der wirkliche Druck
            # macht den eingestellten Tag zum Backtag des Rezepts.
            self._label_was_created = True

    def _on_print_preview(self) -> None:
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        preview = QPrintPreviewDialog(printer, self)
        preview.setWindowTitle("Druckvorschau")
        preview.paintRequested.connect(self._paint_to_printer)
        preview.exec()
