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

Preise erscheinen bewusst nie auf dem Etikett. Es taugt für verschenkte Brote
wie für den Verkauf: Im Verkaufsmodus (:attr:`LabelOptions.for_sale`) hält
jede Schrift die Mindest-x-Höhe ein, die Ziffern der Füllmenge ihre
Mindesthöhe, und das Zutatenverzeichnis wird nicht zugunsten der Schriftgröße
gekürzt. :func:`measure_label` prüft das gezeichnete Ergebnis.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Final

from PIL import Image, ImageDraw, ImageFont

from brotrechner.core.labeling import Run, parse_emphasis
from brotrechner.core.nutrients import Nutrients
from brotrechner.core.rounding import as_declarable, declare_energy, declare_nutrient
from brotrechner.core.sales import SaleIssue
from brotrechner.export.fonts import Font, FontSet, ink_height, load_font_set

__all__ = [
    "MAX_LABEL_MM",
    "MAX_LABEL_PIXELS",
    "MIN_LABEL_MM",
    "MIN_X_HEIGHT_MM",
    "LabelOptions",
    "LabelReport",
    "LabelSize",
    "LabelTheme",
    "measure_label",
    "render_and_measure",
    "render_label",
    "required_digit_height_mm",
]

#: Mindest-x-Höhe der Pflichtangaben in Millimetern (Artikel 13 Abs. 2 und
#: Anhang IV der VO (EU) Nr. 1169/2011). Die Ausnahme von 0,9 mm gilt nur für
#: Packungen, deren größte Oberfläche kleiner als 80 cm² ist - ein Brotbeutel
#: ist größer.
MIN_X_HEIGHT_MM: Final = 1.2

#: Mindesthöhe der Ziffern der Füllmenge je Gewichtsstufe: bis 50 g 2 mm, bis
#: 200 g 3 mm, bis 1 kg 4 mm, darüber 6 mm (Richtlinie 76/211/EWG, Anhang I
#: Nr. 3.1; in Deutschland umgesetzt in der Fertigpackungsverordnung). Für
#: Packungen ungleicher Füllmenge, die eine Preisauszeichnungswaage
#: beschriftet, lässt die Verordnung 2 mm genügen - hier gilt bewusst die
#: strengere Staffel.
_DIGIT_HEIGHTS: Final[tuple[tuple[float, float], ...]] = ((50.0, 2.0), (200.0, 3.0), (1000.0, 4.0))
_DIGIT_HEIGHT_ABOVE: Final = 6.0
_DIGITS: Final = "0123456789"

#: Rechenungenauigkeit beim Vergleich von Millimetern aus ganzen Pixeln.
_EPSILON: Final = 1e-9

#: Grenzen für ein eigenes Format. Nach unten bleiben nach den Rändern 16 mm
#: Breite für den Inhalt; nach oben ist ein A4-Blatt die Grenze - größer ist
#: kein Etikett, und das Bild wüchse ins Unermessliche.
MIN_LABEL_MM: Final = 30.0
MAX_LABEL_MM: Final = 297.0

#: Höchstzahl an Pixeln eines Etikettbilds. Ein Blatt A4 in 600 dpi hat rund
#: 35 Millionen; in 1200 dpi wären es 139 Millionen und über 400 MB Speicher.
MAX_LABEL_PIXELS: Final = 40_000_000

_NET_WEIGHT_WORD: Final = "Nettogewicht"
_NUTRITION_HEADING: Final = "Nährwerte je 100 g"
_INGREDIENTS_HEADING: Final = "Zutaten"


def required_digit_height_mm(grams: float) -> float:
    """Mindesthöhe der Ziffern einer Füllmenge von ``grams`` Gramm in Millimetern."""
    for limit, height in _DIGIT_HEIGHTS:
        if grams <= limit:
            return height
    return _DIGIT_HEIGHT_ABOVE


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
    #: Zutatenverzeichnis-Regel der VO (EU) Nr. 1169/2011. Allergene stehen in
    #: ``*Sternchen*`` und werden fett gedruckt.
    ingredients: Sequence[str] = field(default_factory=tuple)
    #: Allergenangabe für ein Etikett ohne Zutatenverzeichnis, etwa
    #: "Enthält: Weizen, Milch" (Artikel 21 Abs. 1). Erscheint nur, wenn kein
    #: Verzeichnis gedruckt wird.
    allergen_note: str = ""
    net_weight_g: float = 0.0

    #: Etikett für den Verkauf: Jede Schrift hat mindestens
    #: :data:`MIN_X_HEIGHT_MM` x-Höhe, die Ziffern der Füllmenge die Höhe nach
    #: :func:`required_digit_height_mm`, und das Zutatenverzeichnis wird nicht
    #: zugunsten der Schriftgröße gekürzt.
    for_sale: bool = False
    #: Name und Anschrift des Lebensmittelunternehmers (Artikel 9 Abs. 1 h),
    #: mehrzeilig wie eingegeben.
    producer: str = ""
    #: Aufbewahrungshinweis, etwa "Trocken und bei Raumtemperatur lagern."
    storage_hint: str = ""
    #: Eigenes Format (Breite, Höhe) in Millimetern - etwa die Etiketten eines
    #: Bogens, die keinem der festen Formate entsprechen. Hat Vorrang vor
    #: ``size``.
    custom_mm: tuple[float, float] | None = None

    @property
    def millimeters(self) -> tuple[float, float]:
        """Breite und Höhe des Etiketts in Millimetern."""
        return self.custom_mm if self.custom_mm is not None else self.size.millimeters

    def pixel_size(self) -> tuple[int, int]:
        """Bildgröße in Pixeln für die gewählte Auflösung."""
        width_mm, height_mm = self.millimeters
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
    #: Kleinste Schriftgröße in Pixeln; 0, wenn keine Mindestgröße gilt.
    min_text_px: int = 0

    def mm(self, value: float) -> int:
        """Millimeter in Pixel, ohne Stauchung - für Ränder und Linienstärken."""
        return max(1, round(value * self.pixels_per_mm))

    def scaled(self, value: float) -> int:
        """Millimeter in Pixel, mit Stauchung - für Abstände."""
        return max(1, round(value * self.factor * self.pixels_per_mm))

    def text(self, size_mm: float) -> int:
        """Schriftgröße in Pixeln: gestaucht, aber nie unter der Mindestgröße."""
        return max(self.scaled(size_mm), self.min_text_px)

    def line(self, size_mm: float, gap_mm: float) -> int:
        """Zeilenhöhe zu einer Schrift von ``size_mm``.

        Hebt die Mindestgröße die Schrift an, wächst die Zeile im selben
        Verhältnis mit - sonst stießen die Zeilen aneinander.
        """
        if self.min_text_px <= self.scaled(size_mm):
            return self.scaled(gap_mm)
        return max(self.scaled(gap_mm), round(self.min_text_px * gap_mm / size_mm))


