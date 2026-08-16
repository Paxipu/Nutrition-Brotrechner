"""Wiederverwendbare Bausteine der Oberfläche.

Die Auswertung wird nicht mehr als Monospace-Textblock ausgegeben, sondern in
Karten - kleine, klar abgegrenzte Flächen mit Titel und Inhalt. Das ist der
Kern der neuen Gliederung: Jede Kennzahl hat ihren Platz, statt in einer
Textwüste gesucht werden zu müssen.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from brotrechner.core.reference import AmpelLevel
from brotrechner.gui.theme import SPACING, Tokens

__all__ = ["AmpelDot", "Card", "ClickableLabel", "IntakeBar", "StatCard", "separator"]


class ClickableLabel(QLabel):
    """Beschriftung, die sich wie eine Schaltfläche anklicken lässt.

    Wird für den Pfadhinweis in der Statusleiste gebraucht. Ein eigenes Widget
    statt einer überschriebenen Methode am Einzelobjekt: Letzteres lässt sich
    weder typprüfen noch wiederverwenden.
    """

    clicked = Signal()

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, ev: QMouseEvent) -> None:  # noqa: N802 - Qt-Vertrag
        """Löst bei der linken Maustaste :attr:`clicked` aus."""
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(ev)


class Card(QFrame):
    """Abgesetzte Fläche mit optionalem Titel und einer Inhaltsspalte.

    Args:
        title: Überschrift; leer lässt die Kopfzeile weg.
        parent: Elternwidget.
    """

    def __init__(self, title: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setFrameShape(QFrame.Shape.NoFrame)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(SPACING["md"], SPACING["md"], SPACING["md"], SPACING["md"])
        outer.setSpacing(SPACING["sm"])

        self._header = QHBoxLayout()
        self._header.setSpacing(SPACING["sm"])
        self._title = QLabel(title)
        self._title.setObjectName("CardTitle")
        self._header.addWidget(self._title)
        self._header.addStretch(1)
        outer.addLayout(self._header)
        self._title.setVisible(bool(title))

        self.body = QVBoxLayout()
        self.body.setSpacing(SPACING["sm"])
        outer.addLayout(self.body)

    def set_title(self, title: str) -> None:
        """Ändert die Überschrift; ein leerer Text blendet sie aus."""
        self._title.setText(title)
        self._title.setVisible(bool(title))

    def add_header_widget(self, widget: QWidget) -> None:
        """Setzt ein Bedienelement rechts in die Kopfzeile."""
        self._header.addWidget(widget)

    def add_widget(self, widget: QWidget, stretch: int = 0) -> None:
        """Hängt ein Widget in den Karteninhalt."""
        self.body.addWidget(widget, stretch)


class StatCard(QFrame):
    """Kompakte Kennzahl: großer Wert, darüber Beschriftung, darunter Zusatz."""

    def __init__(
        self,
        caption: str,
        value: str = "-",
        hint: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("StatCard")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING["md"], SPACING["sm"], SPACING["md"], SPACING["sm"])
        layout.setSpacing(2)

        self._caption = QLabel(caption)
        self._caption.setObjectName("StatCaption")
        self._value = QLabel(value)
        self._value.setObjectName("StatValue")
        self._hint = QLabel(hint)
        self._hint.setObjectName("StatCaption")
        self._hint.setVisible(bool(hint))

        layout.addWidget(self._caption)
        layout.addWidget(self._value)
        layout.addWidget(self._hint)

    def set_value(self, value: str, hint: str = "") -> None:
        """Aktualisiert Wert und Zusatzzeile."""
        self._value.setText(value)
        self._hint.setText(hint)
        self._hint.setVisible(bool(hint))


class AmpelDot(QWidget):
    """Farbiger Punkt für die Nährwert-Ampel.

    Ein Punkt allein wäre für farbfehlsichtige Anwender nicht unterscheidbar,
    deshalb trägt das Widget zusätzlich einen Tooltip mit der Stufe im Klartext
    und die Tabelle daneben den Textwert.
    """

    _DIAMETER = 11

    def __init__(self, tokens: Tokens, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._level = AmpelLevel.NONE
        self.setFixedSize(self._DIAMETER + 4, self._DIAMETER + 4)

    def set_level(self, level: AmpelLevel) -> None:
        """Setzt die Ampelstufe."""
        self._level = level
        self.setToolTip(
            f"Gehalt: {level.label}" if level is not AmpelLevel.NONE else "keine Ampel definiert"
        )
        self.update()

    def set_tokens(self, tokens: Tokens) -> None:
        """Übernimmt einen neuen Farbsatz (Moduswechsel)."""
        self._tokens = tokens
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt-Vertrag
        del event
        if self._level is AmpelLevel.NONE:
            return
        colour = {
            AmpelLevel.LOW: self._tokens.success,
            AmpelLevel.MEDIUM: self._tokens.warning,
            AmpelLevel.HIGH: self._tokens.danger,
        }[self._level]

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(colour))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(2, 2, self._DIAMETER, self._DIAMETER)
        painter.end()


class IntakeBar(QWidget):
    """Balken für den Anteil an der Tagesreferenzmenge.

    Werte über 100 % werden auf volle Breite begrenzt und farblich
    hervorgehoben, damit ein 300-%-Wert die Skala nicht sprengt.
    """

    _HEIGHT = 6

    def __init__(self, tokens: Tokens, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._percent = 0.0
        self.setFixedHeight(self._HEIGHT + 6)
        self.setMinimumWidth(36)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_percent(self, percent: float | None) -> None:
        """Setzt den Prozentwert; ``None`` leert den Balken."""
        self._percent = max(0.0, percent or 0.0)
        self.setToolTip(
            f"{self._percent:.0f} % der Tagesreferenzmenge" if percent is not None else ""
        )
        self.update()

    def set_tokens(self, tokens: Tokens) -> None:
        self._tokens = tokens
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt-Vertrag
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        top = (self.height() - self._HEIGHT) // 2
        painter.setBrush(QColor(self._tokens.border))
        painter.drawRoundedRect(0, top, self.width(), self._HEIGHT, 3, 3)

        if self._percent > 0:
            filled = int(self.width() * min(self._percent, 100.0) / 100.0)
            colour = self._tokens.warning if self._percent > 100 else self._tokens.accent
            painter.setBrush(QColor(colour))
            painter.drawRoundedRect(0, top, max(3, filled), self._HEIGHT, 3, 3)
        painter.end()


def separator(parent: QWidget | None = None) -> QFrame:
    """Waagerechte Trennlinie im Kartenstil."""
    line = QFrame(parent)
    line.setProperty("role", "separator")
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFixedHeight(1)
    return line
