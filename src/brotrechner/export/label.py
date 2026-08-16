"""PNG-Etikett mit Nährwertdeklaration.

Der Renderer gibt bewusst ein ``PIL.Image`` zurück und schreibt **keine** Datei.
Damit kann dieselbe Funktion die Bildschirmvorschau, das Speichern und den
Druck bedienen - in der Vorversion erzeugte jeder Knopf sein eigenes Bild
direkt auf der Festplatte, weshalb es keine Vorschau geben konnte.

Aufbau und Reihenfolge der Nährwerttabelle folgen Anhang XV der VO (EU)
Nr. 1169/2011: Energie (kJ und kcal), Fett, davon gesättigte Fettsäuren,
Kohlenhydrate, davon Zucker, Ballaststoffe (freiwillig), Eiweiß, Salz.

Preise erscheinen bewusst nie auf dem Etikett - es ist für verschenkte Brote
gedacht.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Final

from PIL import Image, ImageDraw

from brotrechner.core.nutrients import KCAL_TO_KJ, Nutrients
from brotrechner.export.fonts import Font, FontSet, load_font_set

__all__ = ["LabelOptions", "LabelSize", "LabelTheme", "render_label"]


class LabelSize(Enum):
    """Vordefinierte Etikettformate in Millimetern."""

    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    SQUARE = "square"

    @property
    def millimeters(self) -> tuple[float, float]:
        return {
            LabelSize.SMALL: (54.0, 86.0),
            LabelSize.MEDIUM: (70.0, 100.0),
            LabelSize.LARGE: (90.0, 130.0),
            LabelSize.SQUARE: (90.0, 90.0),
        }[self]

    @property
    def label(self) -> str:
        w, h = self.millimeters
        names = {
            LabelSize.SMALL: "Klein",
            LabelSize.MEDIUM: "Mittel",
            LabelSize.LARGE: "Groß",
            LabelSize.SQUARE: "Quadratisch",
        }
        return f"{names[self]} ({w:.0f} × {h:.0f} mm)"


class LabelTheme(Enum):
    """Farbstimmung des Etiketts."""

    NATURAL = "natural"
    """Warmes Cremeweiß mit grünen Akzenten."""

    MONO = "mono"
    """Reines Schwarzweiß - druckt auf jedem Etikettendrucker sauber."""

    RYE = "rye"
    """Erdiges Braun, passend zu Roggen- und Vollkornbroten."""

    @property
    def label(self) -> str:
        return {
            LabelTheme.NATURAL: "Natur (grün)",
            LabelTheme.MONO: "Schwarzweiß",
            LabelTheme.RYE: "Roggen (braun)",
        }[self]

    @property
    def colors(self) -> _Palette:
        return _PALETTES[self]


@dataclass(frozen=True, slots=True)
class _Palette:
    background: str
    accent: str
    text: str
    muted: str
    rule: str
    panel: str


_PALETTES: Final[dict[LabelTheme, _Palette]] = {
    LabelTheme.NATURAL: _Palette("#FFFDF6", "#2F6B3A", "#1F2421", "#6E7671", "#C9D8CB", "#F1F6EF"),
    LabelTheme.MONO: _Palette("#FFFFFF", "#000000", "#000000", "#555555", "#BBBBBB", "#F2F2F2"),
    LabelTheme.RYE: _Palette("#FDF8F0", "#7A4A21", "#2A211A", "#7A6B5D", "#DFCDB6", "#F6EEE2"),
}


@dataclass(slots=True)
class LabelOptions:
    """Alle Stellschrauben des Etiketts."""

    title: str = "Hausgemachtes Brot"
    subtitle: str = ""
    size: LabelSize = LabelSize.MEDIUM
    theme: LabelTheme = LabelTheme.NATURAL
    dpi: int = 300
    show_date: bool = True
    show_ingredients: bool = True
    show_fiber: bool = True
    show_reference_hint: bool = True
    footer: str = "Mit Liebe gebacken"
    best_before: date | None = None
    baked_on: date | None = None

    #: Zutatenliste, absteigend nach Anteil - so verlangt es die
    #: Zutatenverzeichnis-Regel der VO (EU) Nr. 1169/2011.
    ingredients: Sequence[str] = field(default_factory=tuple)
    net_weight_g: float = 0.0

    def pixel_size(self) -> tuple[int, int]:
        """Bildgröße in Pixeln für die gewählte Auflösung."""
        width_mm, height_mm = self.size.millimeters
        return (
            max(1, round(width_mm / 25.4 * self.dpi)),
            max(1, round(height_mm / 25.4 * self.dpi)),
        )


def single_line(text: str) -> str:
    """Macht aus beliebigem Text eine einzeilige, zeichenbare Zeichenkette.

    Pillow kann bei mehrzeiligem Text keinen Anker auswerten und wirft dann
    einen ``ValueError``. Ein Rezeptname mit Zeilenumbruch - etwa aus der
    Zwischenablage eingefügt - würde das Etikett sonst zum Absturz bringen.
    Steuerzeichen werden ebenfalls entfernt, weil sie in keiner Schrift ein
    sinnvolles Glyph haben.
    """
    cleaned = "".join(" " if ch.isspace() or ord(ch) < 32 else ch for ch in text)
    return " ".join(cleaned.split())


def render_label(
    nutrients: Nutrients,
    options: LabelOptions,
    *,
    fonts: FontSet | None = None,
) -> Image.Image:
    """Zeichnet das Etikett.

    Args:
        nutrients: Nährwerte je 100 g fertiges Brot.
        options: Gestaltung und Inhalte.
        fonts: Vorgeladener Schriftsatz; ``None`` lädt den des Systems.

    Returns:
        RGB-Bild in der in ``options`` gewählten Größe.

    Raises:
        ValueError: Bei unsinniger Auflösung oder negativem Nettogewicht.
    """
    if options.dpi < 36 or options.dpi > 1200:
        raise ValueError(f"Auflösung muss zwischen 36 und 1200 dpi liegen, war {options.dpi}")
    if options.net_weight_g < 0:
        raise ValueError(f"Nettogewicht darf nicht negativ sein, war {options.net_weight_g}")

    fonts = fonts or load_font_set()
    palette = options.theme.colors
    width, height = options.pixel_size()
    scale = options.dpi / 25.4  # Pixel je Millimeter

    def mm(value: float) -> int:
        """Millimeter in Pixel."""
        return max(1, round(value * scale))

    image = Image.new("RGB", (width, height), palette.background)
    draw = ImageDraw.Draw(image)

    # Typografische Skala, in Millimetern gedacht und damit auflösungsunabhängig.
    f_section = fonts.get(mm(2.9), bold=True)
    f_body = fonts.get(mm(2.7))
    f_body_bold = fonts.get(mm(2.7), bold=True)
    f_small = fonts.get(mm(2.1))
    f_weight = fonts.get(mm(3.6), bold=True)

    margin = mm(5.0)
    inner_left = margin + mm(2.0)
    inner_right = width - margin - mm(2.0)

    # Dünner Rahmen: gibt dem Etikett eine Kante zum Ausschneiden.
    draw.rectangle(
        [margin // 2, margin // 2, width - margin // 2, height - margin // 2],
        outline=palette.rule,
        width=max(1, mm(0.3)),
    )

    y = _draw_header(
        draw,
        options,
        palette,
        fonts,
        left=inner_left,
        right=inner_right,
        top=margin + mm(2.0),
        mm=mm,
    )

    # ── Nährwerttabelle ───────────────────────────────────────────────────
    draw.text((inner_left, y), "Nährwerte je 100 g", fill=palette.accent, font=f_section)
    y += mm(4.6)

    rows = _nutrition_rows(nutrients, show_fiber=options.show_fiber)
    panel_top = y - mm(1.2)
    panel_height = len(rows) * mm(4.2) + mm(2.4)
    draw.rectangle(
        [inner_left - mm(1.5), panel_top, inner_right + mm(1.5), panel_top + panel_height],
        fill=palette.panel,
    )

    for label, value, indented, emphasised in rows:
        font = f_body_bold if emphasised else f_body
        colour = palette.text if not indented else palette.muted
        draw.text((inner_left + (mm(3.0) if indented else 0), y), label, fill=colour, font=font)
        draw.text((inner_right, y), value, fill=colour, font=font, anchor="rt")
        y += mm(4.2)

    y += mm(3.0)

    # ── Nettogewicht ──────────────────────────────────────────────────────
    if options.net_weight_g > 0:
        draw.line([(inner_left, y), (inner_right, y)], fill=palette.rule, width=max(1, mm(0.25)))
        y += mm(2.8)
        draw.text(
            ((inner_left + inner_right) // 2, y),
            f"Nettogewicht {_format_weight(options.net_weight_g)}",
            fill=palette.accent,
            font=f_weight,
            anchor="mt",
        )
        y += mm(6.0)

    # ── Fuß zuerst festlegen, damit die Zutatenliste ihren Platz kennt ───
    footer_y = height - margin - mm(3.0)
    footer_top = footer_y - (mm(4.0) if options.show_reference_hint else 0) - mm(3.0)

    # ── Zutatenverzeichnis ────────────────────────────────────────────────
    if options.show_ingredients and options.ingredients:
        draw.text((inner_left, y), "Zutaten", fill=palette.accent, font=f_section)
        y += mm(4.0)
        _draw_ingredient_list(
            draw,
            single_line(", ".join(options.ingredients)),
            fonts=fonts,
            colour=palette.muted,
            left=inner_left,
            right=inner_right,
            top=y,
            bottom=footer_top,
            mm=mm,
        )

    # ── Fuß ───────────────────────────────────────────────────────────────
    if options.show_reference_hint:
        hint_font = fonts.get(mm(1.7))
        hint = "Referenzmenge für einen durchschnittlichen Erwachsenen (8400 kJ / 2000 kcal)"
        hint_lines = _wrap(draw, hint, hint_font, inner_right - inner_left)
        hint_y = footer_y - mm(4.0) - (len(hint_lines) - 1) * mm(2.4)
        for line in hint_lines:
            draw.text(
                ((inner_left + inner_right) // 2, hint_y),
                line,
                fill=palette.muted,
                font=hint_font,
                anchor="mb",
            )
            hint_y += mm(2.4)
    if single_line(options.footer):
        draw.text(
            ((inner_left + inner_right) // 2, footer_y),
            single_line(options.footer),
            fill=palette.muted,
            font=f_small,
            anchor="mb",
        )

    return image


def _draw_ingredient_list(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    fonts: FontSet,
    colour: str,
    left: int,
    right: int,
    top: int,
    bottom: int,
    mm: Callable[[float], int],
) -> None:
    """Setzt das Zutatenverzeichnis in den verbleibenden Platz.

    Ein Brot mit zwölf Zutaten hat ein deutlich längeres Verzeichnis als eines
    mit dreien. Statt über die Fußzeile zu laufen, wird die Schrift in Stufen
    verkleinert und - wenn selbst das nicht reicht - der Rest mit einem
    Auslassungszeichen abgeschnitten. Das Etikett bleibt dadurch immer lesbar
    und formatstabil.

    Args:
        draw: Zeichenkontext.
        text: Zutaten als Fließtext, bereits nach Anteil sortiert.
        fonts: Schriftsatz.
        colour: Textfarbe.
        left: Linke Kante.
        right: Rechte Kante.
        top: Oberkante des verfügbaren Bereichs.
        bottom: Unterkante, die nicht überschritten werden darf.
        mm: Umrechnung Millimeter → Pixel.
    """
    available = bottom - top
    if available <= 0:
        return

    for size_mm, line_mm in ((2.1, 3.0), (1.9, 2.7), (1.7, 2.4), (1.5, 2.1)):
        font = fonts.get(mm(size_mm))
        line_height = mm(line_mm)
        lines = _wrap(draw, text, font, right - left)
        if len(lines) * line_height <= available:
            break
    else:  # kleinste Stufe reicht nicht - abschneiden
        max_lines = max(1, available // line_height)
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            lines[-1] = lines[-1].rstrip(", ") + " …"

    for line in lines:
        draw.text((left, top), line, fill=colour, font=font)
        top += line_height


def _draw_header(
    draw: ImageDraw.ImageDraw,
    options: LabelOptions,
    palette: _Palette,
    fonts: FontSet,
    *,
    left: int,
    right: int,
    top: int,
    mm: Callable[[float], int],
) -> int:
    """Zeichnet Titel, Untertitel, Datumszeile und Trennlinie.

    Returns:
        Das ``y`` unterhalb der Trennlinie.
    """
    y = _draw_wrapped_centered(
        draw,
        single_line(options.title),
        font=fonts.get(mm(4.6), bold=True),
        colour=palette.accent,
        left=left,
        right=right,
        top=top,
        line_height=mm(5.6),
    )
    if single_line(options.subtitle):
        y = _draw_wrapped_centered(
            draw,
            single_line(options.subtitle),
            font=fonts.get(mm(2.6)),
            colour=palette.muted,
            left=left,
            right=right,
            top=y + mm(0.6),
            line_height=mm(3.4),
        )

    date_line = _date_line(options)
    if date_line:
        y += mm(0.8)
        draw.text(
            ((left + right) // 2, y),
            date_line,
            fill=palette.muted,
            font=fonts.get(mm(2.1)),
            anchor="mt",
        )
        y += mm(3.4)

    y += mm(1.6)
    draw.line([(left, y), (right, y)], fill=palette.accent, width=max(1, mm(0.5)))
    return y + mm(3.4)


def _date_line(options: LabelOptions) -> str:
    """Baut die Datumszeile aus Backdatum und Mindesthaltbarkeit."""
    parts: list[str] = []
    if options.show_date:
        baked = options.baked_on or date.today()
        parts.append(f"gebacken am {baked.strftime('%d.%m.%Y')}")
    if options.best_before:
        parts.append(f"mindestens haltbar bis {options.best_before.strftime('%d.%m.%Y')}")
    return "  ·  ".join(parts)


def _nutrition_rows(nutrients: Nutrients, *, show_fiber: bool) -> list[tuple[str, str, bool, bool]]:
    """Zeilen der Nährwerttabelle in der gesetzlich vorgegebenen Reihenfolge.

    Returns:
        Liste aus ``(Bezeichnung, Wert, eingerückt, hervorgehoben)``.
    """
    kj = round(nutrients.energy_kcal * KCAL_TO_KJ)
    rows: list[tuple[str, str, bool, bool]] = [
        ("Energie", f"{kj:.0f} kJ / {nutrients.energy_kcal:.0f} kcal", False, True),
        ("Fett", _grams(nutrients.fat), False, False),
        ("davon gesättigte Fettsäuren", _grams(nutrients.saturated_fat), True, False),
        ("Kohlenhydrate", _grams(nutrients.carbs), False, False),
        ("davon Zucker", _grams(nutrients.sugar), True, False),
    ]
    if show_fiber:
        rows.append(("Ballaststoffe", _grams(nutrients.fiber), False, False))
    rows.append(("Eiweiß", _grams(nutrients.protein), False, False))
    rows.append(("Salz", _grams(nutrients.salt, decimals=2), False, False))
    return rows


def _grams(value: float, *, decimals: int = 1) -> str:
    """Formatiert einen Grammwert mit deutschem Dezimalkomma.

    Werte unter 0,05 g werden nach den Rundungsregeln der EU-Guidance als
    ``< 0,5 g`` bzw. ``0 g`` dargestellt.
    """
    if value <= 0:
        return "0 g"
    rounded = round(value, decimals)
    if rounded == 0:
        return "< 0,01 g" if decimals >= 2 else "< 0,1 g"
    text = f"{rounded:.{decimals}f}".replace(".", ",")
    return f"{text} g"


def _format_weight(grams: float) -> str:
    """Nettogewicht in g oder kg, je nach Größenordnung."""
    if grams >= 1000:
        return f"{grams / 1000:.2f}".replace(".", ",") + " kg"
    return f"{grams:.0f} g"


def _draw_wrapped_centered(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    font: Font,
    colour: str,
    left: int,
    right: int,
    top: int,
    line_height: int,
) -> int:
    """Wie :func:`_draw_wrapped`, aber zentriert."""
    centre = (left + right) // 2
    for line in _wrap(draw, text, font, right - left):
        draw.text((centre, top), line, fill=colour, font=font, anchor="mt")
        top += line_height
    return top


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: Font, max_width: int) -> list[str]:
    """Bricht Text auf die verfügbare Breite um.

    Wörter, die selbst breiter als die Zeile sind (lange Zutatennamen), werden
    hart getrennt, damit nichts aus dem Etikett herausläuft.
    """
    if not text:
        return []

    def width_of(value: str) -> float:
        box = draw.textbbox((0, 0), value, font=font)
        return float(box[2] - box[0])

    lines: list[str] = []
    current = ""
    for word in text.split(" "):
        candidate = f"{current} {word}".strip()
        if current and width_of(candidate) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate

        while width_of(current) > max_width and len(current) > 1:
            cut = _longest_prefix(current, width_of, max_width)
            lines.append(current[:cut])
            current = current[cut:]

    if current:
        lines.append(current)
    return lines


def _longest_prefix(text: str, measure: Callable[[str], float], max_width: int) -> int:
    """Längster Präfix, der noch in ``max_width`` passt (mindestens 1 Zeichen)."""
    low, high = 1, len(text)
    best = 1
    while low <= high:
        middle = (low + high) // 2
        if measure(text[:middle]) <= max_width:
            best = middle
            low = middle + 1
        else:
            high = middle - 1
    return max(1, min(best, len(text) - 1)) if len(text) > 1 else 1