#: Stufen, in denen die Typografie verkleinert wird, bis der Inhalt passt.
#: Unter 0,62 wäre ein Etikett nicht mehr zuverlässig lesbar; dann kürzt
#: stattdessen das Zutatenverzeichnis. Im Verkauf hält jede Stufe die
#: Mindestgröße ein - kleiner als sie wird keine Schrift.
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


@dataclass(frozen=True, slots=True)
class LabelReport:
    """Befund eines gezeichneten Etiketts.

    Gemessen wird das Bild, nicht die Absicht: Die x-Höhe stammt aus der Tinte
    jeder Schrift, mit der tatsächlich Text entstanden ist.
    """

    #: Alles passt, das Zutatenverzeichnis vollständig, und der Fuß steht
    #: auf dem Etikett statt darunter.
    fits: bool
    #: Alles außer dem Zutatenverzeichnis passt - es darf sich auf einem
    #: Geschenketikett kürzen, der Rest nicht.
    fixed_part_fits: bool
    scalable_font: bool
    #: Kleinste x-Höhe aller gezeichneten Texte.
    min_x_height_mm: float
    #: Höhe der Ziffern der Füllmenge; 0 ohne Füllmenge.
    net_weight_digit_mm: float
    #: Verlangte Ziffernhöhe nach :func:`required_digit_height_mm`; 0 ohne
    #: Füllmenge und außerhalb des Verkaufs.
    required_digit_mm: float
    #: Die Füllmenge passt in ihrer Schriftgröße in die Breite.
    net_weight_width_ok: bool
    #: Höhe, die der Inhalt samt vollständigem Verzeichnis braucht.
    required_height_px: int
    available_height_px: int

    def issues(self, *, for_sale: bool) -> list[SaleIssue]:
        """Was am Etikett nicht stimmt.

        Args:
            for_sale: Prüft zusätzlich die Vorgaben für den Verkauf. Ein
                Geschenketikett darf kleinere Schrift und ein gekürztes
                Verzeichnis haben - aber nichts darf unten abgeschnitten werden.
        """
        if not for_sale:
            if self.fixed_part_fits:
                return []
            return [
                SaleIssue(
                    "does_not_fit",
                    "Der Inhalt passt nicht auf dieses Format - der untere Teil wird "
                    "abgeschnitten. Größeres Format wählen oder Texte kürzen.",
                )
            ]
        issues: list[SaleIssue] = []
        if not self.scalable_font:
            issues.append(
                SaleIssue(
                    "no_scalable_font",
                    "Keine skalierbare Schrift gefunden - die Mindestschriftgröße lässt "
                    "sich nicht einhalten (Art. 13 Abs. 2). Bitte eine TrueType-Schrift "
                    "wie DejaVu Sans installieren.",
                )
            )
        if not self.fits:
            issues.append(
                SaleIssue(
                    "does_not_fit",
                    "Der Inhalt passt nicht vollständig auf dieses Format, wenn jede Schrift "
                    "die Mindestgröße hat - größeres Format wählen oder Texte kürzen, etwa "
                    "Fußzeile oder Referenzhinweis weglassen (Art. 13 Abs. 2, Anhang IV)",
                )
            )
        if self.min_x_height_mm + _EPSILON < MIN_X_HEIGHT_MM:
            issues.append(
                SaleIssue(
                    "font_too_small",
                    f"Schrift zu klein: x-Höhe {_mm(self.min_x_height_mm)} statt mindestens "
                    f"{_mm(MIN_X_HEIGHT_MM)} (Art. 13 Abs. 2, Anhang IV)",
                )
            )
        # Zu schmal ist die Ursache, zu kleine Ziffern sind dann nur die Folge.
        if not self.net_weight_width_ok:
            issues.append(
                SaleIssue(
                    "net_weight_too_wide",
                    "Die Füllmenge passt in der vorgeschriebenen Ziffernhöhe von "
                    f"{_mm(self.required_digit_mm)} nicht in die Breite - größeres Format "
                    "wählen (Fertigpackungsverordnung)",
                )
            )
        elif self.net_weight_digit_mm + _EPSILON < self.required_digit_mm:
            issues.append(
                SaleIssue(
                    "net_weight_too_small",
                    f"Ziffern der Füllmenge {_mm(self.net_weight_digit_mm)} hoch statt "
                    f"mindestens {_mm(self.required_digit_mm)} (Fertigpackungsverordnung)",
                )
            )
        return issues


