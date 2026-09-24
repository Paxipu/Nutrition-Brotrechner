"""PNG-Etikett mit Nährwertdeklaration.

Der Renderer gibt bewusst ein ``PIL.Image`` zurück und schreibt **keine** Datei.
Damit kann dieselbe Funktion die Bildschirmvorschau, das Speichern und den
Druck bedienen - in der Vorversion erzeugte jeder Knopf sein eigenes Bild
direkt auf der Festplatte, weshalb es keine Vorschau geben konnte.

Aufbau und Reihenfolge der Nährwerttabelle folgen Anhang XV der VO (EU)
Nr. 1169/2011: Brennwert (kJ und kcal), Fett, davon gesättigte Fettsäuren,
Kohlenhydrate, davon Zucker, Ballaststoffe (freiwillig), Eiweiß, Salz. Die
Werte sind nach der Leitlinie der EU-Kommission gerundet
(:mod:`brotrechner.core.rounding`).

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

from brotrechner.core.nutrients import Nutrients
from brotrechner.core.rounding import as_declarable, declare_energy, declare_nutrient
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


@dataclass(frozen=True, slots=True)
class _Metrics:
    """Alle Maße des Etiketts in Pixeln, abgeleitet aus einem Stauchungsfaktor.

    Sämtliche Größen sind in Millimetern gedacht und werden über die Auflösung
    in Pixel umgerechnet. ``factor`` staucht die gesamte Typografie gleichmäßig,
    wenn der Inhalt sonst nicht auf das Etikett passt - ein Aufkleber von
    54 × 86 mm trägt nun einmal weniger als einer von 90 × 130 mm.
    """

    pixels_per_mm: float
    factor: float

    def mm(self, value: float) -> int:
        """Millimeter in Pixel, ohne Stauchung - für Ränder und Linienstärken."""
        return max(1, round(value * self.pixels_per_mm))

    def scaled(self, value: float) -> int:
        """Millimeter in Pixel, mit Stauchung - für Schrift und Zeilenabstände."""
        return max(1, round(value * self.factor * self.pixels_per_mm))


#: Stufen, in denen die Typografie verkleinert wird, bis der Inhalt passt.
#: Unter 0,62 wäre ein Etikett nicht mehr zuverlässig lesbar; dann kürzt
#: stattdessen das Zutatenverzeichnis.
_SCALE_STEPS: Final[tuple[float, ...]] = (1.0, 0.94, 0.88, 0.82, 0.76, 0.70, 0.66, 0.62)

#: Bis zu dieser Stufe wird herunterskaliert, um das *vollständige*
#: Zutatenverzeichnis unterzubringen. Darunter wäre der Preis zu hoch: Ein
#: winziges Etikett, nur damit die letzte Zutat noch hineinpasst, nutzt
#: niemandem. Dann wird lieber die Liste gekürzt.
_FULL_LIST_MIN_FACTOR: Final = 0.76

#: Fußnote nach Anhang XIII der VO (EU) Nr. 1169/2011.
_REFERENCE_HINT: Final = (
    "Referenzmenge für einen durchschnittlichen Erwachsenen (8400 kJ / 2000 kcal)"
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


def date_lines(options: LabelOptions) -> list[str]:
    """Datumsangaben, je eine eigene Zeile.

    Backdatum und Mindesthaltbarkeit standen früher nebeneinander in einer
    Zeile. Zusammen wurde die so lang, dass sie über beide Ränder hinauslief.
    Zwei Zeilen sind auch inhaltlich richtiger - es sind zwei verschiedene
    Angaben, und die Mindesthaltbarkeit ist die rechtlich geregelte.
    """
    lines: list[str] = []
    if options.show_date:
        baked = options.baked_on or date.today()
        lines.append(f"gebacken am {baked.strftime('%d.%m.%Y')}")
    if options.best_before:
        lines.append(f"mindestens haltbar bis {options.best_before.strftime('%d.%m.%Y')}")
    return lines


def render_label(
    nutrients: Nutrients,
    options: LabelOptions,
    *,
    fonts: FontSet | None = None,
) -> Image.Image:
    """Zeichnet das Etikett.

    Der Aufbau wird zuerst *gemessen* und erst dann gezeichnet: Für jede Stufe
    aus :data:`_SCALE_STEPS` wird geprüft, ob Kopf, Nährwerttabelle,
    Nettogewicht, mindestens eine Zeile Zutatenverzeichnis und die Fußzeile
    zusammen auf das Etikett passen. Gezeichnet wird mit der größten Stufe, die
    noch passt.

    Vorher standen feste Abstände im Code, abgestimmt auf ein einziges Format.
    Auf dem kleinen Aufkleber schoben sich die Blöcke dadurch übereinander.

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

    image = Image.new("RGB", (width, height), palette.background)
    draw = ImageDraw.Draw(image)

    metrics = _fitting_metrics(
        draw,
        nutrients,
        options,
        fonts=fonts,
        pixels_per_mm=options.dpi / 25.4,
        width=width,
        height=height,
    )
    margin = metrics.mm(5.0)
    left = margin + metrics.mm(2.0)
    right = width - margin - metrics.mm(2.0)

    # Dünner Rahmen: gibt dem Etikett eine Kante zum Ausschneiden.
    draw.rectangle(
        [margin // 2, margin // 2, width - margin // 2, height - margin // 2],
        outline=palette.rule,
        width=max(1, metrics.mm(0.3)),
    )

    y = _draw_head(
        draw,
        options,
        palette=palette,
        fonts=fonts,
        m=metrics,
        left=left,
        right=right,
        top=margin + metrics.mm(2.0),
    )
    y = _draw_nutrition(
        draw,
        nutrients,
        options,
        palette=palette,
        fonts=fonts,
        m=metrics,
        left=left,
        right=right,
        top=y,
    )
    y = _draw_net_weight(
        draw,
        options,
        palette=palette,
        fonts=fonts,
        m=metrics,
        left=left,
        right=right,
        top=y,
    )
    footer_top = _draw_footer(
        draw,
        options,
        palette=palette,
        fonts=fonts,
        m=metrics,
        left=left,
        right=right,
        bottom=height - margin - metrics.mm(2.0),
    )

    if options.show_ingredients and options.ingredients:
        _draw_ingredients(
            draw,
            options,
            palette=palette,
            fonts=fonts,
            m=metrics,
            left=left,
            right=right,
            top=y,
            bottom=footer_top,
        )

    return image


def _fitting_metrics(
    draw: ImageDraw.ImageDraw,
    nutrients: Nutrients,
    options: LabelOptions,
    *,
    fonts: FontSet,
    pixels_per_mm: float,
    width: int,
    height: int,
) -> _Metrics:
    """Größte Typografiestufe, mit der alles auf das Etikett passt.

    In zwei Durchgängen: Zuerst wird versucht, das **vollständige**
    Zutatenverzeichnis unterzubringen - es ist die gesetzlich vorgeschriebene
    Angabe und wiegt schwerer als ein Millimeter Schriftgröße. Gelingt das bis
    :data:`_FULL_LIST_MIN_FACTOR` nicht, entscheidet der zweite Durchgang nur
    noch über den festen Teil, und die Liste kürzt sich selbst.
    """
    for factor in _SCALE_STEPS:
        if factor < _FULL_LIST_MIN_FACTOR:
            break
        metrics = _Metrics(pixels_per_mm, factor)
        needed = _required_height(
            draw, nutrients, options, fonts=fonts, m=metrics, width=width, full_ingredients=True
        )
        if needed <= height:
            return metrics

    for factor in _SCALE_STEPS:
        metrics = _Metrics(pixels_per_mm, factor)
        needed = _required_height(draw, nutrients, options, fonts=fonts, m=metrics, width=width)
        if needed <= height:
            return metrics
    return _Metrics(pixels_per_mm, _SCALE_STEPS[-1])


def _required_height(
    draw: ImageDraw.ImageDraw,
    nutrients: Nutrients,
    options: LabelOptions,
    *,
    fonts: FontSet,
    m: _Metrics,
    width: int,
    full_ingredients: bool = False,
) -> int:
    """Platzbedarf bei der gegebenen Stufe.

    Args:
        full_ingredients: Rechnet das Zutatenverzeichnis mit allen Zeilen ein.
            Sonst wird nur *eine* Zeile veranschlagt - die Liste darf sich
            kürzen, alles andere nicht.
    """
    inner_width = width - 2 * (m.mm(5.0) + m.mm(2.0))
    total = 2 * (m.mm(5.0) + m.mm(2.0))

    title = _wrap(draw, single_line(options.title), _font_title(fonts, m), inner_width)
    total += max(1, len(title)) * m.scaled(5.6)

    subtitle = single_line(options.subtitle)
    if subtitle:
        lines = _wrap(draw, subtitle, _font_subtitle(fonts, m), inner_width)
        total += m.scaled(0.6) + len(lines) * m.scaled(3.4)

    dates = date_lines(options)
    if dates:
        total += m.scaled(0.8) + len(dates) * m.scaled(3.4)

    total += m.scaled(1.6) + m.scaled(3.4)  # Trennlinie mit Abstand

    rows = _nutrition_rows(nutrients, show_fiber=options.show_fiber)
    total += m.scaled(4.6) + len(rows) * m.scaled(4.2) + m.scaled(3.0)

    if options.net_weight_g > 0:
        total += m.scaled(2.8) + m.scaled(6.0)

    if options.show_ingredients and options.ingredients:
        total += m.scaled(4.0)  # Überschrift
        if full_ingredients:
            text = single_line(", ".join(options.ingredients))
            lines = _wrap(draw, text, _font_small(fonts, m), inner_width)
            total += len(lines) * m.scaled(3.0)
        else:
            total += m.scaled(3.0)  # mindestens eine Zeile

    return total + _footer_height(draw, options, fonts, m, inner_width)


def _footer_height(
    draw: ImageDraw.ImageDraw,
    options: LabelOptions,
    fonts: FontSet,
    m: _Metrics,
    inner_width: int,
) -> int:
    """Höhe von Referenzhinweis und Fußzeile."""
    height = m.scaled(2.0)
    if options.show_reference_hint:
        lines = _wrap(draw, _REFERENCE_HINT, _font_hint(fonts, m), inner_width)
        height += len(lines) * m.scaled(2.4)
    if single_line(options.footer):
        height += m.scaled(3.4)
    return height


# ── Schriftgrößen ──────────────────────────────────────────────────────────


def _font_title(fonts: FontSet, m: _Metrics) -> Font:
    return fonts.get(m.scaled(4.6), bold=True)


def _font_subtitle(fonts: FontSet, m: _Metrics) -> Font:
    return fonts.get(m.scaled(2.6))


def _font_section(fonts: FontSet, m: _Metrics) -> Font:
    return fonts.get(m.scaled(2.9), bold=True)


def _font_body(fonts: FontSet, m: _Metrics, *, bold: bool = False) -> Font:
    return fonts.get(m.scaled(2.7), bold=bold)


def _font_small(fonts: FontSet, m: _Metrics) -> Font:
    return fonts.get(m.scaled(2.1))


def _font_weight(fonts: FontSet, m: _Metrics) -> Font:
    return fonts.get(m.scaled(3.6), bold=True)


def _font_hint(fonts: FontSet, m: _Metrics) -> Font:
    return fonts.get(m.scaled(1.7))


# ── Einzelne Blöcke ────────────────────────────────────────────────────────


def _draw_head(
    draw: ImageDraw.ImageDraw,
    options: LabelOptions,
    *,
    palette: _Palette,
    fonts: FontSet,
    m: _Metrics,
    left: int,
    right: int,
    top: int,
) -> int:
    """Titel, Untertitel, Datumszeilen und Trennlinie."""
    y = _draw_wrapped_centered(
        draw,
        single_line(options.title),
        font=_font_title(fonts, m),
        colour=palette.accent,
        left=left,
        right=right,
        top=top,
        line_height=m.scaled(5.6),
    )

    subtitle = single_line(options.subtitle)
    if subtitle:
        y = _draw_wrapped_centered(
            draw,
            subtitle,
            font=_font_subtitle(fonts, m),
            colour=palette.muted,
            left=left,
            right=right,
            top=y + m.scaled(0.6),
            line_height=m.scaled(3.4),
        )

    dates = date_lines(options)
    if dates:
        y += m.scaled(0.8)
        font = _font_small(fonts, m)
        centre = (left + right) // 2
        for line in dates:
            draw.text((centre, y), line, fill=palette.muted, font=font, anchor="mt")
            y += m.scaled(3.4)

    y += m.scaled(1.6)
    draw.line([(left, y), (right, y)], fill=palette.accent, width=max(1, m.mm(0.5)))
    return y + m.scaled(3.4)


def _draw_nutrition(
    draw: ImageDraw.ImageDraw,
    nutrients: Nutrients,
    options: LabelOptions,
    *,
    palette: _Palette,
    fonts: FontSet,
    m: _Metrics,
    left: int,
    right: int,
    top: int,
) -> int:
    """Überschrift und Nährwerttabelle."""
    draw.text((left, top), "Nährwerte je 100 g", fill=palette.accent, font=_font_section(fonts, m))
    y = top + m.scaled(4.6)

    rows = _nutrition_rows(nutrients, show_fiber=options.show_fiber)
    row_height = m.scaled(4.2)
    panel_top = y - m.scaled(1.2)
    draw.rectangle(
        [
            left - m.mm(1.5),
            panel_top,
            right + m.mm(1.5),
            panel_top + len(rows) * row_height + m.scaled(2.4),
        ],
        fill=palette.panel,
    )

    body = _font_body(fonts, m)
    body_bold = _font_body(fonts, m, bold=True)
    for label, value, indented, emphasised in rows:
        font = body_bold if emphasised else body
        colour = palette.muted if indented else palette.text
        draw.text((left + (m.scaled(3.0) if indented else 0), y), label, fill=colour, font=font)
        draw.text((right, y), value, fill=colour, font=font, anchor="rt")
        y += row_height

    return y + m.scaled(3.0)


def _draw_net_weight(
    draw: ImageDraw.ImageDraw,
    options: LabelOptions,
    *,
    palette: _Palette,
    fonts: FontSet,
    m: _Metrics,
    left: int,
    right: int,
    top: int,
) -> int:
    """Trennlinie und Nettogewicht."""
    if options.net_weight_g <= 0:
        return top
    draw.line([(left, top), (right, top)], fill=palette.rule, width=max(1, m.mm(0.25)))
    y = top + m.scaled(2.8)
    draw.text(
        ((left + right) // 2, y),
        f"Nettogewicht {_format_weight(options.net_weight_g)}",
        fill=palette.accent,
        font=_font_weight(fonts, m),
        anchor="mt",
    )
    return y + m.scaled(6.0)


def _draw_footer(
    draw: ImageDraw.ImageDraw,
    options: LabelOptions,
    *,
    palette: _Palette,
    fonts: FontSet,
    m: _Metrics,
    left: int,
    right: int,
    bottom: int,
) -> int:
    """Zeichnet die Fußzeile von unten nach oben.

    Returns:
        Das ``y``, an dem der Fuß beginnt - die Untergrenze für alles darüber.
    """
    centre = (left + right) // 2
    y = bottom

    footer = single_line(options.footer)
    if footer:
        draw.text((centre, y), footer, fill=palette.muted, font=_font_small(fonts, m), anchor="mb")
        y -= m.scaled(3.4)

    if options.show_reference_hint:
        font = _font_hint(fonts, m)
        for line in reversed(_wrap(draw, _REFERENCE_HINT, font, right - left)):
            draw.text((centre, y), line, fill=palette.muted, font=font, anchor="mb")
            y -= m.scaled(2.4)

    return y - m.scaled(2.0)


def _draw_ingredients(
    draw: ImageDraw.ImageDraw,
    options: LabelOptions,
    *,
    palette: _Palette,
    fonts: FontSet,
    m: _Metrics,
    left: int,
    right: int,
    top: int,
    bottom: int,
) -> None:
    """Überschrift und Zutatenverzeichnis im verbleibenden Platz.

    Reicht der Platz nicht, wird die Schrift stufenweise verkleinert und
    zuletzt gekürzt: Ein Brot mit zwölf Zutaten hat ein deutlich längeres
    Verzeichnis als eines mit dreien.
    """
    draw.text((left, top), "Zutaten", fill=palette.accent, font=_font_section(fonts, m))
    y = top + m.scaled(4.0)
    available = bottom - y
    if available <= 0:
        return

    text = single_line(", ".join(options.ingredients))
    font = _font_small(fonts, m)
    line_height = m.scaled(3.0)
    lines = _wrap(draw, text, font, right - left)

    for size_mm, gap_mm in ((2.1, 3.0), (1.9, 2.7), (1.7, 2.4), (1.5, 2.1)):
        font = fonts.get(m.scaled(size_mm))
        line_height = m.scaled(gap_mm)
        lines = _wrap(draw, text, font, right - left)
        if len(lines) * line_height <= available:
            break
    else:
        max_lines = max(1, available // line_height)
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            lines[-1] = lines[-1].rstrip(", ") + " …"

    for line in lines:
        draw.text((left, y), line, fill=palette.muted, font=font)
        y += line_height


def _nutrition_rows(nutrients: Nutrients, *, show_fiber: bool) -> list[tuple[str, str, bool, bool]]:
    """Zeilen der Nährwerttabelle in der gesetzlich vorgegebenen Reihenfolge.

    Returns:
        Liste aus ``(Bezeichnung, Wert, eingerückt, hervorgehoben)``.
    """
    rows: list[tuple[str, str, bool, bool]] = [
        ("Brennwert", declare_energy(as_declarable(nutrients.energy_kcal)), False, True),
        ("Fett", _grams("fat", nutrients), False, False),
        ("davon gesättigte Fettsäuren", _grams("saturated_fat", nutrients), True, False),
        ("Kohlenhydrate", _grams("carbs", nutrients), False, False),
        ("davon Zucker", _grams("sugar", nutrients), True, False),
    ]
    if show_fiber:
        rows.append(("Ballaststoffe", _grams("fiber", nutrients), False, False))
    rows.append(("Eiweiß", _grams("protein", nutrients), False, False))
    rows.append(("Salz", _grams("salt", nutrients), False, False))
    return rows


def _grams(field_name: str, nutrients: Nutrients) -> str:
    """Gerundete Angabe eines Nährstoffs nach der EU-Rundungsregel."""
    return declare_nutrient(field_name, as_declarable(getattr(nutrients, field_name))).text


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
