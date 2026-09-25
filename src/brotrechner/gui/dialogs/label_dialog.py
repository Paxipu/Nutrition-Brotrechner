"""Etikett-Vorschau mit Speichern, Speichern unter und Drucken.

Die Vorversion kannte nur einen Knopf, der sofort eine PNG-Datei in einen
festen Ordner schrieb - ohne dass man vorher sah, was entsteht. Hier wird das
Etikett zuerst angezeigt und laufend neu gezeichnet, sobald eine Einstellung
geändert wird. Erst danach entscheidet man, was damit geschehen soll:

* **Speichern** legt die Datei im Standardordner ab,
* **Speichern unter …** öffnet einen Dateidialog,
* **Drucken …** geht direkt in den Druckdialog des Systems - Umweg über eine
  Datei entfällt.

Mit „Etikett für den Verkauf“ prüft der Dialog laufend die Pflichtangaben und
das gezeichnete Etikett. Offene Punkte stehen unter den Einstellungen;
Speichern und Drucken fragen dann nach.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QDate, QRectF, Qt
from PySide6.QtGui import QImage, QPageLayout, QPainter, QPixmap, QResizeEvent
from PySide6.QtPrintSupport import QPrintDialog, QPrinter, QPrintPreviewDialog
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from brotrechner.core.analysis import RecipeAnalysis
from brotrechner.core.labeling import IngredientList, build_ingredient_list, contains_statement
from brotrechner.core.plausibility import check_process
from brotrechner.core.sales import SaleIssue, check_sale
from brotrechner.core.validation import Severity
from brotrechner.export.fonts import load_font_set
from brotrechner.export.label import (
    LabelOptions,
    LabelReport,
    LabelSize,
    LabelTheme,
    render_and_measure,
    render_label,
)
from brotrechner.export.printing import centered
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

#: Ungefähre Auflösung der Bildschirmvorschau. Gezeichnet wird in der
#: Ausgabeauflösung - nur so stimmt die Prüfung mit dem Druck überein - und
#: das Bild dann ganzzahlig auf etwa diese Auflösung verkleinert. Ein
#: 600-dpi-Bild ungekürzt in die Vorschau zu wandeln kostete bis 0,2 s.
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
        # Einmal geladen: Die Schriftgrößen bleiben so über alle Vorschauen
        # hinweg zwischengespeichert.
        self._fonts = load_font_set()

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

        # Einstellungen - in einem Rollbereich, damit Prüfliste und
        # Schaltflächen auch auf kleinen Bildschirmen sichtbar bleiben.
        cards = QVBoxLayout()
        cards.setContentsMargins(0, 0, 0, 0)
        cards.setSpacing(SPACING["md"])

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
        cards.addWidget(settings)

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
            "Zutaten in absteigender Reihenfolge ihres Gewichts, Allergene fett -\n"
            "so verlangt es die Kennzeichnungsverordnung. Ohne Verzeichnis steht\n"
            'stattdessen "Enthält: ..." mit den Allergenen auf dem Etikett.'
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
        cards.addWidget(content)
        cards.addWidget(self._build_sale_card())
        cards.addStretch(1)

        cards_widget = QWidget()
        cards_widget.setLayout(cards)
        scroll = QScrollArea()
        scroll.setWidget(cards_widget)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        side = QVBoxLayout()
        side.setSpacing(SPACING["md"])
        side.addWidget(scroll, 1)

        # Die Farbe richtet sich nach dem Backprozess: Seine Fehler sperren die
        # Ausgabe, alles andere sind Hinweise. Er ändert sich im Dialog nicht.
        self.lbl_issues = QLabel()
        self.lbl_issues.setWordWrap(True)
        self.lbl_issues.setObjectName(
            "Danger"
            if any(f.severity is Severity.ERROR for f in self._process_findings)
            else "Warning"
        )
        self.lbl_issues.setVisible(False)
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
        for line_edit in (self.txt_title, self.txt_subtitle, self.txt_footer, self.txt_storage):
            line_edit.textChanged.connect(self._refresh)
        self.txt_producer.textChanged.connect(self._refresh)
        # Die Auflösung zählt mit: Geprüft wird das Etikett, wie es gedruckt wird.
        for combo in (self.cmb_size, self.cmb_theme, self.cmb_dpi):
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
        self.chk_for_sale.toggled.connect(self._on_for_sale_toggled)
        self.date_baked.dateChanged.connect(self._on_baked_changed)
        self.date_best_before.dateChanged.connect(self._on_best_before_changed)

        self.btn_save.clicked.connect(self._on_save)
        self.btn_save_as.clicked.connect(self._on_save_as)
        self.btn_print.clicked.connect(self._on_print)
        self.btn_preview_print.clicked.connect(self._on_print_preview)
        self.btn_close.clicked.connect(self.reject)

    def _build_sale_card(self) -> Card:
        """Karte „Verkauf“: Schalter, Hersteller und Lagerhinweis."""
        card = Card("Verkauf")
        self.chk_for_sale = QCheckBox("Etikett für den Verkauf")
        self.chk_for_sale.setToolTip(
            "Prüft die Pflichtangaben für verpackt verkauftes Brot nach\n"
            "VO (EU) Nr. 1169/2011: Bezeichnung, Zutatenverzeichnis mit Allergenen,\n"
            "Nettogewicht, Mindesthaltbarkeit, Name und Anschrift - alles in\n"
            "mindestens 1,2 mm x-Höhe. Ersetzt keine Rechtsberatung."
        )
        card.add_widget(self.chk_for_sale)

        self.txt_producer = QPlainTextEdit()
        self.txt_producer.setPlaceholderText(
            "Name und Anschrift, z. B.\nBackstube Muster\nHauptstraße 1\n12345 Musterstadt"
        )
        self.txt_producer.setTabChangesFocus(True)
        # Vier Zeilen - Name, Straße, Ort und Reserve - samt Rahmen und Innenabstand.
        self.txt_producer.setFixedHeight(self.fontMetrics().lineSpacing() * 4 + 12)
        self.txt_producer.setToolTip(
            "Wie eingegeben auf dem Etikett - jede Zeile bleibt eine Zeile."
        )
        self.txt_storage = QLineEdit()
        self.txt_storage.setPlaceholderText("optional, z. B. Trocken lagern.")

        self._sale_form = QFormLayout()
        self._sale_form.setSpacing(SPACING["sm"])
        self._sale_form.addRow("Hersteller", self.txt_producer)
        self._sale_form.addRow("Lagerung", self.txt_storage)
        card.body.addLayout(self._sale_form)
        self._show_sale_fields(visible=False)
        return card

    def _show_sale_fields(self, *, visible: bool) -> None:
        for row in range(self._sale_form.rowCount()):
            self._sale_form.setRowVisible(row, visible)

    def _on_for_sale_toggled(self, checked: bool) -> None:
        """Blendet die Verkaufsangaben ein und setzt, was Pflicht ist.

        Mindesthaltbarkeit und Zutatenverzeichnis werden angehakt - ohne sie
        darf verpacktes Brot nicht verkauft werden. Abwählen bleibt möglich;
        die Prüfliste meldet es dann.
        """
        self._show_sale_fields(visible=checked)
        if checked:
            self.chk_best_before.setChecked(True)
            self.chk_ingredients.setChecked(True)
        self._refresh()

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
        listing = self._ingredient_list()
        for_sale = self.chk_for_sale.isChecked()
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
            ingredients=tuple(entry.markup for entry in listing.entries),
            # Ohne Zutatenverzeichnis müssen die Allergene trotzdem genannt werden.
            allergen_note=(
                "" if self.chk_ingredients.isChecked() else contains_statement(listing.allergens)
            ),
            net_weight_g=self._analysis.baked_weight_g,
            for_sale=for_sale,
            producer=self.txt_producer.toPlainText().strip() if for_sale else "",
            storage_hint=self.txt_storage.text().strip() if for_sale else "",
        )

    def _best_before(self) -> date | None:
        """Mindesthaltbarkeitsdatum, sofern angehakt."""
        if not self.chk_best_before.isChecked():
            return None
        return _to_date(self.date_best_before.date())

    def _ingredient_list(self) -> IngredientList:
        """Zutatenverzeichnis nach LMIV: sortiert, zusammengefasst, Allergene markiert."""
        return build_ingredient_list(
            self._analysis.lines, baked_weight_g=self._analysis.baked_weight_g
        )

    def _refresh(self) -> None:
        """Zeichnet und prüft das Etikett, zeigt Vorschau und offene Punkte."""
        if self._rendering:
            return
        self._rendering = True
        try:
            options = self._options(dpi=self.cmb_dpi.currentData())
            image, report = render_and_measure(self._analysis.per_100g, options, fonts=self._fonts)
            self._show_issues(self._sale_issues(options, report))
            factor = max(1, options.dpi // _PREVIEW_DPI)
            preview = image.reduce(factor) if factor > 1 else image
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

    def _sale_issues(self, options: LabelOptions, report: LabelReport) -> list[SaleIssue]:
        """Offene Punkte: Pflichtangaben im Verkauf, dazu das Etikett selbst."""
        issues: list[SaleIssue] = []
        if options.for_sale:
            issues += check_sale(
                title=self.txt_title.text(),
                producer=options.producer,
                baked_on=options.baked_on,
                best_before=options.best_before,
                show_ingredients=options.show_ingredients,
                listing=self._ingredient_list(),
                net_weight_g=options.net_weight_g,
            )
        return issues + report.issues(for_sale=options.for_sale)

    def _show_issues(self, issues: list[SaleIssue]) -> None:
        """Zeigt Befunde des Backprozesses und offene Punkte unter den Einstellungen."""
        lines = [f.message for f in self._process_findings] + [i.message for i in issues]
        self.lbl_issues.setText("\n".join(f"• {line}" for line in lines))
        self.lbl_issues.setVisible(bool(lines))

    def _update_dimensions(self) -> None:
        options = self._options(dpi=self.cmb_dpi.currentData())
        width, height = options.pixel_size()
        mm_w, mm_h = options.size.millimeters
        self.lbl_dimensions.setText(
            f"{mm_w:.0f} × {mm_h:.0f} mm · {width} × {height} Pixel bei {options.dpi} dpi"
        )

    def _render_output(self) -> Image.Image:
        """Rendert das Etikett in voller Auflösung."""
        return render_label(
            self._analysis.per_100g,
            self._options(dpi=self.cmb_dpi.currentData()),
            fonts=self._fonts,
        )

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

    def _sale_confirmed(self) -> bool:
        """Fragt nach, bevor ein unvollständiges Verkaufsetikett entsteht.

        Geprüft wird neu und in Ausgabeauflösung - maßgeblich ist, was gleich
        gedruckt oder gespeichert wird.
        """
        options = self._options(dpi=self.cmb_dpi.currentData())
        if not options.for_sale:
            return True
        _, report = render_and_measure(self._analysis.per_100g, options, fonts=self._fonts)
        issues = self._sale_issues(options, report)
        if not issues:
            return True
        answer = QMessageBox.question(
            self,
            "Pflichtangaben unvollständig",
            "Für den Verkauf fehlt noch etwas:\n\n"
            + "\n".join(f"• {issue.message}" for issue in issues)
            + "\n\nTrotzdem fortfahren?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return confirmed(answer)

    def _on_save(self) -> None:
        if self._output_blocked() or not self._sale_confirmed():
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
        if self._output_blocked() or not self._sale_confirmed():
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
        """Zeichnet das Etikett in Originalgröße mitten auf die Seite.

        Früher wurde es auf die ganze Seite gestreckt - ein Etikett von
        70 × 100 mm kam auf A4 rund 200 mm breit heraus. Jetzt wird in
        Millimetern ab der Papierkante gerechnet und erst zuletzt mit der
        Auflösung des Druckers in Pixel umgesetzt.
        """
        options = self._options(dpi=self.cmb_dpi.currentData())
        image = pil_to_qimage(render_label(self._analysis.per_100g, options, fonts=self._fonts))
        # Ursprung an der Papierkante statt am bedruckbaren Bereich: Sonst
        # zählte der Druckerrand doppelt, einmal von Qt und einmal hier.
        printer.setFullPage(True)
        paper = printer.pageLayout().fullRect(QPageLayout.Unit.Millimeter)
        placement = centered(options.size.millimeters, (paper.width(), paper.height()))
        painter = QPainter()
        if not painter.begin(printer):  # pragma: no cover - Druckerfehler
            QMessageBox.critical(self, "Drucken", "Der Drucker konnte nicht geöffnet werden.")
            return
        try:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawImage(QRectF(*placement.to_pixels(printer.resolution())), image)
        finally:
            painter.end()

    def _on_print(self) -> None:
        if self._output_blocked() or not self._sale_confirmed():
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