def _mm(value: float) -> str:
    """Millimeter mit zwei Nachkommastellen und deutschem Komma."""
    return f"{value:.2f} mm".replace(".", ",")


class _MeasuringDraw(ImageDraw.ImageDraw):
    """Zeichnet wie gewohnt und merkt sich jede Schrift, mit der Text entsteht.

    Daraus misst :func:`measure_label` die kleinste x-Höhe - am Ergebnis, nicht
    an der Absicht. Ein später ergänzter Textblock kann so nicht unbemerkt zu
    klein geraten.
    """

    def __init__(self, image: Image.Image) -> None:
        super().__init__(image)
        self.fonts_used: dict[int, Font] = {}

    def text(self, xy: Any, text: Any, *args: Any, **kwargs: Any) -> None:
        font = kwargs.get("font")
        if font is not None and text:
            self.fonts_used[id(font)] = font
        super().text(xy, text, *args, **kwargs)


def measure_label(
    nutrients: Nutrients,
    options: LabelOptions,
    *,
    fonts: FontSet | None = None,
) -> LabelReport:
    """Zeichnet das Etikett und prüft das Ergebnis.

    Args:
        nutrients: Nährwerte je 100 g fertiges Brot.
        options: Gestaltung und Inhalte - geprüft in der dort gewählten
            Auflösung, denn die Schrift rundet auf ganze Pixel.
        fonts: Vorgeladener Schriftsatz; ``None`` lädt den des Systems.

    Raises:
        ValueError: Wie :func:`render_label`.
    """
    return _render(nutrients, options, fonts or load_font_set())[1]


def render_and_measure(
    nutrients: Nutrients,
    options: LabelOptions,
    *,
    fonts: FontSet | None = None,
) -> tuple[Image.Image, LabelReport]:
    """Zeichnet das Etikett und prüft es in einem Durchgang.

    Für die Vorschau im Dialog: Bild und Befund stammen aus demselben
    Zeichenvorgang und passen damit sicher zusammen.

    Raises:
        ValueError: Wie :func:`render_label`.
    """
    return _render(nutrients, options, fonts or load_font_set())


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
        ValueError: Bei unsinniger Auflösung, negativem Nettogewicht, einem
            Format außerhalb von :data:`MIN_LABEL_MM` bis :data:`MAX_LABEL_MM`
            oder mehr als :data:`MAX_LABEL_PIXELS` Pixeln.
    """
    return _render(nutrients, options, fonts or load_font_set())[0]


def _render(
    nutrients: Nutrients, options: LabelOptions, fonts: FontSet
) -> tuple[Image.Image, LabelReport]:
    """Zeichnet das Etikett und misst dabei, was entsteht."""
    if options.dpi < 36 or options.dpi > 1200:
        raise ValueError(f"Auflösung muss zwischen 36 und 1200 dpi liegen, war {options.dpi}")
    if options.net_weight_g < 0:
        raise ValueError(f"Nettogewicht darf nicht negativ sein, war {options.net_weight_g}")
    if not all(MIN_LABEL_MM <= side <= MAX_LABEL_MM for side in options.millimeters):
        width_mm, height_mm = options.millimeters
        raise ValueError(
            f"Etikettformat muss je Seite zwischen {MIN_LABEL_MM:g} und {MAX_LABEL_MM:g} mm "
            f"liegen, war {width_mm:g} × {height_mm:g} mm"
        )
    pixels = options.pixel_size()
    if pixels[0] * pixels[1] > MAX_LABEL_PIXELS:
        raise ValueError(
            f"Etikett zu groß für {options.dpi} dpi: {pixels[0]} × {pixels[1]} Pixel - "
            "bitte eine kleinere Auflösung wählen"
        )

    palette = options.theme.colors
    width, height = options.pixel_size()

    image = Image.new("RGB", (width, height), palette.background)
    draw = _MeasuringDraw(image)

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
    # Der Fuß steht unten auf dem Etikett. Reicht der Platz nicht, rückt er
    # unter den Inhalt und wird am Rand abgeschnitten - überlagert wird nie.
    # Im Verkauf bleibt dabei das Zutatenverzeichnis vollständig.
    inner = right - left
    reserved = _body_height(
        draw, options, fonts=fonts, m=metrics, width=inner, full_ingredients=options.for_sale
    ) + _footer_height(draw, options, fonts, metrics, inner)
    bottom = height - margin - metrics.mm(2.0)
    pushed_out = y + reserved > bottom
    footer_top = _draw_footer(
        draw,
        options,
        palette=palette,
        fonts=fonts,
        m=metrics,
        left=left,
        right=right,
        bottom=max(bottom, y + reserved),
    )

    complete = True
    if _shows_ingredients(options):
        complete = _draw_ingredients(
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
    elif options.allergen_note.strip():
        _draw_allergen_note(
            draw, options, palette=palette, fonts=fonts, m=metrics, left=left, right=right, top=y
        )

    fixed = _required_height(draw, nutrients, options, fonts=fonts, m=metrics, width=width)
    pixels_per_mm = metrics.pixels_per_mm
    x_height = min((ink_height(font, "x") for font in draw.fonts_used.values()), default=math.inf)
    weight = (
        _net_weight_layout(draw, options, fonts, metrics, right - left)
        if options.net_weight_g > 0
        else None
    )
    report = LabelReport(
        fits=complete and not pushed_out,
        fixed_part_fits=fixed <= height,
        scalable_font=fonts.is_scalable,
        min_x_height_mm=x_height / pixels_per_mm,
        net_weight_digit_mm=(
            ink_height(weight.value_font, _DIGITS) / pixels_per_mm if weight else 0.0
        ),
        required_digit_mm=(
            required_digit_height_mm(options.net_weight_g) if weight and options.for_sale else 0.0
        ),
        net_weight_width_ok=weight.fits_width if weight else True,
        required_height_px=_required_height(
            draw, nutrients, options, fonts=fonts, m=metrics, width=width, full_ingredients=True
        ),
        available_height_px=height,
    )
    return image, report


def _shows_ingredients(options: LabelOptions) -> bool:
    """Wird ein Zutatenverzeichnis gedruckt?"""
    return options.show_ingredients and bool(options.ingredients)


def _ingredient_runs(options: LabelOptions) -> list[Run]:
    """Das Zutatenverzeichnis als Folge normaler und fetter Textstücke.

    Jede Zutat wird für sich zerlegt: Ein nicht geschlossenes Sternchen in
    einer Bezeichnung darf nicht mit dem der nächsten ein Paar bilden.
    """
    runs: list[Run] = []
    for index, entry in enumerate(options.ingredients):
        if index:
            runs.append(Run(", "))
        runs.extend(parse_emphasis(single_line(entry)))
    return runs


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

    Im Verkauf gibt es den zweiten Durchgang nicht: Dort wird bis zur
    kleinsten Stufe versucht, das vollständige Verzeichnis unterzubringen.
    Passt es auch dann nicht, meldet :func:`measure_label` das.
    """
    minimum = _min_text_px(fonts, options, pixels_per_mm)
    for factor in _SCALE_STEPS:
        if factor < _FULL_LIST_MIN_FACTOR and not options.for_sale:
            break
        metrics = _Metrics(pixels_per_mm, factor, minimum)
        needed = _required_height(
            draw, nutrients, options, fonts=fonts, m=metrics, width=width, full_ingredients=True
        )
        if needed <= height:
            return metrics
    if options.for_sale:
        return _Metrics(pixels_per_mm, _SCALE_STEPS[-1], minimum)

    for factor in _SCALE_STEPS:
        metrics = _Metrics(pixels_per_mm, factor)
        needed = _required_height(draw, nutrients, options, fonts=fonts, m=metrics, width=width)
        if needed <= height:
            return metrics
    return _Metrics(pixels_per_mm, _SCALE_STEPS[-1])


