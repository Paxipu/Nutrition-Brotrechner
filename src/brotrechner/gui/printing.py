"""Etiketten auf den Drucker bringen: Seite einrichten und zeichnen.

Die Lage der Etiketten kommt fertig aus :mod:`brotrechner.export.printing`,
in Millimetern ab der Papierkante. Hier wird nur noch die Seite passend
eingestellt und jede Lage mit der Auflösung des Druckers in Pixel umgesetzt.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QRectF, QSizeF
from PySide6.QtGui import QImage, QPageLayout, QPageSize, QPainter
from PySide6.QtPrintSupport import QPrinter

from brotrechner.export.printing import Placement, PrintMode

__all__ = ["paint_labels", "paper_mm", "prepare_printer"]


def prepare_printer(
    printer: QPrinter, mode: PrintMode, label_mm: tuple[float, float], *, rotated: bool
) -> None:
    """Stellt Seite und Ausrichtung für die Druckart ein - vor dem Druckdialog.

    Am Etikettendrucker ist die Seite so groß wie das Etikett (gedreht: so
    breit, wie es hoch ist). Für Bögen gilt A4 im Hochformat. Einzeln bleibt
    das Papier, das der Drucker vorschlägt. Im Druckdialog lässt sich alles
    noch ändern; gezeichnet wird dann auf das tatsächlich gewählte Papier.

    Qt legt den Ursprung sonst in die Ecke des bedruckbaren Bereichs, und der
    Druckerrand zählte doppelt - deshalb immer ``fullPage``.
    """
    printer.setFullPage(True)
    if mode == PrintMode.LABEL_PRINTER:
        width, height = (label_mm[1], label_mm[0]) if rotated else label_mm
        # QPageSize kennt nur das Hochformat; quer wird über die Ausrichtung.
        size = QPageSize(
            QSizeF(min(width, height), max(width, height)),
            QPageSize.Unit.Millimeter,
            f"Etikett {width:g} × {height:g} mm",
            QPageSize.SizeMatchPolicy.ExactMatch,
        )
        printer.setPageSize(size)
        printer.setPageOrientation(
            QPageLayout.Orientation.Landscape
            if width > height
            else QPageLayout.Orientation.Portrait
        )
    elif mode in (PrintMode.SHEET, PrintMode.CUT_SHEET):
        printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        printer.setPageOrientation(QPageLayout.Orientation.Portrait)


def paper_mm(printer: QPrinter) -> tuple[float, float]:
    """Breite und Höhe des Papiers, wie es gerade eingestellt ist."""
    paper = printer.pageLayout().fullRect(QPageLayout.Unit.Millimeter)
    return (paper.width(), paper.height())


def paint_labels(printer: QPrinter, image: QImage, placements: Sequence[Placement]) -> bool:
    """Zeichnet das Etikett an jede Lage, Seite für Seite.

    Returns:
        ``False``, wenn sich der Drucker nicht öffnen ließ.
    """
    printer.setFullPage(True)
    painter = QPainter()
    if not painter.begin(printer):
        return False
    try:
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        dpi = printer.resolution()
        page = 0
        for placement in placements:
            while page < placement.page:
                printer.newPage()
                page += 1
            _draw(painter, image, placement, dpi)
    finally:
        painter.end()
    return True


def _draw(painter: QPainter, image: QImage, placement: Placement, dpi: float) -> None:
    """Ein Etikett in seine Fläche - gedreht, wenn die Lage es verlangt."""
    x, y, width, height = placement.to_pixels(dpi)
    if not placement.rotated:
        painter.drawImage(QRectF(x, y, width, height), image)
        return
    # Im Uhrzeigersinn um die Mitte der Fläche: Die Breite des Etiketts liegt
    # danach senkrecht, seine Höhe waagerecht.
    painter.save()
    try:
        painter.translate(x + width / 2, y + height / 2)
        painter.rotate(90)
        painter.drawImage(QRectF(-height / 2, -width / 2, height, width), image)
    finally:
        painter.restore()
