"""Die kleinen Dialoge: Skalieren, Notizen, Datenprüfung und Import."""

from __future__ import annotations

from typing import Any

import pytest

from brotrechner.core.models import Ingredient, Recipe, RecipeItem
from brotrechner.core.validation import Finding, Severity
from brotrechner.data.portable import ConflictPolicy, ImportPreview

pytestmark = pytest.mark.gui


def _recipe(count: int = 3, baked: float = 800.0) -> Recipe:
    return Recipe(
        name="Mischbrot",
        items=[RecipeItem(f"k{i}", f"Zutat {i}", "", 100.0 * (i + 1)) for i in range(count)],
        baked_weight_g=baked,
    )


class TestScaleDialog:
    @pytest.fixture
    def make(self, qapp: object):  # type: ignore[no-untyped-def]
        del qapp
        from brotrechner.gui.dialogs.simple_dialogs import ScaleDialog

        created: list[Any] = []

        def build(recipe: Recipe) -> Any:
            dialog = ScaleDialog(recipe)
            created.append(dialog)
            return dialog

        yield build
        for dialog in created:
            dialog.close()

    def test_it_starts_with_the_recipe(self, make: Any) -> None:
        dialog = make(_recipe())
        assert dialog.factor == 1.0
        assert dialog.spin_target.value() == 800.0

    def test_a_target_weight_sets_the_factor(self, make: Any) -> None:
        dialog = make(_recipe())
        dialog.spin_target.setValue(1200.0)
        assert dialog.factor == pytest.approx(1.5)

    def test_a_factor_sets_the_target_weight(self, make: Any) -> None:
        dialog = make(_recipe())
        dialog.spin_factor.setValue(0.5)
        assert dialog.spin_target.value() == pytest.approx(400.0)

    def test_the_preview_shows_the_new_amounts(self, make: Any) -> None:
        dialog = make(_recipe())
        dialog.spin_factor.setValue(2.0)
        assert "Zutat 0: 100 g → <b>200 g</b>" in dialog.lbl_preview.text()

    def test_a_long_recipe_is_shortened(self, make: Any) -> None:
        dialog = make(_recipe(count=9))
        text = dialog.lbl_preview.text()
        assert "Zutat 5" in text
        assert "Zutat 6" not in text
        assert "… und 3 weitere" in text

    def test_without_a_baked_weight_the_factor_stays(self, make: Any) -> None:
        """Ohne Bezugsgewicht gibt es aus dem Zielgewicht keinen Faktor."""
        dialog = make(_recipe(baked=0.0))
        dialog.spin_target.setValue(500.0)
        assert dialog.factor == 1.0


class TestNotesDialog:
    def test_the_notes_are_shown_and_trimmed(self, qapp: object) -> None:
        del qapp
        from brotrechner.gui.dialogs.simple_dialogs import NotesDialog

        dialog = NotesDialog("Roggenbrot", "Ofen heißer")
        assert dialog.txt_notes.toPlainText() == "Ofen heißer"
        dialog.txt_notes.setPlainText("  Teig zu weich\n\n")
        assert dialog.notes == "Teig zu weich"
        dialog.close()


def _finding(severity: Severity, message: str, suggestion: float | None = None) -> Finding:
    return Finding("k", "Mehl", "water", "code", severity, message, suggestion)


class TestValidationDialog:
    FINDINGS = (
        _finding(Severity.ERROR, "Bilanz verletzt", 12.5),
        _finding(Severity.WARNING, "Wasser ungewöhnlich"),
        _finding(Severity.INFO, "Kein Preis"),
    )

    @pytest.fixture
    def dialog(self, qapp: object):  # type: ignore[no-untyped-def]
        del qapp
        from brotrechner.gui.dialogs.simple_dialogs import ValidationDialog
        from brotrechner.gui.theme import ThemeMode, resolve_tokens

        widget = ValidationDialog(self.FINDINGS, resolve_tokens(ThemeMode.LIGHT))
        yield widget
        widget.close()

    def _messages(self, dialog: Any) -> list[str]:
        return [dialog.table.item(row, 3).text() for row in range(dialog.table.rowCount())]

    def _show(self, dialog: Any, data: object) -> None:
        from brotrechner.gui.qt_compat import select_data

        assert select_data(dialog.cmb_severity, data)

    def test_problems_first(self, dialog: Any) -> None:
        assert self._messages(dialog) == [
            "Bilanz verletzt  →  Vorschlag: 12,50",
            "Wasser ungewöhnlich",
        ]

    def test_everything(self, dialog: Any) -> None:
        self._show(dialog, "all")
        assert len(self._messages(dialog)) == 3

    def test_only_hints(self, dialog: Any) -> None:
        self._show(dialog, Severity.INFO)
        assert self._messages(dialog) == ["Kein Preis"]

    def test_errors_are_red(self, dialog: Any) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QColor

        grade = dialog.table.item(0, 1)
        assert grade.text() == Severity.ERROR.label
        assert grade.foreground().color() == QColor(Qt.GlobalColor.red)

    def test_the_counts(self, qapp: object) -> None:
        del qapp
        from PySide6.QtWidgets import QLabel

        from brotrechner.gui.dialogs.simple_dialogs import ValidationDialog
        from brotrechner.gui.theme import ThemeMode, resolve_tokens

        widget = ValidationDialog(self.FINDINGS, resolve_tokens(ThemeMode.LIGHT))
        texts = [label.text() for label in widget.findChildren(QLabel)]
        assert "1 Fehler · 1 Warnungen · 1 Hinweise" in texts
        widget.close()


class TestImportDialog:
    @pytest.fixture
    def make(self, qapp: object):  # type: ignore[no-untyped-def]
        del qapp
        from brotrechner.gui.dialogs.simple_dialogs import ImportDialog

        created: list[Any] = []

        def build(preview: ImportPreview) -> Any:
            dialog = ImportDialog(preview)
            created.append(dialog)
            return dialog

        yield build
        for dialog in created:
            dialog.close()

    @staticmethod
    def _ok(dialog: Any) -> Any:
        from PySide6.QtWidgets import QDialogButtonBox

        box = dialog.findChild(QDialogButtonBox)
        return box.button(QDialogButtonBox.StandardButton.Ok)

    @staticmethod
    def _labels(dialog: Any) -> str:
        from PySide6.QtWidgets import QLabel

        return " ".join(label.text() for label in dialog.findChildren(QLabel))

    def test_only_new_ingredients(self, make: Any) -> None:
        new = tuple(Ingredient(name=f"Neu {i}") for i in range(10))
        dialog = make(ImportPreview(new=new))
        assert dialog.policy is ConflictPolicy.SKIP
        assert self._ok(dialog).isEnabled()
        text = self._labels(dialog)
        assert "Neu 7" in text
        assert "Neu 8" not in text
        assert "(+2)" in text

    def test_conflicts_offer_a_choice(self, make: Any) -> None:
        mine = Ingredient(name="Mehl")
        theirs = Ingredient(name="Mehl")
        dialog = make(ImportPreview(conflicting=((theirs, mine),)))
        assert dialog.policy is ConflictPolicy.SKIP, "Vorgabe: nichts überschreiben"
        dialog._buttons[ConflictPolicy.REPLACE].setChecked(True)
        assert dialog.policy is ConflictPolicy.REPLACE
        dialog._buttons[ConflictPolicy.KEEP_BOTH].setChecked(True)
        assert dialog.policy is ConflictPolicy.KEEP_BOTH

    def test_an_empty_file_cannot_be_imported(self, make: Any) -> None:
        assert not self._ok(make(ImportPreview())).isEnabled()
