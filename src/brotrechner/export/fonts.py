"""Plattformübergreifende Schriftauflösung für die Bildausgabe.

Die Vorgängerversion lud fest ``arial.ttf``. Auf einem Linux-System existiert
diese Datei nicht, wodurch das Etikett kommentarlos auf Pillows Bitmap-
Standardschrift zurückfiel - winzig, unskalierbar und ohne Umlaute in guter
Qualität. Dieses Modul sucht stattdessen eine geeignete TrueType-Schrift in
allen üblichen Systempfaden.
"""

from __future__ import annotations

import functools
import sys
from pathlib import Path
from typing import Final, TypeAlias

from PIL import ImageFont

__all__ = ["Font", "FontSet", "find_font_file", "load_font_set"]

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
    # weiterer Ort, an dem eine brauchbare Schrift liegen kann.
    try:  # pragma: no cover - hängt von der Umgebung ab
        import matplotlib  # noqa: PLC0415

        dirs.append(Path(matplotlib.__file__).parent / "mpl-data" / "fonts" / "ttf")
    except ImportError:  # pragma: no cover
        pass

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


def load_font_set() -> FontSet:
    """Lädt den Schriftsatz des Systems."""
    found = find_font_file()
    if found is None:
        return FontSet(None, None)
    return FontSet(*found)