def _min_text_px(fonts: FontSet, options: LabelOptions, pixels_per_mm: float) -> int:
    """Kleinste Schriftgröße in Pixeln: im Verkauf die für 1,2 mm x-Höhe, sonst 0."""
    if not options.for_sale:
        return 0
    return fonts.size_for_ink("x", MIN_X_HEIGHT_MM * pixels_per_mm) or 0


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

    _, title, title_line = _title_layout(draw, options, fonts, m, inner_width)
    total += max(1, len(title)) * title_line

    subtitle = single_line(options.subtitle)
    if subtitle:
        lines = _wrap(draw, subtitle, _font_subtitle(fonts, m), inner_width)
        total += m.scaled(0.6) + len(lines) * m.line(2.6, 3.4)

    dates = _date_rows(draw, options, _font_small(fonts, m), inner_width)
    if dates:
        total += m.scaled(0.8) + len(dates) * m.line(2.1, 3.4)

    total += m.scaled(1.6) + m.scaled(3.4)  # Trennlinie mit Abstand

    rows = _table_rows(draw, nutrients, options, fonts=fonts, m=m, width=inner_width)
    header = _wrap(draw, _NUTRITION_HEADING, _font_section(fonts, m), inner_width)
    total += _heading_height(header, m, gap_mm=4.6)
    total += sum(row.height(m) for row in rows) + m.scaled(3.0)

    if options.net_weight_g > 0:
        total += _net_weight_layout(draw, options, fonts, m, inner_width).height(m)

    total += _body_height(
        draw, options, fonts=fonts, m=m, width=inner_width, full_ingredients=full_ingredients
    )
    return total + _footer_height(draw, options, fonts, m, inner_width)


def _body_height(
    draw: ImageDraw.ImageDraw,
    options: LabelOptions,
    *,
    fonts: FontSet,
    m: _Metrics,
    width: int,
    full_ingredients: bool,
) -> int:
    """Höhe von Zutatenverzeichnis oder Allergenhinweis.

    Args:
        full_ingredients: Rechnet das Verzeichnis mit allen Zeilen ein, sonst
            nur mit einer - es darf sich auf einem Geschenketikett kürzen.
    """
    if _shows_ingredients(options):
        heading = _heading_height(
            _wrap(draw, _INGREDIENTS_HEADING, _font_section(fonts, m), width), m, gap_mm=4.0
        )
        if not full_ingredients:
            return heading + m.line(2.1, 3.0)
        lines = _wrap_runs(
            draw,
            _ingredient_runs(options),
            _font_small(fonts, m),
            _font_small(fonts, m, bold=True),
            width,
        )
        return heading + len(lines) * m.line(2.1, 3.0)
    if options.allergen_note.strip():
        note = _wrap(draw, single_line(options.allergen_note), _font_small(fonts, m), width)
        return m.scaled(1.0) + len(note) * m.line(2.1, 3.0)
    return 0


