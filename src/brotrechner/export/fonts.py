"""Plattformübergreifende Schriftauflösung für die Bildausgabe.

Die Vorgängerversion lud fest ``arial.ttf``. Auf einem Linux-System existiert
diese Datei nicht, wodurch das Etikett kommentarlos auf Pillows Bitmap-
Standardschrift zurückfiel - winzig, unskalierbar und ohne Umlaute in guter
Qualität. Dieses Modul sucht stattdessen eine geeignete TrueType-Schrift in
allen üblichen Systempfaden.
"""

from __future__ import annotations

import functools
import importlib.util
import math
import sys
from pathlib import Path
from typing import Final, TypeAlias

from PIL import ImageFont

__all__ = ["Font", "FontSet", "find_font_file", "ink_height", "load_font_set"]

#: Pillow liefert je nach Herkunft zwei verschiedene Klassen: eine skalierbare
#: TrueType-Schrift oder die eingebaute Bitmap-Schrift. Beide sind für
#: ``ImageDraw.text`` gleichwertig, teilen aber keine gemeinsame Basisklasse.
Font: TypeAlias = "ImageFont.ImageFont | ImageFont.FreeTypeFont"

#: Kandidaten in Reihenfolge der Bevorzugung, je (regulär, fett).
#: DejaVu steht vorn, weil es auf praktisch jeder Linux-Installation liegt,
#: alle benötigten Zeichen enthält und metrisch ruhig wirkt.
_FONT_CANDIDATES: Final[tuple[tuple[str, str], ...]] = (
    ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
    ("LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf"),
    ("NotoSans-Regular.ttf", "NotoSans-Bold.ttf"),
    ("FreeSans.ttf", "FreeSansBold.ttf"),
    ("Arial.ttf", "Arial Bold.ttf"),
    ("arial.ttf", "arialbd.ttf"),
    ("segoeui.ttf", "segoeuib.ttf"),
    ("Helvetica.ttc", "Helvetica.ttc"),
)


def _search_dirs() -> list[Path]:
    """Verzeichnisse, in denen nach Schriftdateien gesucht wird."""
    dirs: list[Path] = []
    if sys.platform == "win32":
        dirs += [
            Path("C:/Windows/Fonts"),
            Path.home() / "AppData/Local/Microsoft/Windows/Fonts",
        ]
    elif sys.platform == "darwin":
        dirs += [
            Path("/System/Library/Fonts"),
            Path("/System/Library/Fonts/Supplemental"),
            Path("/Library/Fonts"),
            Path.home() / "Library/Fonts",
        ]
    else:
        dirs += [
            Path("/usr/share/fonts/truetype/dejavu"),
            Path("/usr/share/fonts/truetype/liberation"),
            Path("/usr/share/fonts/truetype"),
            Path("/usr/share/fonts/TTF"),
            Path("/usr/share/fonts"),
            Path("/usr/local/share/fonts"),
            Path.home() / ".local/share/fonts",
            Path.home() / ".fonts",
        ]

    # matplotlib bringt DejaVu mit. Das ist keine Abhängigkeit, sondern nur ein
    # weiterer Ort, an dem eine brauchbare Schrift liegen kann. Gesucht wird
    # über die Modulsuche statt über einen Import: Das vermeidet, matplotlib
    # nur wegen eines Verzeichnispfads vollständig zu laden, und funktioniert
    # auch dort, wo das Paket gar nicht installiert ist.
    spec = importlib.util.find_spec("matplotlib")
    if spec is not None and spec.origin:  # pragma: no cover - hängt von der Umgebung ab
        dirs.append(Path(spec.origin).parent / "mpl-data" / "fonts" / "ttf")

    return [d for d in dirs if d.is_dir()]


@functools.lru_cache(maxsize=1)
def find_font_file() -> tuple[Path, Path] | None:
    """Sucht ein Paar aus regulärer und fetter Schriftdatei.

    Returns:
        Tupel ``(regulär, fett)`` oder ``None``, wenn keine TrueType-Schrift
        gefunden wurde.
    """
    directories = _search_dirs()
    for regular_name, bold_name in _FONT_CANDIDATES:
        for directory in directories:
            regular = directory / regular_name
            if not regular.is_file():
                continue
            bold = directory / bold_name
            return regular, bold if bold.is_file() else regular

    # Letzte Chance: rekursiv nach DejaVuSans suchen.
    for directory in directories:
        for found in directory.rglob("DejaVuSans.ttf"):
            bold = found.with_name("DejaVuSans-Bold.ttf")
            return found, bold if bold.is_file() else found
    return None


