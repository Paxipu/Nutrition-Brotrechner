"""Umgang mit Qt-Werten, die nicht als Enum-Mitglied zurückkommen.

PySide6 reicht Enum-Werte nicht durchgängig als Enum-Mitglied heraus. Die
geklickte Schaltfläche von :meth:`QMessageBox.question` kommt als blanke Zahl
zurück - nachgemessen mit PySide6 6.11 ist ``type(antwort)`` schlicht ``int``.
Dasselbe gilt für die Rolle, die Qt an ``data()`` und ``headerData()``
übergibt.

Ein Identitätsvergleich gegen ``StandardButton.Yes`` ist damit *immer* falsch.
Weil er in einem Bestätigungszweig stand, tat "Ja" dasselbe wie "Nein":
Überschreiben und Löschen brachen stumm ab, zu hören war nur der Systemton des
Dialogs. Dieselbe Bauart hatte schon der Fehler mit den ``str``-Enums, die
PySide6 durch ``QVariant`` einebnet.

Deshalb gilt an jeder Qt-Grenze ``==`` statt ``is``. Diese Datei hält die Regel
an einer Stelle fest; ``test_no_identity_comparison_against_qt_enums`` wacht
darüber, dass sie im ganzen Paket eingehalten wird.

Außerdem liegen hier die Weichen für Qt-Funktionen, die sich zwischen den
unterstützten Fassungen (PySide6 ab 6.5) geändert haben.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from enum import Enum
from typing import Final, TypeVar

from PySide6.QtCore import QSortFilterProxyModel
from PySide6.QtWidgets import QComboBox, QMessageBox

__all__ = ["changing_filter", "confirmed", "enum_or_none", "select_data"]

#: Qt 6.10 ersetzt ``invalidateFilter()`` durch ein Klammerpaar um die
#: Änderung; die alte Funktion gilt dort als veraltet.
_HAS_FILTER_CHANGE: Final = hasattr(QSortFilterProxyModel, "endFilterChange")

_E = TypeVar("_E", bound=Enum)


def confirmed(
    answer: QMessageBox.StandardButton | int,
    button: QMessageBox.StandardButton = QMessageBox.StandardButton.Yes,
) -> bool:
    """Prüft, welche Schaltfläche eines Rückfragedialogs gewählt wurde.

    Args:
        answer: Rückgabe von :meth:`QMessageBox.question` - je nach Qt-Fassung
            ein Enum-Mitglied oder eine Zahl.
        button: Die erwartete Schaltfläche; voreingestellt "Ja".

    Returns:
        ``True``, wenn der Anwender genau diese Schaltfläche angeklickt hat.
    """
    return int(answer) == int(button)


def enum_or_none(kind: type[_E], value: object) -> _E | None:
    """Das Enum-Mitglied zu einem gemerkten Wert - ``None``, wenn es keins gibt.

    Gemerkte Einstellungen stammen aus einer Datei, die sich von Hand
    bearbeiten lässt; ein unbekannter Wert darf nichts zum Absturz bringen.
    """
    try:
        return kind(value)
    except ValueError:
        return None


def select_data(combo: QComboBox, data: object) -> bool:
    """Wählt den Eintrag mit diesem Datenwert; ``False``, wenn es ihn nicht gibt."""
    index = combo.findData(data)
    if index < 0:
        return False
    combo.setCurrentIndex(index)
    return True


@contextmanager
def changing_filter(proxy: QSortFilterProxyModel) -> Iterator[None]:
    """Klammert eine Änderung der Filterkriterien eines Proxys.

    Ab Qt 6.10 mit ``beginFilterChange``/``endFilterChange``, davor mit
    ``invalidateFilter``. So filtert der Proxy danach neu, ohne dass die neue
    Fassung eine Warnung wegen einer veralteten Funktion ausgibt.
    """
    if _HAS_FILTER_CHANGE:
        proxy.beginFilterChange()
        try:
            yield
        finally:
            proxy.endFilterChange(QSortFilterProxyModel.Direction.Rows)
    else:  # pragma: no cover - nur mit Qt vor 6.10
        yield
        proxy.invalidateFilter()