def _footer_height(
    draw: ImageDraw.ImageDraw,
    options: LabelOptions,
    fonts: FontSet,
    m: _Metrics,
    inner_width: int,
) -> int:
    """Höhe des Fußes: Lagerhinweis, Hersteller, Referenzhinweis und Fußzeile."""
    blocks = _footer_blocks(draw, options, fonts, m, inner_width)
    return m.scaled(2.0) + sum(len(block.lines) * block.line_height for block in blocks)


@dataclass(frozen=True, slots=True)
class _FooterBlock:
    """Ein Absatz im Fuß des Etiketts."""

    lines: list[str]
    font: Font
    line_height: int
    #: Pflichtangaben stehen in der kräftigen Textfarbe, der Rest gedämpft.
    mandatory: bool


def _footer_blocks(
    draw: ImageDraw.ImageDraw, options: LabelOptions, fonts: FontSet, m: _Metrics, width: int
) -> list[_FooterBlock]:
    """Die Absätze des Fußes von oben nach unten.

    Name und Anschrift behalten ihre Zeilen, wie sie eingegeben wurden - auf
    einem schmalen Etikett liest sich eine Anschrift so besser als in einer
    umbrochenen Zeile.
    """
    small = _font_small(fonts, m)
    blocks: list[_FooterBlock] = []
    storage = _wrap(draw, single_line(options.storage_hint), small, width)
    if storage:
        blocks.append(_FooterBlock(storage, small, m.line(2.1, 3.0), mandatory=True))
    producer = [
        part
        for line in options.producer.splitlines()
        for part in _wrap(draw, single_line(line), small, width)
    ]
    if producer:
        blocks.append(_FooterBlock(producer, small, m.line(2.1, 3.0), mandatory=True))
    if options.show_reference_hint:
        hint = _font_hint(fonts, m)
        blocks.append(
            _FooterBlock(
                _wrap(draw, _REFERENCE_HINT, hint, width), hint, m.line(1.7, 2.4), mandatory=False
            )
        )
    footer = _wrap(draw, single_line(options.footer), small, width)
    if footer:
        blocks.append(_FooterBlock(footer, small, m.line(2.1, 3.4), mandatory=False))
    return blocks


def _title_layout(
    draw: ImageDraw.ImageDraw, options: LabelOptions, fonts: FontSet, m: _Metrics, width: int
) -> tuple[Font, list[str], int]:
    """Schrift, Zeilen und Zeilenhöhe des Titels.

    Ein Titel wird lieber etwas kleiner gesetzt als mitten im Wort getrennt -
    "Roggenmischb / rot" war auf dem kleinen Etikett die Folge einer festen
    Titelgröße. Die Schrift schrumpft, bis das längste Wort in die Zeile passt,
    höchstens bis auf die Größe des Fließtexts. Erst darunter wird hart
    getrennt.
    """
    text = single_line(options.title)
    size = m.text(4.6)
    line_height = m.line(4.6, 5.6)
    words = text.split(" ") if text else []

    def widest(px: int) -> float:
        font = fonts.get(px, bold=True)
        return max(draw.textlength(word, font=font) for word in words)

    if words and widest(size) > width:
        floor = m.text(2.7)
        size = max(floor, min(size - 1, int(size * width / widest(size))))
        while size > floor and widest(size) > width:
            size -= 1
        line_height = round(size * 5.6 / 4.6)
    font = fonts.get(size, bold=True)
    return font, _wrap(draw, text, font, width), line_height


def _heading_height(lines: Sequence[str], m: _Metrics, *, gap_mm: float) -> int:
    """Höhe einer Abschnittsüberschrift samt Abstand zum Inhalt darunter."""
    return max(0, len(lines) - 1) * m.line(2.9, 3.6) + m.line(2.9, gap_mm)


def _draw_heading(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    colour: str,
    fonts: FontSet,
    m: _Metrics,
    left: int,
    width: int,
    top: int,
    gap_mm: float,
) -> int:
    """Zeichnet eine Abschnittsüberschrift - auf schmalem Etikett umbrochen.

    Returns:
        Das ``y``, an dem der Abschnitt beginnt.
    """
    font = _font_section(fonts, m)
    lines = _wrap(draw, text, font, width)
    y = top
    for index, line in enumerate(lines):
        if index:
            y += m.line(2.9, 3.6)
        draw.text((left, y), line, fill=colour, font=font)
    return top + _heading_height(lines, m, gap_mm=gap_mm)


def _date_rows(
    draw: ImageDraw.ImageDraw, options: LabelOptions, font: Font, width: int
) -> list[str]:
    """Datumszeilen, jede für sich auf die Breite umgebrochen."""
    return [part for line in date_lines(options) for part in _wrap(draw, line, font, width)]