#: Größe, bei der die Proportionen einer Schrift geschätzt werden - groß genug,
#: dass die Rundung auf ganze Pixel keine Rolle spielt.
_PROBE_PX: Final = 400

#: So viele Pixelgrößen über der Schätzung werden höchstens geprüft.
_MAX_EXTRA_PX: Final = 64


def ink_height(font: Font, glyphs: str) -> int:
    """Höhe der Tinte des niedrigsten Zeichens aus ``glyphs`` in Pixeln.

    Gemessen wird, was gedruckt wird, nicht die Zeilenhöhe der Schrift: Für die
    x-Höhe zählt, wie hoch ein ``x`` tatsächlich auf dem Papier steht. Das
    niedrigste Zeichen entscheidet - bei Ziffern ist die "0" durch ihren
    Überhang etwas höher als die "1".
    """
    heights = []
    for char in glyphs:
        _, top, _, bottom = font.getbbox(char)
        heights.append(int(bottom - top))
    return min(heights, default=0)


class FontSet:
    """Ein Satz Schriftgrößen für die Etikettausgabe.

    Größen werden in Pixeln angegeben und beim Rendern aus der Zielauflösung
    berechnet, damit ein 300-dpi-Etikett dieselbe Optik hat wie die
    Bildschirmvorschau.
    """

    def __init__(self, regular: Path | None, bold: Path | None) -> None:
        self._regular = regular
        self._bold = bold
        self._cache: dict[tuple[bool, int], Font] = {}
        self._sizes: dict[tuple[str, float, tuple[bool, ...]], int | None] = {}

    @property
    def is_scalable(self) -> bool:
        """False, wenn nur Pillows Bitmap-Standardschrift verfügbar ist."""
        return self._regular is not None

    def get(self, size: int, *, bold: bool = False) -> Font:
        """Liefert eine Schrift der gewünschten Größe (mit Zwischenspeicher)."""
        key = (bold, size)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        path = self._bold if bold else self._regular
        font: Font
        if path is None:
            font = ImageFont.load_default()
        else:
            try:
                font = ImageFont.truetype(str(path), size)
            except OSError:  # pragma: no cover - defekte Schriftdatei
                font = ImageFont.load_default()
        self._cache[key] = font
        return font

    def size_for_ink(
        self, glyphs: str, height_px: float, *, cuts: tuple[bool, ...] = (False, True)
    ) -> int | None:
        """Kleinste Pixelgröße, bei der jedes Zeichen aus ``glyphs`` hoch genug ist.

        Die Größe wird aus den Proportionen geschätzt und dann an der
        tatsächlich gerasterten Schrift bestätigt - bei kleinen Größen rundet
        die Schrift auf ganze Pixel, und darauf kommt es beim Druck an.

        Args:
            glyphs: Zeichen, deren Tinte mindestens ``height_px`` hoch sein muss,
                etwa ``"x"`` für die x-Höhe.
            height_px: Verlangte Höhe in Pixeln.
            cuts: Schnitte, die die Bedingung erfüllen müssen; ``False`` ist
                normal, ``True`` fett.

        Returns:
            Die Größe in Pixeln oder ``None``, wenn nur die unskalierbare
            Bitmap-Schrift verfügbar ist.
        """
        if not self.is_scalable:
            return None
        key = (glyphs, height_px, cuts)
        if key in self._sizes:
            return self._sizes[key]

        def shortest(size: int) -> int:
            return min(ink_height(self.get(size, bold=cut), glyphs) for cut in cuts)

        probe = shortest(_PROBE_PX)
        if probe <= 0:
            # Zeichen ohne Tinte werden bei keiner Größe hoch genug.
            self._sizes[key] = None
            return None
        estimate = max(1, math.ceil(height_px * _PROBE_PX / probe))
        found = next(
            (
                size
                for size in range(estimate, estimate + _MAX_EXTRA_PX)
                if shortest(size) >= height_px
            ),
            None,
        )
        # Die Schätzung kann zu hoch liegen, wenn die Schrift bei kleinen
        # Größen aufrundet - dann reicht auch eine kleinere.
        while found is not None and found > 1 and shortest(found - 1) >= height_px:
            found -= 1
        self._sizes[key] = found
        return found


def load_font_set() -> FontSet:
    """Lädt den Schriftsatz des Systems."""
    found = find_font_file()
    if found is None:
        return FontSet(None, None)
    return FontSet(*found)
