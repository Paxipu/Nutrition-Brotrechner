"""Kleine Dialoge: Skalieren, Datenprüfung, Import und Programminfo."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QRadioButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from brotrechner import __author__, __version__
from brotrechner.core.models import Recipe
from brotrechner.core.validation import Finding, Severity
from brotrechner.data.portable import ConflictPolicy, ImportPreview
from brotrechner.export import report
from brotrechner.gui.theme import SPACING, Tokens
from brotrechner.gui.widgets.cards import Card
from brotrechner.i18n import format_number
from brotrechner.logfile import log_path

__all__ = ["AboutDialog", "ImportDialog", "NotesDialog", "ScaleDialog", "ValidationDialog"]

#: Inhaltsbreite des Über-Dialogs in Pixeln.
_ABOUT_WIDTH = 540


def _rich_label(html: str, *, muted: bool = False) -> QLabel:
    """Mehrzeilige Beschriftung mit anklickbaren Verweisen."""
    label = QLabel(html)
    label.setWordWrap(True)
    label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setOpenExternalLinks(True)
    label.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextBrowserInteraction
        | Qt.TextInteractionFlag.LinksAccessibleByMouse
    )
    if muted:
        label.setObjectName("Muted")
    return label


class ScaleDialog(QDialog):
    """Skaliert ein Rezept auf ein neues Zielgewicht.

    Anders als früher lässt sich sowohl über das Zielgewicht als auch direkt
    über den Faktor arbeiten - beide Felder halten sich gegenseitig aktuell.
    """

    def __init__(self, recipe: Recipe, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Rezept skalieren")
        self.setMinimumWidth(420)
        self._recipe = recipe
        self._updating = False

        layout = QVBoxLayout(self)
        layout.setSpacing(SPACING["md"])

        card = Card(recipe.name)
        info = QLabel(
            f"Aktuell {recipe.baked_weight_g:.0f} g gebacken aus "
            f"{recipe.total_amount_g:.0f} g Zutaten."
        )
        info.setObjectName("Muted")
        card.add_widget(info)

        form = QFormLayout()
        form.setSpacing(SPACING["sm"])
        self.spin_target = QDoubleSpinBox()
        self.spin_target.setRange(1.0, 200_000.0)
        self.spin_target.setDecimals(0)
        self.spin_target.setSuffix(" g")
        self.spin_target.setValue(max(1.0, recipe.baked_weight_g))

        self.spin_factor = QDoubleSpinBox()
        self.spin_factor.setRange(0.01, 100.0)
        self.spin_factor.setDecimals(3)
        self.spin_factor.setSingleStep(0.1)
        self.spin_factor.setPrefix("× ")
        self.spin_factor.setValue(1.0)

        form.addRow("Neues Zielgewicht", self.spin_target)
        form.addRow("oder Faktor", self.spin_factor)
        card.body.addLayout(form)

        self.lbl_preview = QLabel()
        self.lbl_preview.setWordWrap(True)
        card.add_widget(self.lbl_preview)
        layout.addWidget(card)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setText("Skaliertes Rezept anlegen")
        ok.setProperty("accent", True)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Abbrechen")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.spin_target.valueChanged.connect(self._on_target_changed)
        self.spin_factor.valueChanged.connect(self._on_factor_changed)
        self._update_preview()

    @property
    def factor(self) -> float:
        """Gewählter Skalierungsfaktor."""
        return self.spin_factor.value()

    def _on_target_changed(self, value: float) -> None:
        if self._updating or self._recipe.baked_weight_g <= 0:
            return
        self._updating = True
        self.spin_factor.setValue(value / self._recipe.baked_weight_g)
        self._updating = False
        self._update_preview()

    def _on_factor_changed(self, value: float) -> None:
        if self._updating:
            return
        self._updating = True
        self.spin_target.setValue(self._recipe.baked_weight_g * value)
        self._updating = False
        self._update_preview()

    def _update_preview(self) -> None:
        factor = self.spin_factor.value()
        lines = [
            f"{item.display_name}: {format_number(item.amount_g, 0)} g → "
            f"<b>{format_number(item.amount_g * factor, 0)} g</b>"
            for item in self._recipe.items[:6]
        ]
        if len(self._recipe.items) > 6:
            lines.append(f"… und {len(self._recipe.items) - 6} weitere")
        self.lbl_preview.setText("<br>".join(lines))


class NotesDialog(QDialog):
    """Notizen zu einem Rezept schreiben und ändern.

    Ein eigener Dialog statt einer einzeiligen Abfrage: Was hier hineingehört -
    was beim letzten Mal schiefging, welcher Kniff geholfen hat - sind mehrere
    Sätze, die man beim Wiederlesen auch wiederfinden können muss.
    """

    def __init__(self, recipe_name: str, notes: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Notizen zum Rezept")
        self.setMinimumSize(520, 380)

        layout = QVBoxLayout(self)
        layout.setSpacing(SPACING["md"])

        card = Card(recipe_name)
        hint = QLabel(
            "Erfahrungen, Kniffe, Abweichungen - alles, was beim nächsten Mal "
            "hilfreich ist. Der Text erscheint in der Rezeptvorschau."
        )
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        card.add_widget(hint)

        self.txt_notes = QPlainTextEdit(notes)
        self.txt_notes.setPlaceholderText(
            "z. B. Teig war zu weich - beim nächsten Mal 30 g Wasser weniger."
        )
        card.add_widget(self.txt_notes, 1)
        layout.addWidget(card, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setText("Übernehmen")
        ok.setProperty("accent", True)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Abbrechen")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.txt_notes.setFocus()

    @property
    def notes(self) -> str:
        """Der eingegebene Text ohne überflüssigen Rand."""
        return self.txt_notes.toPlainText().strip()


class ValidationDialog(QDialog):
    """Zeigt alle Befunde der Datenprüfung als Tabelle."""

    def __init__(
        self, findings: Sequence[Finding], tokens: Tokens, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Datenprüfung")
        self.setMinimumSize(880, 520)
        self._all = list(findings)
        self._tokens = tokens

        layout = QVBoxLayout(self)
        layout.setSpacing(SPACING["md"])

        counts = dict.fromkeys(Severity, 0)
        for finding in self._all:
            counts[finding.severity] += 1
        summary = QLabel(
            f"{counts[Severity.ERROR]} Fehler · {counts[Severity.WARNING]} Warnungen · "
            f"{counts[Severity.INFO]} Hinweise"
        )
        summary.setObjectName("PageTitle")
        layout.addWidget(summary)

        explanation = QLabel(
            "<b>Fehler</b> verletzen eine Bilanz und sind sicher falsch, etwa wenn die "
            "Summe aller Bestandteile über 100 g je 100 g liegt. "
            "<b>Warnungen</b> sind unplausibel, können im Einzelfall aber stimmen. "
            "<b>Hinweise</b> sind rein informativ, zum Beispiel ein fehlender Preis."
        )
        explanation.setWordWrap(True)
        explanation.setObjectName("Muted")
        layout.addWidget(explanation)

        filter_row = QHBoxLayout()
        self.cmb_severity = QComboBox()
        self.cmb_severity.addItem("Fehler und Warnungen", "problems")
        self.cmb_severity.addItem("Nur Fehler", Severity.ERROR)
        self.cmb_severity.addItem("Nur Warnungen", Severity.WARNING)
        self.cmb_severity.addItem("Nur Hinweise", Severity.INFO)
        self.cmb_severity.addItem("Alles", "all")
        filter_row.addWidget(QLabel("Anzeigen:"))
        filter_row.addWidget(self.cmb_severity)
        filter_row.addStretch(1)
        layout.addLayout(filter_row)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Zutat", "Grad", "Feld", "Befund"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("Schließen")
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

        self.cmb_severity.currentIndexChanged.connect(self._refill)
        self._refill()

    def _refill(self) -> None:
        choice = self.cmb_severity.currentData()
        if choice == "all":
            shown = self._all
        elif choice == "problems":
            shown = [f for f in self._all if f.severity is not Severity.INFO]
        else:
            shown = [f for f in self._all if f.severity is choice]

        self.table.setRowCount(len(shown))
        for row, finding in enumerate(shown):
            message = finding.message
            if finding.suggestion is not None:
                message += f"  →  Vorschlag: {format_number(finding.suggestion, 2)}"
            for column, text in enumerate(
                [finding.display_name, finding.severity.label, finding.field, message]
            ):
                item = QTableWidgetItem(text)
                if column == 1:
                    item.setForeground(
                        Qt.GlobalColor.red
                        if finding.severity is Severity.ERROR
                        else Qt.GlobalColor.darkYellow
                        if finding.severity is Severity.WARNING
                        else Qt.GlobalColor.gray
                    )
                self.table.setItem(row, column, item)


class ImportDialog(QDialog):
    """Vorschau eines Zutaten-Imports mit Wahl des Kollisionsverhaltens."""

    def __init__(self, preview: ImportPreview, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Zutaten importieren")
        self.setMinimumWidth(560)
        self._preview = preview

        layout = QVBoxLayout(self)
        layout.setSpacing(SPACING["md"])

        summary = Card("Was importiert wird")
        summary.add_widget(
            QLabel(
                f"<b>{preview.total}</b> Zutaten in der Datei · "
                f"<b>{len(preview.new)}</b> neu · "
                f"<b>{len(preview.conflicting)}</b> bereits vorhanden"
            )
        )
        if preview.new:
            names = ", ".join(i.display_name for i in preview.new[:8])
            more = f" … (+{len(preview.new) - 8})" if len(preview.new) > 8 else ""
            new_label = QLabel(f"Neu: {names}{more}")
            new_label.setWordWrap(True)
            new_label.setObjectName("Muted")
            summary.add_widget(new_label)
        layout.addWidget(summary)

        self._buttons: dict[ConflictPolicy, QRadioButton] = {}
        if preview.has_conflicts:
            conflict_card = Card("Vorhandene Zutaten")
            names = ", ".join(existing.display_name for _, existing in preview.conflicting[:8])
            more = f" … (+{len(preview.conflicting) - 8})" if len(preview.conflicting) > 8 else ""
            detail = QLabel(f"Betroffen: {names}{more}")
            detail.setWordWrap(True)
            detail.setObjectName("Muted")
            conflict_card.add_widget(detail)

            for policy, hint in (
                (ConflictPolicy.SKIP, "Die Datei wird für diese Zutaten ignoriert."),
                (ConflictPolicy.REPLACE, "Eigene Werte werden überschrieben."),
                (
                    ConflictPolicy.KEEP_BOTH,
                    "Die importierte Zutat bekommt eine Ziffer angehängt.",
                ),
            ):
                button = QRadioButton(f"{policy.label} — {hint}")
                self._buttons[policy] = button
                conflict_card.add_widget(button)
            self._buttons[ConflictPolicy.SKIP].setChecked(True)
            layout.addWidget(conflict_card)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setText("Importieren")
        ok.setProperty("accent", True)
        ok.setEnabled(preview.total > 0)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Abbrechen")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def policy(self) -> ConflictPolicy:
        """Gewähltes Verhalten bei Namenskollisionen."""
        for policy, button in self._buttons.items():
            if button.isChecked():
                return policy
        return ConflictPolicy.SKIP


class AboutDialog(QDialog):
    """Programminfo mit Urheberschaft, Lizenz, Datenpfaden und Paketzustand.

    Die GPL verlangt, dass ein Programm mit interaktiver Oberfläche beim
    Anwender einen kurzen Hinweis auf Urheberrecht, fehlende Gewährleistung
    und die Bezugsquelle des Quelltextes zugänglich macht. Genau das leistet
    dieser Dialog; die vollständige Lizenz liegt als Datei ``LICENSE`` bei.
    """

    def __init__(
        self,
        *,
        data_dir: str,
        ingredient_count: int,
        recipe_count: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Über Brotrechner")

        layout = QVBoxLayout(self)
        layout.setSpacing(SPACING["md"])
        # Der Dialog soll genau so hoch werden, wie sein Inhalt es verlangt.
        # Ohne diese Vorgabe rechnet Qt die Höhe umbrochener Rich-Text-Absätze
        # erst nach dem Anzeigen aus und lässt darunter eine leere Fläche.
        layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetFixedSize)

        title = QLabel(f"Brotrechner {__version__}")
        title.setObjectName("PageTitle")
        # Ohne feste Höhe zieht das Layout die Überschrift auseinander und
        # reißt eine Lücke zum Fließtext darunter.
        title.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(title)

        description = _rich_label(
            "Nährwerte, Kosten, Bäckerprozent und Teigausbeute für selbstgebackenes Brot.<br>"
            "Nährwertdeklaration und Toleranzen folgen der VO (EU) Nr. 1169/2011.",
            muted=True,
        )
        layout.addWidget(description)

        origin = Card("Herkunft und Lizenz")
        # Feste Breite: Zusammen mit SetFixedSize bestimmt sie, für welche
        # Zeilenbreite Qt die Höhe der umbrochenen Absätze berechnet.
        origin.setFixedWidth(_ABOUT_WIDTH)
        origin.add_widget(
            _rich_label(
                f"Copyright © 2026 <b>{__author__}</b><br>"
                "Konzept, fachliche Vorgaben und Abnahme: Martin Kraus."
            )
        )
        origin.add_widget(
            _rich_label(
                "<b>Der gesamte Quelltext wurde von Claude (Anthropic) erzeugt.</b> "
                "Kein Teil des Programms ist von Hand geschrieben; die Vorgaben, die "
                "fachlichen Entscheidungen und die Abnahme stammen von Martin Kraus.",
                muted=True,
            )
        )
        origin.add_widget(
            _rich_label(
                "Freigegeben unter der <b>GNU General Public License, Version 3</b> "
                "oder einer späteren Version. Dieses Programm kommt <b>ohne jede "
                "Gewährleistung</b>. Es ist freie Software, und Sie dürfen es unter "
                "den Bedingungen der GPL weitergeben. Der vollständige Lizenztext "
                "liegt als Datei <code>LICENSE</code> bei und steht unter "
                '<a href="https://www.gnu.org/licenses/gpl-3.0.html">'
                "gnu.org/licenses/gpl-3.0.html</a>.",
                muted=True,
            )
        )
        origin.add_widget(
            _rich_label(
                "Quelltext: "
                '<a href="https://github.com/Paxipu/Nutrition-Brotrechner">'
                "github.com/Paxipu/Nutrition-Brotrechner</a>",
                muted=True,
            )
        )
        layout.addWidget(origin)

        facts = Card("Zustand")
        facts.setFixedWidth(_ABOUT_WIDTH)
        facts.add_widget(QLabel(f"{ingredient_count} Zutaten · {recipe_count} Rezepte"))
        path_label = QLabel(
            f"Datenverzeichnis:<br><code>{data_dir}</code><br>"
            f"Protokoll:<br><code>{log_path(Path(data_dir))}</code>"
        )
        path_label.setWordWrap(True)
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        facts.add_widget(path_label)
        facts.add_widget(
            QLabel(
                "PDF-Bericht: "
                + ("verfügbar" if report.is_available() else "nicht verfügbar (reportlab fehlt)")
            )
        )
        layout.addWidget(facts)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close = buttons.button(QDialogButtonBox.StandardButton.Close)
        close.setText("Schließen")
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