@dataclass(frozen=True, slots=True)
class _TableRow:
    """Eine Zeile der Nährwerttabelle, auf die Breite des Etiketts gebracht.

    Reicht die Breite nicht für Beschriftung und Wert nebeneinander, wird die
    Beschriftung umbrochen - "davon gesättigte Fettsäuren" lief auf dem
    kleinen Etikett sonst in ihren eigenen Wert hinein. Passt nicht einmal ein
    einzelnes Wort neben den Wert, rückt der Wert in eine eigene Zeile.
    """

    label_lines: tuple[str, ...]
    #: Der Wert; mehr als eine Zeile nur, wenn er allein breiter als das
    #: Etikett ist.
    value_lines: tuple[str, ...]
    indented: bool
    emphasised: bool
    value_below: bool

    def height(self, m: _Metrics) -> int:
        extra = len(self.label_lines) - 1
        if self.value_below:
            extra += len(self.value_lines)
        return m.line(2.7, 4.2) + extra * m.line(2.7, 3.3)


def _table_rows(
    draw: ImageDraw.ImageDraw,
    nutrients: Nutrients,
    options: LabelOptions,
    *,
    fonts: FontSet,
    m: _Metrics,
    width: int,
) -> list[_TableRow]:
    """Die Zeilen der Nährwerttabelle samt Umbruch."""
    rows: list[_TableRow] = []
    for label, value, indented, emphasised in _nutrition_rows(
        nutrients, show_fiber=options.show_fiber
    ):
        font = _font_body(fonts, m, bold=emphasised)
        indent = m.scaled(3.0) if indented else 0
        room = width - indent - m.scaled(2.0) - draw.textlength(value, font=font)
        values = [value]
        if draw.textlength(label, font=font) <= room:
            lines, below = [label], False
        elif all(draw.textlength(word, font=font) <= room for word in label.split(" ")):
            lines, below = _wrap(draw, label, font, int(room)), False
        else:
            lines, below = _wrap(draw, label, font, width - indent), True
            values = _wrap(draw, value, font, width - indent)
        rows.append(_TableRow(tuple(lines), tuple(values), indented, emphasised, below))
    return rows


@dataclass(frozen=True, slots=True)
class _NetWeightLayout:
    """Das Nettogewicht: Wort und Menge, nebeneinander oder untereinander.

    Auf dem kleinen Etikett ragte "Nettogewicht 2,96 kg" über den Rand. Im
    Verkauf wächst zudem die Menge auf die vorgeschriebene Ziffernhöhe - das
    Wort bleibt dabei in seiner Größe.
    """

    value: str
    word_font: Font
    value_font: Font
    one_line: bool
    fits_width: bool
    #: Das Wort, wenn es allein steht - umbrochen, falls das Etikett schmaler ist.
    word_lines: tuple[str, ...]
    #: Höhe einer Zeile, in der das Wort allein steht.
    word_line: int
    #: Höhe der Zeile mit der Menge samt Abstand darunter.
    value_line: int

    def height(self, m: _Metrics) -> int:
        words = 0 if self.one_line else len(self.word_lines) * self.word_line
        return m.scaled(2.8) + words + self.value_line


def _net_weight_layout(
    draw: ImageDraw.ImageDraw, options: LabelOptions, fonts: FontSet, m: _Metrics, width: int
) -> _NetWeightLayout:
    """Schriften und Anordnung des Nettogewichts."""
    value = _format_weight(options.net_weight_g)
    word_px = m.text(3.6)
    value_px = word_px
    if options.for_sale:
        digits = fonts.size_for_ink(
            _DIGITS,
            required_digit_height_mm(options.net_weight_g) * m.pixels_per_mm,
            cuts=(True,),
        )
        value_px = max(value_px, digits or 0)
    word_font = fonts.get(word_px, bold=True)
    value_font = fonts.get(value_px, bold=True)
    value_width = draw.textlength(value, font=value_font)
    fits_width = value_width <= width
    if not fits_width:
        # Lieber kleinere Ziffern als eine Menge, die über den Rand ragt - der
        # Befund meldet, dass die vorgeschriebene Höhe nicht in die Breite passt.
        value_px = max(1, min(value_px - 1, int(value_px * width / value_width)))
        while value_px > 1 and draw.textlength(value, font=fonts.get(value_px, bold=True)) > width:
            value_px -= 1
        value_font = fonts.get(value_px, bold=True)
        value_width = draw.textlength(value, font=value_font)
    together = draw.textlength(f"{_NET_WEIGHT_WORD} ", font=word_font) + value_width
    return _NetWeightLayout(
        value=value,
        word_font=word_font,
        value_font=value_font,
        one_line=together <= width,
        fits_width=fits_width,
        word_lines=tuple(_wrap(draw, _NET_WEIGHT_WORD, word_font, width)),
        word_line=m.line(3.6, 4.4),
        value_line=value_px + m.line(3.6, 6.0) - word_px,
    )


def _ascent(font: Font) -> int:
    """Abstand von der Oberlänge zur Grundlinie in Pixeln."""
    if isinstance(font, ImageFont.FreeTypeFont):
        return font.getmetrics()[0]
    return 0  # pragma: no cover - die Bitmapschrift kennt nur eine Größe


# ── Schriftgrößen ──────────────────────────────────────────────────────────


def _font_subtitle(fonts: FontSet, m: _Metrics) -> Font:
    return fonts.get(m.text(2.6))


def _font_section(fonts: FontSet, m: _Metrics) -> Font:
    return fonts.get(m.text(2.9), bold=True)


