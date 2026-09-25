"""Wo ein Etikett auf dem Papier landet - in Millimetern, ohne Qt.

Ein Drucker rechnet in Pixeln seiner eigenen Auflösung, ein Etikett in
Millimetern. Die Vorversion skalierte das Etikett auf die ganze Seite: Ein
Etikett von 70 × 100 mm kam auf A4 als rund 190 × 270 mm heraus. Hier wird
jede Lage in Millimetern ab der linken oberen Papierkante berechnet und erst
beim Zeichnen mit der Auflösung des Druckers in Pixel umgerechnet. So hat das
gedruckte Etikett genau seine Größe - auf jedem Drucker.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

__all__ = ["MM_PER_INCH", "Placement", "centered"]

MM_PER_INCH: Final = 25.4


@dataclass(frozen=True, slots=True)
class Placement:
    """Ein Etikett auf einer Druckseite.

    Attributes:
        page: Nummer der Seite, beginnend bei 0.
        x_mm: Abstand der linken Etikettkante von der linken Papierkante.
        y_mm: Abstand der oberen Etikettkante von der oberen Papierkante.
        width_mm: Breite des Etiketts.
        height_mm: Höhe des Etiketts.
    """

    page: int
    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float

    def to_pixels(self, dpi: float) -> tuple[float, float, float, float]:
        """Lage und Größe in Pixeln eines Geräts mit ``dpi`` Punkten je Zoll."""
        scale = dpi / MM_PER_INCH
        return (
            self.x_mm * scale,
            self.y_mm * scale,
            self.width_mm * scale,
            self.height_mm * scale,
        )


def centered(label_mm: tuple[float, float], page_mm: tuple[float, float]) -> Placement:
    """Ein Etikett in Originalgröße mitten auf der Seite.

    Auf einem Etikettendrucker, dessen Seite so groß ist wie das Etikett,
    füllt es die Seite genau aus.

    Args:
        label_mm: Breite und Höhe des Etiketts.
        page_mm: Breite und Höhe des Papiers.
    """
    width, height = label_mm
    page_width, page_height = page_mm
    return Placement(
        page=0,
        x_mm=(page_width - width) / 2,
        y_mm=(page_height - height) / 2,
        width_mm=width,
        height_mm=height,
    )
