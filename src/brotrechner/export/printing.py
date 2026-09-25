"""Wo ein Etikett auf dem Papier landet - in Millimetern, ohne Qt.

Ein Drucker rechnet in Pixeln seiner eigenen Auflösung, ein Etikett in
Millimetern. Die Vorversion skalierte das Etikett auf die ganze Seite: Ein
Etikett von 70 × 100 mm kam auf A4 als rund 190 × 270 mm heraus. Hier wird
jede Lage in Millimetern ab der linken oberen Papierkante berechnet und erst
beim Zeichnen mit der Auflösung des Druckers in Pixel umgerechnet. So hat das
gedruckte Etikett genau seine Größe - auf jedem Drucker.

Vier Druckarten decken ab, womit Etiketten üblicherweise entstehen:

* **Einzeln** - ein Etikett mitten auf jedem Blatt.
* **Etikettendrucker** - die Seite ist so groß wie das Etikett; je Etikett
  eine Seite, auf Wunsch um 90° gedreht, wenn der Drucker das Etikett quer
  einzieht.
* **Etikettenbogen** - ein Raster nach den Maßen auf der Verpackung. Ein
  angebrochener Bogen lässt sich ab dem ersten freien Etikett bedrucken.
* **A4 zum Ausschneiden** - so viele Etiketten, wie auf ein Blatt passen,
  mittig und mit Abstand zum Schneiden.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Final

__all__ = [
    "A4_MM",
    "MM_PER_INCH",
    "Placement",
    "PrintMode",
    "SheetLayout",
    "centered",
    "fitted_sheet",
    "one_per_page",
    "sheet_placements",
]

MM_PER_INCH: Final = 25.4

#: Breite und Höhe eines A4-Blatts im Hochformat.
A4_MM: Final = (210.0, 297.0)

#: Rechenungenauigkeit beim Vergleich von Millimetern.
_TOLERANCE_MM: Final = 0.01


class PrintMode(Enum):
    """Wie das Etikett aufs Papier kommt."""

    SINGLE = "single"
    LABEL_PRINTER = "label_printer"
    SHEET = "sheet"
    CUT_SHEET = "cut_sheet"

    @property
    def label(self) -> str:
        return {
            PrintMode.SINGLE: "Einzeln mitten aufs Blatt",
            PrintMode.LABEL_PRINTER: "Etikettendrucker",
            PrintMode.SHEET: "Etikettenbogen",
            PrintMode.CUT_SHEET: "Mehrere auf A4 zum Ausschneiden",
        }[self]


@dataclass(frozen=True, slots=True)
class Placement:
    """Ein Etikett auf einer Druckseite.

    Attributes:
        page: Nummer der Seite, beginnend bei 0.
        x_mm: Abstand der linken Kante von der linken Papierkante.
        y_mm: Abstand der oberen Kante von der oberen Papierkante.
        width_mm: Breite der Fläche, die das Etikett auf dem Papier belegt.
        height_mm: Höhe dieser Fläche.
        rotated: Das Etikett steht um 90° im Uhrzeigersinn gedreht in der
            Fläche - Breite und Höhe der Fläche sind dann die des Etiketts
            vertauscht.
    """

    page: int
    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float
    rotated: bool = False

    def to_pixels(self, dpi: float) -> tuple[float, float, float, float]:
        """Lage und Größe in Pixeln eines Geräts mit ``dpi`` Punkten je Zoll."""
        scale = dpi / MM_PER_INCH
        return (
            self.x_mm * scale,
            self.y_mm * scale,
            self.width_mm * scale,
            self.height_mm * scale,
        )


def centered(
    label_mm: tuple[float, float], page_mm: tuple[float, float], *, page: int = 0
) -> Placement:
    """Ein Etikett in Originalgröße mitten auf der Seite.

    Auf einem Etikettendrucker, dessen Seite so groß ist wie das Etikett,
    füllt es die Seite genau aus.

    Args:
        label_mm: Breite und Höhe des Etiketts.
        page_mm: Breite und Höhe des Papiers.
        page: Nummer der Seite.
    """
    width, height = label_mm
    page_width, page_height = page_mm
    return Placement(
        page=page,
        x_mm=(page_width - width) / 2,
        y_mm=(page_height - height) / 2,
        width_mm=width,
        height_mm=height,
    )


def one_per_page(
    label_mm: tuple[float, float],
    page_mm: tuple[float, float],
    *,
    count: int,
    rotated: bool = False,
) -> list[Placement]:
    """Je Seite ein Etikett, mittig - einzeln auf A4 oder am Etikettendrucker.

    Args:
        label_mm: Breite und Höhe des Etiketts.
        page_mm: Breite und Höhe des Papiers.
        count: Anzahl der Etiketten und damit der Seiten.
        rotated: Um 90° gedreht - das Etikett belegt dann Höhe × Breite.
    """
    width, height = label_mm
    footprint = (height, width) if rotated else (width, height)
    placements = []
    for page in range(max(0, count)):
        spot = centered(footprint, page_mm, page=page)
        placements.append(
            Placement(page, spot.x_mm, spot.y_mm, spot.width_mm, spot.height_mm, rotated)
        )
    return placements


@dataclass(frozen=True, slots=True)
class SheetLayout:
    """Das Raster eines Etikettenbogens in Millimetern.

    Die Maße stehen auf der Verpackung: wie viele Etiketten nebeneinander und
    untereinander, der Rand links und oben bis zum ersten Etikett und der
    Abstand zwischen zwei Etiketten. Die Größe eines Etiketts ist die des
    Etikettformats.
    """

    columns: int = 2
    rows: int = 4
    margin_left_mm: float = 0.0
    margin_top_mm: float = 0.0
    gap_x_mm: float = 0.0
    gap_y_mm: float = 0.0
    page_mm: tuple[float, float] = A4_MM

    @property
    def per_page(self) -> int:
        """Etiketten je Bogen."""
        return max(0, self.columns) * max(0, self.rows)

    def cell(self, index: int, label_mm: tuple[float, float]) -> tuple[float, float]:
        """Linke obere Ecke des Etiketts Nummer ``index`` (ab 0, zeilenweise)."""
        width, height = label_mm
        row, column = divmod(index, self.columns)
        return (
            self.margin_left_mm + column * (width + self.gap_x_mm),
            self.margin_top_mm + row * (height + self.gap_y_mm),
        )

    def problems(self, label_mm: tuple[float, float]) -> list[str]:
        """Was an diesem Raster nicht stimmt - leer, wenn es aufs Blatt passt."""
        if self.columns < 1 or self.rows < 1:
            return ["Der Bogen braucht mindestens eine Spalte und eine Reihe."]
        found: list[str] = []
        lengths = (self.margin_left_mm, self.margin_top_mm, self.gap_x_mm, self.gap_y_mm)
        if any(not math.isfinite(value) or value < 0 for value in lengths):
            found.append("Ränder und Abstände dürfen nicht negativ sein.")
        width, height = label_mm
        page_width, page_height = self.page_mm
        right = self.margin_left_mm + self.columns * width + (self.columns - 1) * self.gap_x_mm
        bottom = self.margin_top_mm + self.rows * height + (self.rows - 1) * self.gap_y_mm
        if right > page_width + _TOLERANCE_MM:
            found.append(
                f"Das Raster ist {_mm(right)} breit, das Blatt nur {_mm(page_width)} - "
                "Spalten, Rand oder Abstand prüfen."
            )
        if bottom > page_height + _TOLERANCE_MM:
            found.append(
                f"Das Raster ist {_mm(bottom)} hoch, das Blatt nur {_mm(page_height)} - "
                "Reihen, Rand oder Abstand prüfen."
            )
        return found


def sheet_placements(
    layout: SheetLayout,
    label_mm: tuple[float, float],
    *,
    count: int,
    first: int = 1,
) -> list[Placement]:
    """Etiketten auf Bögen, zeilenweise von links oben.

    Args:
        layout: Das Raster des Bogens.
        label_mm: Breite und Höhe eines Etiketts.
        count: Anzahl der Etiketten; weitere Bögen folgen nach Bedarf.
        first: Erstes freies Etikett auf dem ersten Bogen, ab 1 gezählt - so
            lässt sich ein angebrochener Bogen weiterverwenden. Alle weiteren
            Bögen beginnen wieder beim ersten Etikett.

    Raises:
        ValueError: Wenn ``first`` nicht auf dem Bogen liegt.
    """
    per_page = layout.per_page
    if per_page < 1:
        return []
    if not 1 <= first <= per_page:
        raise ValueError(f"Erstes Etikett muss zwischen 1 und {per_page} liegen, war {first}")
    width, height = label_mm
    placements = []
    for number in range(first - 1, first - 1 + max(0, count)):
        page, index = divmod(number, per_page)
        x, y = layout.cell(index, label_mm)
        placements.append(Placement(page, x, y, width, height))
    return placements


def fitted_sheet(
    label_mm: tuple[float, float],
    page_mm: tuple[float, float] = A4_MM,
    *,
    margin_mm: float = 10.0,
    gap_mm: float = 5.0,
) -> SheetLayout:
    """So viele Etiketten, wie auf ein Blatt passen - mittig, mit Schnittabstand.

    Mindestens eines: Ist das Etikett größer als das Blatt, meldet
    :meth:`SheetLayout.problems` das.

    Args:
        label_mm: Breite und Höhe eines Etiketts.
        page_mm: Breite und Höhe des Papiers.
        margin_mm: Mindestrand ringsum - die meisten Drucker bedrucken den
            äußersten Rand nicht.
        gap_mm: Abstand zwischen zwei Etiketten, damit sich beide sauber
            ausschneiden lassen.
    """
    width, height = label_mm
    page_width, page_height = page_mm
    columns = max(1, math.floor((page_width - 2 * margin_mm + gap_mm) / (width + gap_mm)))
    rows = max(1, math.floor((page_height - 2 * margin_mm + gap_mm) / (height + gap_mm)))
    grid_width = columns * width + (columns - 1) * gap_mm
    grid_height = rows * height + (rows - 1) * gap_mm
    return SheetLayout(
        columns=columns,
        rows=rows,
        margin_left_mm=(page_width - grid_width) / 2,
        margin_top_mm=(page_height - grid_height) / 2,
        gap_x_mm=gap_mm,
        gap_y_mm=gap_mm,
        page_mm=page_mm,
    )


def _mm(value: float) -> str:
    """Millimeter mit einer Nachkommastelle und deutschem Komma."""
    return f"{value:.1f} mm".replace(".", ",")