def _font_body(fonts: FontSet, m: _Metrics, *, bold: bool = False) -> Font:
    return fonts.get(m.text(2.7), bold=bold)


def _font_small(fonts: FontSet, m: _Metrics, *, bold: bool = False) -> Font:
    return fonts.get(m.text(2.1), bold=bold)


def _font_hint(fonts: FontSet, m: _Metrics) -> Font:
    return fonts.get(m.text(1.7))


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
    title_font, title, title_line = _title_layout(draw, options, fonts, m, right - left)
    centre = (left + right) // 2
    y = top
    # Alle Texte hängen an Ober- oder Unterlänge der Schrift ("a", "d"), nicht
    # an ihrer Tinte ("t", "b"): Nur so stehen die Zeilen in gleichmäßigem
    # Abstand, und Wert und Beschriftung einer Tabellenzeile teilen sich eine
    # Grundlinie. Mit "rt" saßen die Werte sichtbar höher als ihre Beschriftung.
    for line in title:
        draw.text((centre, y), line, fill=palette.accent, font=title_font, anchor="ma")
        y += title_line

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
            line_height=m.line(2.6, 3.4),
        )

    font = _font_small(fonts, m)
    dates = _date_rows(draw, options, font, right - left)
    if dates:
        y += m.scaled(0.8)
        for line in dates:
            draw.text((centre, y), line, fill=palette.muted, font=font, anchor="ma")
            y += m.line(2.1, 3.4)

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
    y = _draw_heading(
        draw,
        _NUTRITION_HEADING,
        colour=palette.accent,
        fonts=fonts,
        m=m,
        left=left,
        width=right - left,
        top=top,
        gap_mm=4.6,
    )

    rows = _table_rows(draw, nutrients, options, fonts=fonts, m=m, width=right - left)
    panel_top = y - m.scaled(1.2)
    draw.rectangle(
        [
            left - m.mm(1.5),
            panel_top,
            right + m.mm(1.5),
            panel_top + sum(row.height(m) for row in rows) + m.scaled(2.4),
        ],
        fill=palette.panel,
    )

    for row in rows:
        font = _font_body(fonts, m, bold=row.emphasised)
        colour = palette.muted if row.indented else palette.text
        x = left + (m.scaled(3.0) if row.indented else 0)
        line_y = y
        for index, text in enumerate(row.label_lines):
            if index:
                line_y += m.line(2.7, 3.3)
            draw.text((x, line_y), text, fill=colour, font=font)
        for text in row.value_lines:
            if row.value_below:
                line_y += m.line(2.7, 3.3)
            draw.text((right, line_y), text, fill=colour, font=font, anchor="ra")
        y += row.height(m)

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
    layout = _net_weight_layout(draw, options, fonts, m, right - left)
    centre = (left + right) // 2
    colour = palette.accent
    if layout.one_line and layout.word_font is layout.value_font:
        text = f"{_NET_WEIGHT_WORD} {layout.value}"
        draw.text((centre, y), text, fill=colour, font=layout.value_font, anchor="ma")
    elif layout.one_line:
        # Verschiedene Größen in einer Zeile teilen sich die Grundlinie.
        word = f"{_NET_WEIGHT_WORD} "
        word_width = draw.textlength(word, font=layout.word_font)
        start = centre - (word_width + draw.textlength(layout.value, font=layout.value_font)) / 2
        baseline = y + _ascent(layout.value_font)
        draw.text((round(start), baseline), word, fill=colour, font=layout.word_font, anchor="ls")
        draw.text(
            (round(start + word_width), baseline),
            layout.value,
            fill=colour,
            font=layout.value_font,
            anchor="ls",
        )
    else:
        for word in layout.word_lines:
            draw.text((centre, y), word, fill=colour, font=layout.word_font, anchor="ma")
            y += layout.word_line
        draw.text((centre, y), layout.value, fill=colour, font=layout.value_font, anchor="ma")
    return y + layout.value_line


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
    for block in reversed(_footer_blocks(draw, options, fonts, m, right - left)):
        colour = palette.text if block.mandatory else palette.muted
        for line in reversed(block.lines):
            draw.text((centre, y), line, fill=colour, font=block.font, anchor="md")
            y -= block.line_height
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
) -> bool:
    """Überschrift und Zutatenverzeichnis im verbleibenden Platz.

    Reicht der Platz nicht, wird die Schrift stufenweise verkleinert und
    zuletzt gekürzt: Ein Brot mit zwölf Zutaten hat ein deutlich längeres
    Verzeichnis als eines mit dreien. Im Verkauf endet das Verkleinern an der
    Mindestgröße.

    Returns:
        ``True``, wenn das Verzeichnis vollständig auf dem Etikett steht.
    """
    y = _draw_heading(
        draw,
        _INGREDIENTS_HEADING,
        colour=palette.accent,
        fonts=fonts,
        m=m,
        left=left,
        width=right - left,
        top=top,
        gap_mm=4.0,
    )
    available = bottom - y
    if available <= 0:
        return False

    runs = _ingredient_runs(options)
    width = right - left
    complete = True
    for size_mm, gap_mm in ((2.1, 3.0), (1.9, 2.7), (1.7, 2.4), (1.5, 2.1)):
        regular = fonts.get(m.text(size_mm))
        bold = fonts.get(m.text(size_mm), bold=True)
        line_height = m.line(size_mm, gap_mm)
        lines = _wrap_runs(draw, runs, regular, bold, width)
        if len(lines) * line_height <= available:
            break
    else:
        max_lines = max(1, available // line_height)
        if len(lines) > max_lines:
            complete = False
            lines = lines[:max_lines]
            # Das Auslassungszeichen braucht Platz: Notfalls weicht das letzte
            # Wort davor, sonst ragte die Zeile über den Rand.
            last = [*lines[-1], [("…", False)]]
            while len(last) > 1 and _line_width(draw, last, regular, bold) > width:
                del last[-2]
            lines[-1] = last

    for line in lines:
        # Allergene fett und in der kräftigeren Textfarbe: Sie sollen sich
        # deutlich vom übrigen Verzeichnis abheben (Artikel 21 Abs. 1).
        _draw_runs_line(
            draw,
            line,
            x=left,
            y=y,
            regular=regular,
            bold=bold,
            fill=palette.muted,
            bold_fill=palette.text,
        )
        y += line_height
    return complete


def _draw_allergen_note(
    draw: ImageDraw.ImageDraw,
    options: LabelOptions,
    *,
    palette: _Palette,
    fonts: FontSet,
    m: _Metrics,
    left: int,
    right: int,
    top: int,
) -> None:
    """Allergenangabe anstelle des Zutatenverzeichnisses."""
    y = top + m.scaled(1.0)
    font = _font_small(fonts, m)
    for line in _wrap(draw, single_line(options.allergen_note), font, right - left):
        draw.text((left, y), line, fill=palette.text, font=font)
        y += m.line(2.1, 3.0)


#: Eine Zeile aus Wörtern, jedes Wort aus Stücken ``(Text, fett)``.
_Word = list[tuple[str, bool]]
_Line = list[_Word]


def _wrap_runs(
    draw: ImageDraw.ImageDraw,
    runs: Sequence[Run],
    regular: Font,
    bold: Font,
    max_width: int,
) -> list[_Line]:
    """Bricht Text aus normalen und fetten Stücken auf die Breite um.

    Ein Wort kann aus mehreren Stücken bestehen ("**Weizen**mehl") und wird
    nie zwischen ihnen getrennt. Nur ein Wort, das allein breiter als die
    Zeile ist, wird hart getrennt, damit nichts über den Rand läuft.
    """
    words: list[_Word] = [[]]
    for run in runs:
        for index, part in enumerate(run.text.split(" ")):
            if index:
                words.append([])
            if part:
                words[-1].append((part, run.bold))
    space = draw.textlength(" ", font=regular)

    lines: list[_Line] = []
    current: _Line = []
    current_width = 0.0
    for word in (w for w in words if w):
        for piece in _split_word(draw, word, regular, bold, max_width):
            width = _word_width(draw, piece, regular, bold)
            if current and current_width + space + width > max_width:
                lines.append(current)
                current, current_width = [], 0.0
            current_width += (space if current else 0.0) + width
            current.append(piece)
    if current:
        lines.append(current)
    return lines


def _split_word(
    draw: ImageDraw.ImageDraw, word: _Word, regular: Font, bold: Font, max_width: int
) -> list[_Word]:
    """Trennt ein Wort, das allein breiter als die Zeile ist, Zeichen für Zeichen."""
    if _word_width(draw, word, regular, bold) <= max_width:
        return [word]
    pieces: list[_Word] = [[]]
    for text, is_bold in word:
        for char in text:
            candidate = [*pieces[-1], (char, is_bold)]
            if pieces[-1] and _word_width(draw, candidate, regular, bold) > max_width:
                pieces.append([(char, is_bold)])
            else:
                pieces[-1] = candidate
    return [_merge_segments(piece) for piece in pieces]


def _merge_segments(word: _Word) -> _Word:
    """Fasst benachbarte Stücke gleicher Auszeichnung zusammen."""
    merged: _Word = []
    for text, is_bold in word:
        if merged and merged[-1][1] == is_bold:
            merged[-1] = (merged[-1][0] + text, is_bold)
        else:
            merged.append((text, is_bold))
    return merged


def _word_width(draw: ImageDraw.ImageDraw, word: _Word, regular: Font, bold: Font) -> float:
    return sum(draw.textlength(text, font=bold if is_bold else regular) for text, is_bold in word)


def _line_width(draw: ImageDraw.ImageDraw, line: _Line, regular: Font, bold: Font) -> float:
    """Breite einer umbrochenen Zeile samt Wortabständen."""
    space = draw.textlength(" ", font=regular)
    return sum(_word_width(draw, word, regular, bold) for word in line) + space * (len(line) - 1)


def _draw_runs_line(
    draw: ImageDraw.ImageDraw,
    line: _Line,
    *,
    x: int,
    y: int,
    regular: Font,
    bold: Font,
    fill: str,
    bold_fill: str,
) -> None:
    """Zeichnet eine Zeile Stück für Stück mit der jeweiligen Schrift und Farbe."""
    space = draw.textlength(" ", font=regular)
    cursor = float(x)
    for index, word in enumerate(line):
        if index:
            cursor += space
        for text, is_bold in word:
            font = bold if is_bold else regular
            draw.text((round(cursor), y), text, fill=bold_fill if is_bold else fill, font=font)
            cursor += draw.textlength(text, font=font)


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
        draw.text((centre, top), line, fill=colour, font=font, anchor="ma")
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
