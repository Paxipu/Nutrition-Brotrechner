#!/usr/bin/env python3
"""Erzeugt das Programmsymbol in allen benötigten Größen.

Wie die Zutatendatenbank ist auch das Symbol erzeugt statt gezeichnet: So
lassen sich Farben zentral ändern, und alle Größen bleiben zueinander stimmig.

Gezeichnet wird ein aufgeschnittener Laib - eine Kuppel mit drei Einschnitten,
wie sie beim Ausbacken entstehen. Die Form ist bewusst grob gehalten, weil das
Symbol in der Taskleiste nur 16 Pixel breit ist; feine Linien verschwinden dort.

Aufruf::

    python tools/build_icon.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ICON_DIR = ROOT / "src/brotrechner/gui/icons"

#: Farben aus dem Hell-Farbsatz der Oberfläche.
ACCENT = (47, 107, 58)
CRUMB = (255, 253, 246)

#: Größen, die Windows für Taskleiste, Explorer und Alt-Tab verlangt.
SIZES = (16, 24, 32, 48, 64, 128, 256)

#: Kantenglättung: gezeichnet wird vierfach vergrößert und dann verkleinert.
SUPERSAMPLE = 4


def render(size: int) -> Image.Image:
    """Zeichnet das Symbol in der gewünschten Kantenlänge."""
    s = size * SUPERSAMPLE
    image = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Hintergrund: abgerundetes Quadrat in der Akzentfarbe.
    draw.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.22), fill=ACCENT)

    # Laib: flache Kuppel auf gerader Standfläche.
    left, right = s * 0.14, s * 0.86
    dome_top, base = s * 0.34, s * 0.70
    dome_height = (base - dome_top) * 2
    draw.pieslice([left, dome_top, right, dome_top + dome_height], 180, 360, fill=CRUMB)
    draw.rectangle([left, dome_top + dome_height / 2, right, base], fill=CRUMB)

    # Drei kurze Ausbunde im oberen Drittel der Kruste. Sie bleiben bewusst
    # kurz: Reichten sie bis zur Standfläche, läse sich das Symbol als
    # Balkendiagramm statt als Brot.
    width = max(1, int(s * 0.05))
    for index in range(3):
        x = s * (0.30 + index * 0.175)
        y = s * (0.53 - abs(index - 1) * 0.025)
        draw.line([(x, y), (x + s * 0.075, y - s * 0.085)], fill=ACCENT, width=width)

    return image.resize((size, size), Image.Resampling.LANCZOS)


def main() -> int:
    """Schreibt ICO für Windows und PNG für Linux und macOS."""
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    frames = [render(size) for size in SIZES]

    ico = ICON_DIR / "brotrechner.ico"
    frames[-1].save(ico, format="ICO", sizes=[(s, s) for s in SIZES])

    png = ICON_DIR / "brotrechner.png"
    frames[-1].save(png, format="PNG")

    print(f"{ico} ({', '.join(str(s) for s in SIZES)} px)")
    print(f"{png} (256 px)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
