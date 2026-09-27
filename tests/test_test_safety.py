"""Schutzvorrichtungen der Testumgebung selbst.

Ein modaler Dialog, den ein Test nicht beantwortet, hielt bisher den ganzen
Testlauf an - ohne Meldung, bis jemand ihn abbrach. Und Tests, die etwas
exportieren, legten auf einem Entwicklerrechner den Ordner
``~/Documents/Brotrechner`` an.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.gui


def test_an_open_dialog_is_closed_and_named(qapp: Any, dialog_guard: Any) -> None:
    """Ein Meldungsfenster heißt nach seinem Text.

    Den Titel verwirft Qt auf macOS schon beim Setzen (Apple-Richtlinien) -
    genannt wurde dort bisher nur "QMessageBox".
    """
    from PySide6.QtWidgets import QMessageBox

    box = QMessageBox(QMessageBox.Icon.Question, "Löschen", "Wirklich löschen?\n\nGanz sicher?")
    box.setModal(True)
    box.show()
    qapp.processEvents()
    assert dialog_guard.close_open_dialogs() == ["Wirklich löschen?"]
    assert not box.isVisible()
    assert dialog_guard.close_open_dialogs() == []
    dialog_guard.left_open.clear()  # Hier gewollt - der Test soll nicht scheitern.


def test_other_dialogs_are_named_by_their_title(qapp: Any, dialog_guard: Any) -> None:
    from PySide6.QtWidgets import QDialog

    dialog = QDialog()
    dialog.setWindowTitle("Etikett drucken")
    dialog.setModal(True)
    dialog.show()
    untitled = QDialog()
    untitled.setModal(True)
    untitled.show()
    qapp.processEvents()
    assert dialog_guard.close_open_dialogs() == ["QDialog", "Etikett drucken"]
    dialog_guard.left_open.clear()


def test_a_blocking_dialog_does_not_hang_the_run(qapp: Any, dialog_guard: Any) -> None:
    """Ohne Wächter kehrte ``exec()`` nie zurück."""
    del qapp
    from PySide6.QtWidgets import QMessageBox

    box = QMessageBox(QMessageBox.Icon.Information, "Vergessen", "Niemand antwortet")
    box.exec()
    assert dialog_guard.left_open == ["Niemand antwortet"]
    dialog_guard.left_open.clear()


def test_exports_stay_inside_the_test(
    qapp: object, data_dir: Path, dialogs: dict[str, object], tmp_path: Path
) -> None:
    del qapp, dialogs
    from brotrechner.gui.main_window import MainWindow

    window = MainWindow(data_dir=data_dir)
    try:
        assert window._export_dir().is_relative_to(tmp_path)
    finally:
        window.close()
    assert Path.home().is_relative_to(tmp_path)
