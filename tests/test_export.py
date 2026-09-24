"""Tests der Ausgabeformate: Etikett, CSV und PDF-Bericht."""

from __future__ import annotations

import csv
import itertools
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, ClassVar
from unittest import mock

import pytest
from hypothesis import given
from hypothesis import strategies as st
from PIL import Image, ImageDraw

from brotrechner.core.analysis import ResolvedItem, analyze
from brotrechner.core.models import Ingredient
from brotrechner.core.nutrients import Nutrients
from brotrechner.export import report
from brotrechner.export.fonts import load_font_set
from brotrechner.export.label import (
    LabelOptions,
    LabelSize,
    LabelTheme,
    date_lines,
    render_label,
)
from brotrechner.export.table import (
    INGREDIENT_COLUMNS,
    write_analysis_csv,
    write_ingredients_csv,
)

#: Ein Brot mit vielen Zutaten - der Fall, an dem sich der Aufbau bewähren muss.
LONG_INGREDIENTS = [
    "Wasser",
    "Dinkelvollkornmehl",
    "Weizenvollkornmehl",
    "Roggenvollkornmehl",
    "Dinkelmehl Type 630",
    "Grünkern fränkisch",
    "Hafer (ganz)",
    "Haferkleie",
    "Gluten rein",
    "Salz",
    "Dinkel (ganz)",
]

BREAD = Nutrients(
    energy_kcal=209,
    fat=1.6,
    saturated_fat=0.3,
    carbs=36.7,
    sugar=0.5,
    protein=9.6,
    salt=2.21,
    fiber=6.1,
    water=42.0,
)

# Einmal geladen: die Schriftsuche durchläuft sonst je Beispiel das Dateisystem.
FONTS = load_font_set()

#: Wörter aus westeuropäischer Schrift (Latin-1), Ziffern und Satzzeichen -
#: was auf einem Etikett stehen kann. Außen vor bleiben kombinierende Zeichen
#: und übereinander gestapelte Akzente wie in "Ȫ": Deren Tinte reicht über die
#: Oberlänge der Schrift hinaus und darf die Unterlänge der Zeile darüber
#: berühren - das ist bei jedem Zeilenabstand so. Bis zu 40 Zeichen je Wort,
#: damit auch Wörter vorkommen, die breiter als das Etikett sind.
_WORD = st.text(
    alphabet=st.characters(min_codepoint=0x21, max_codepoint=0xFF, categories=("L", "N", "P")),
    min_size=1,
    max_size=40,
)

#: Texte aus bis zu zwölf solchen Wörtern - lang genug, um umbrechen zu müssen.
_LABEL_TEXT = st.lists(_WORD, max_size=12).map(" ".join)


class TestLabelRendering:
    def test_default_label(self) -> None:
        image = render_label(BREAD, LabelOptions(net_weight_g=1500), fonts=FONTS)
        assert isinstance(image, Image.Image)
        assert image.mode == "RGB"

    @pytest.mark.parametrize("size", list(LabelSize))
    def test_every_size_renders(self, size: LabelSize) -> None:
        options = LabelOptions(size=size, dpi=150, net_weight_g=1000)
        image = render_label(BREAD, options, fonts=FONTS)
        assert image.size == options.pixel_size()

    @pytest.mark.parametrize("theme", list(LabelTheme))
    def test_every_theme_renders(self, theme: LabelTheme) -> None:
        image = render_label(BREAD, LabelOptions(theme=theme, dpi=150), fonts=FONTS)
        assert image.size[0] > 0

    def test_pixel_size_follows_the_resolution(self) -> None:
        low = LabelOptions(dpi=150).pixel_size()
        high = LabelOptions(dpi=300).pixel_size()
        assert high[0] == pytest.approx(low[0] * 2, abs=2)

    def test_a_long_ingredient_list_stays_inside(self) -> None:
        """Zwölf Zutaten dürfen nicht in die Fußzeile laufen."""
        options = LabelOptions(
            size=LabelSize.SMALL,
            dpi=150,
            net_weight_g=2964,
            ingredients=[f"Sehr langer Zutatenname Nummer {i}" for i in range(20)],
        )
        image = render_label(BREAD, options, fonts=FONTS)
        assert image.size == options.pixel_size()

    def test_no_ingredients_is_fine(self) -> None:
        render_label(BREAD, LabelOptions(show_ingredients=False, dpi=150), fonts=FONTS)

    def test_zero_nutrients_render(self) -> None:
        render_label(Nutrients(), LabelOptions(dpi=150), fonts=FONTS)

    def test_best_before_date(self) -> None:
        from datetime import date

        options = LabelOptions(dpi=150, best_before=date(2026, 12, 24))
        render_label(BREAD, options, fonts=FONTS)

    def test_everything_switched_off(self) -> None:
        options = LabelOptions(
            dpi=150,
            show_date=False,
            show_ingredients=False,
            show_fiber=False,
            show_reference_hint=False,
            footer="",
            net_weight_g=0,
        )
        render_label(BREAD, options, fonts=FONTS)

    @pytest.mark.parametrize("dpi", [10, 5000])
    def test_absurd_resolution_is_rejected(self, dpi: int) -> None:
        with pytest.raises(ValueError, match="Auflösung"):
            render_label(BREAD, LabelOptions(dpi=dpi), fonts=FONTS)

    def test_negative_weight_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="Nettogewicht"):
            render_label(BREAD, LabelOptions(net_weight_g=-1), fonts=FONTS)

    def test_weight_is_shown_in_kilograms_above_one_kilo(self) -> None:
        """Nur ein Rauchtest der Formatierung - geprüft wird das Rendern."""
        render_label(BREAD, LabelOptions(dpi=150, net_weight_g=2964), fonts=FONTS)
        render_label(BREAD, LabelOptions(dpi=150, net_weight_g=750), fonts=FONTS)

    def test_font_set_is_usable(self) -> None:
        assert FONTS.get(12) is not None

    @given(
        title=st.text(max_size=120),
        subtitle=st.text(max_size=80),
        footer=st.text(max_size=80),
    )
    def test_any_text_renders_without_crashing(
        self, title: str, subtitle: str, footer: str
    ) -> None:
        """Auch leere oder sehr lange Titel dürfen das Etikett nicht sprengen."""
        options = LabelOptions(
            title=title, subtitle=subtitle, footer=footer, dpi=110, net_weight_g=800
        )
        image = render_label(BREAD, options, fonts=FONTS)
        assert image.size == options.pixel_size()


class TestLabelLayout:
    """Der Aufbau wird gemessen, bevor gezeichnet wird.

    Früher standen feste Millimeterabstände im Code, abgestimmt auf ein
    einziges Format. Auf dem kleinen Aufkleber schoben sich die Blöcke dadurch
    übereinander, und Backdatum samt Mindesthaltbarkeit liefen als eine einzige
    Zeile über beide Ränder hinaus.
    """

    @staticmethod
    def _block_bounds(options: LabelOptions) -> tuple[int, int]:
        """Unterkante des festen Teils und Oberkante der Fußzeile.

        Beide werden mit denselben Funktionen ermittelt, die auch zeichnen -
        eine getrennte Nachrechnung könnte auseinanderlaufen.
        """
        from PIL import ImageDraw

        from brotrechner.export import label as module

        width, height = options.pixel_size()
        canvas = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(canvas)
        metrics = module._fitting_metrics(
            draw,
            BREAD,
            options,
            fonts=FONTS,
            pixels_per_mm=options.dpi / 25.4,
            width=width,
            height=height,
        )
        margin = metrics.mm(5.0)
        left = margin + metrics.mm(2.0)
        right = width - margin - metrics.mm(2.0)
        palette = options.theme.colors

        shared = {"palette": palette, "fonts": FONTS, "m": metrics, "left": left, "right": right}
        y = module._draw_head(draw, options, **shared, top=margin + metrics.mm(2.0))
        y = module._draw_nutrition(draw, BREAD, options, **shared, top=y)
        y = module._draw_net_weight(draw, options, **shared, top=y)
        footer_top = module._draw_footer(
            draw, options, **shared, bottom=height - margin - metrics.mm(2.0)
        )
        return y, footer_top

    @pytest.mark.parametrize("size", list(LabelSize))
    def test_content_never_reaches_into_the_footer(self, size: LabelSize) -> None:
        """Auf keinem Format darf sich der feste Teil mit der Fußzeile überlagern."""
        options = LabelOptions(
            title="Roggenmischbrot",
            size=size,
            dpi=150,
            net_weight_g=2964,
            ingredients=LONG_INGREDIENTS,
            best_before=date(2026, 8, 23),
            baked_on=date(2026, 8, 16),
        )
        content_bottom, footer_top = self._block_bounds(options)
        assert content_bottom <= footer_top, (
            f"{size.value}: Inhalt endet bei {content_bottom} px, Fuß beginnt bei {footer_top} px"
        )

    @pytest.mark.parametrize("size", list(LabelSize))
    def test_long_title_still_fits(self, size: LabelSize) -> None:
        options = LabelOptions(
            title="Dreikorn-Vollkornbrot mit Saaten und Sauerteig nach alter Art",
            subtitle="Handgeformt, 48 Stunden Führung",
            size=size,
            dpi=150,
            net_weight_g=2964,
            ingredients=LONG_INGREDIENTS,
            best_before=date(2026, 8, 23),
        )
        content_bottom, footer_top = self._block_bounds(options)
        assert content_bottom <= footer_top

    @pytest.mark.parametrize("size", list(LabelSize))
    def test_forty_ingredients_do_not_break_the_layout(self, size: LabelSize) -> None:
        options = LabelOptions(
            title="Vielkornbrot",
            size=size,
            dpi=150,
            net_weight_g=2964,
            ingredients=[f"Zutat Nummer {i}" for i in range(40)],
            best_before=date(2026, 8, 23),
        )
        content_bottom, footer_top = self._block_bounds(options)
        assert content_bottom <= footer_top

    def test_the_medium_label_keeps_the_whole_ingredient_list(self) -> None:
        """Das Zutatenverzeichnis ist vorgeschrieben und wiegt schwerer als Schriftgröße."""
        from PIL import ImageDraw

        from brotrechner.export import label as module

        options = LabelOptions(
            title="Roggenmischbrot",
            size=LabelSize.MEDIUM,
            dpi=150,
            net_weight_g=2964,
            ingredients=LONG_INGREDIENTS,
            best_before=date(2026, 8, 23),
        )
        width, height = options.pixel_size()
        draw = ImageDraw.Draw(Image.new("RGB", (width, height)))
        metrics = module._fitting_metrics(
            draw,
            BREAD,
            options,
            fonts=FONTS,
            pixels_per_mm=options.dpi / 25.4,
            width=width,
            height=height,
        )
        needed = module._required_height(
            draw, BREAD, options, fonts=FONTS, m=metrics, width=width, full_ingredients=True
        )
        assert needed <= height


@dataclass(frozen=True)
class _Drawn:
    """Ein gezeichneter Text.

    ``advance`` ist die Strecke, die der Text beim Setzen belegt, ``ink`` die
    Box seiner Tinte. Die Tinte darf minimal über die Strecke hinausragen - bei
    "À" oder "f" ist das so gewollt und kein Layoutfehler.
    """

    text: str
    baseline: tuple[float, str]
    advance: tuple[float, float]
    ink: tuple[float, float, float, float]


def _drawn_texts(options: LabelOptions) -> list[_Drawn]:
    """Rendert das Etikett und liefert jeden gezeichneten Text.

    Aufgezeichnet wird an ``ImageDraw.text`` selbst - dort kommt jeder Text
    vorbei, gleich über welches Zeichenobjekt. Geprüft wird damit, was
    tatsächlich auf dem Etikett landet, unabhängig von der Rechnung, mit der
    das Layout den Platz vorab verteilt.
    """
    texts: list[_Drawn] = []
    original = ImageDraw.ImageDraw.text

    def recording_text(
        self: ImageDraw.ImageDraw, xy: Any, text: Any, *args: Any, **kwargs: Any
    ) -> None:
        font = kwargs.get("font")
        anchor = kwargs.get("anchor") or "la"
        x, y = xy
        length = self.textlength(text, font=font)
        start = {"l": x, "m": x - length / 2, "r": x - length}[anchor[0]]
        ink = self.textbbox(xy, text, font=font, anchor=anchor)
        texts.append(_Drawn(str(text), (y, anchor[1]), (start, start + length), ink))
        original(self, xy, text, *args, **kwargs)

    with mock.patch.object(ImageDraw.ImageDraw, "text", recording_text):
        render_label(BREAD, options, fonts=FONTS)
    assert texts, "Nichts aufgezeichnet - die Prüfung liefe ins Leere"
    return texts


def _layout_problems(options: LabelOptions, *, check_overlaps: bool = True) -> list[str]:
    """Texte, die über den Innenrand ragen oder einander überdecken."""
    texts = _drawn_texts(options)
    pixels_per_mm = options.dpi / 25.4
    left = round(5.0 * pixels_per_mm) + round(2.0 * pixels_per_mm)
    right = options.pixel_size()[0] - left
    # Tinte darf bis 0,5 mm in den Innenrand reichen - der Rahmen liegt 2,5 mm weiter außen.
    ink_slack = 0.5 * pixels_per_mm
    problems = [
        f"{d.text!r} ragt über den Rand: {d.advance[0]:.0f}..{d.advance[1]:.0f} statt "
        f"{left}..{right}"
        for d in texts
        if d.advance[0] < left - 1
        or d.advance[1] > right + 1
        or d.ink[0] < left - ink_slack
        or d.ink[2] > right + ink_slack
    ]
    if check_overlaps:
        for a, b in itertools.combinations(texts, 2):
            if a.baseline == b.baseline:
                # Dieselbe Zeile: Die Strecken dürfen sich nicht überschneiden.
                overlap = min(a.advance[1], b.advance[1]) - max(a.advance[0], b.advance[0])
                if overlap > 1:
                    problems.append(f"{a.text!r} überdeckt {b.text!r}")
                continue
            # Verschiedene Zeilen: Die Tinte darf sich nicht berühren. Die
            # Schrift rundet jede Glyphenkante auf ganze Pixel - bei 72 dpi und
            # 8 Pixel Schrifthöhe sind das zusammen bis zu 2 Pixel.
            overlap_x = min(a.ink[2], b.ink[2]) - max(a.ink[0], b.ink[0])
            overlap_y = min(a.ink[3], b.ink[3]) - max(a.ink[1], b.ink[1])
            if overlap_x > 1 and overlap_y > 2:
                problems.append(f"{a.text!r} überdeckt {b.text!r}")
    return problems


class TestNothingOverlaps:
    """Kein Text ragt über den Rand, keiner überdeckt einen anderen.

    Auf dem kleinen Etikett lief "davon gesättigte Fettsäuren" in den eigenen
    Wert, "Brennwert" stieß an "996 kJ / 238 kcal", "Nettogewicht 2,96 kg"
    ragte über den Rand, und der Titel wurde mitten im Wort getrennt.
    """

    VARIANTS: ClassVar[dict[str, dict[str, object]]] = {
        "knapp": {
            "show_date": False,
            "show_ingredients": False,
            "show_reference_hint": False,
            "footer": "",
        },
        "voll": {
            "ingredients": LONG_INGREDIENTS,
            "baked_on": date(2026, 8, 16),
            "best_before": date(2026, 8, 23),
        },
        "viele Zutaten": {"ingredients": [f"Zutat Nummer {i}" for i in range(40)]},
        "langer Titel": {
            "title": "Dreikorn-Vollkornbrot mit Saaten und Sauerteig nach alter Art",
            "subtitle": "Handgeformt, 48 Stunden Führung",
            "footer": "Gebacken mit viel Zeit, Liebe und Mehl aus der Mühle nebenan",
        },
        # Passt auf dem kleinen Format nicht: Der Fuß rückt dann unter das
        # vollständige Verzeichnis, statt es zu überdecken.
        "Verkauf": {
            "for_sale": True,
            "producer": "Backstube Muster\nHauptstraße 1\n12345 Musterstadt",
            "storage_hint": "Trocken und bei Raumtemperatur lagern.",
            "ingredients": LONG_INGREDIENTS,
            "baked_on": date(2026, 8, 16),
            "best_before": date(2026, 8, 23),
        },
    }

    @pytest.mark.parametrize("dpi", [110, 300])
    @pytest.mark.parametrize("variant", list(VARIANTS))
    @pytest.mark.parametrize("size", list(LabelSize))
    def test_every_format(self, size: LabelSize, variant: str, dpi: int) -> None:
        values: dict[str, object] = {
            "title": "Roggenmischbrot",
            "size": size,
            "dpi": dpi,
            "net_weight_g": 2964,
        }
        values.update(self.VARIANTS[variant])
        options = LabelOptions(**values)  # type: ignore[arg-type]
        assert _layout_problems(options) == []

    def test_the_title_is_not_split_inside_a_word(self) -> None:
        options = LabelOptions(title="Roggenmischbrot", size=LabelSize.SMALL, dpi=200)
        assert "Roggenmischbrot" in [drawn.text for drawn in _drawn_texts(options)]

    @pytest.mark.parametrize("size", list(LabelSize))
    def test_value_and_label_share_a_baseline(self, size: LabelSize) -> None:
        """Mit dem Anker "rt" saß jeder Wert sichtbar höher als seine Beschriftung."""
        texts = _drawn_texts(LabelOptions(size=size, dpi=300))
        for label, value in (("Fett", "1,6 g"), ("Eiweiß", "9,6 g"), ("Salz", "2,2 g")):
            label_line = next(d for d in texts if d.text == label)
            value_line = next(d for d in texts if d.text == value)
            assert label_line.baseline == value_line.baseline, label

    @given(
        title=_LABEL_TEXT,
        subtitle=_LABEL_TEXT,
        footer=_LABEL_TEXT,
        producer=_LABEL_TEXT,
        size=st.sampled_from(list(LabelSize)),
        weight=st.floats(min_value=0.0, max_value=9999.0),
        for_sale=st.booleans(),
    )
    def test_no_text_leaves_the_label_or_covers_another(
        self,
        *,
        title: str,
        subtitle: str,
        footer: str,
        producer: str,
        size: LabelSize,
        weight: float,
        for_sale: bool,
    ) -> None:
        """Wie lang ein Text auch ist - er bricht um, statt über den Rand zu laufen.

        Und passt der Inhalt nicht, rückt der Fuß nach unten, statt ihn zu
        überdecken.
        """
        options = LabelOptions(
            title=title,
            subtitle=subtitle,
            footer=footer,
            size=size,
            dpi=110,
            net_weight_g=weight,
            ingredients=LONG_INGREDIENTS,
            for_sale=for_sale,
            producer=producer,
        )
        assert _layout_problems(options) == []


class TestDateLines:
    def test_both_dates_get_their_own_line(self) -> None:
        """Zusammen in einer Zeile liefen sie über beide Ränder hinaus."""
        lines = date_lines(LabelOptions(baked_on=date(2026, 8, 16), best_before=date(2026, 8, 23)))
        assert lines == ["gebacken am 16.08.2026", "mindestens haltbar bis 23.08.2026"]

    def test_only_the_baking_date(self) -> None:
        assert date_lines(LabelOptions(baked_on=date(2026, 8, 16))) == ["gebacken am 16.08.2026"]

    def test_only_the_best_before_date(self) -> None:
        lines = date_lines(LabelOptions(show_date=False, best_before=date(2026, 8, 23)))
        assert lines == ["mindestens haltbar bis 23.08.2026"]

    def test_no_dates_at_all(self) -> None:
        assert date_lines(LabelOptions(show_date=False)) == []


class TestIngredientCsv:
    def test_header_and_rows(self, tmp_path: Path, flour: Ingredient, water: Ingredient) -> None:
        target = tmp_path / "zutaten.csv"
        count = write_ingredients_csv(target, [flour, water])
        assert count == 2
        with target.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle, delimiter=";"))
        assert rows[0] == list(INGREDIENT_COLUMNS)
        assert len(rows) == 3

    def test_german_decimal_comma(self, tmp_path: Path, flour: Ingredient) -> None:
        target = tmp_path / "zutaten.csv"
        write_ingredients_csv(target, [flour])
        assert "1,7" in target.read_text(encoding="utf-8-sig")

    def test_byte_order_mark_for_excel(self, tmp_path: Path, flour: Ingredient) -> None:
        target = tmp_path / "zutaten.csv"
        write_ingredients_csv(target, [flour])
        assert target.read_bytes().startswith(b"\xef\xbb\xbf")

    def test_manufacturer_has_its_own_column(self, tmp_path: Path, flour: Ingredient) -> None:
        target = tmp_path / "zutaten.csv"
        write_ingredients_csv(target, [flour])
        with target.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle, delimiter=";"))
        assert rows[1][0] == "Roggenvollkornmehl"
        assert rows[1][1] == "Bauck"

    def test_sorted_output(self, tmp_path: Path, flour: Ingredient, water: Ingredient) -> None:
        target = tmp_path / "zutaten.csv"
        write_ingredients_csv(target, [water, flour])
        with target.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle, delimiter=";"))
        assert rows[1][0] == "Roggenvollkornmehl"

    def test_empty_database(self, tmp_path: Path) -> None:
        target = tmp_path / "leer.csv"
        assert write_ingredients_csv(target, []) == 0


class TestAnalysisCsv:
    def test_writes_the_lines_and_totals(
        self, tmp_path: Path, flour: Ingredient, water: Ingredient
    ) -> None:
        analysis = analyze(
            [ResolvedItem(flour, 1000.0), ResolvedItem(water, 700.0)], baked_weight_g=1500.0
        )
        target = tmp_path / "rezept.csv"
        assert write_analysis_csv(target, analysis, recipe_name="Testbrot") == 2
        text = target.read_text(encoding="utf-8-sig")
        assert "Rezept: Testbrot" in text
        assert "Teigausbeute" in text

    def test_without_a_recipe_name(self, tmp_path: Path, flour: Ingredient) -> None:
        analysis = analyze([ResolvedItem(flour, 100.0)], baked_weight_g=90.0)
        target = tmp_path / "rezept.csv"
        write_analysis_csv(target, analysis)
        assert not target.read_text(encoding="utf-8-sig").startswith("Rezept")


@pytest.mark.skipif(not report.is_available(), reason="reportlab nicht installiert")
class TestPdfReport:
    def test_creates_a_pdf(self, tmp_path: Path, flour: Ingredient, water: Ingredient) -> None:
        analysis = analyze(
            [ResolvedItem(flour, 1000.0), ResolvedItem(water, 700.0)],
            baked_weight_g=1500.0,
            energy_kwh=1.2,
        )
        target = tmp_path / "bericht.pdf"
        report.write_report(target, analysis, recipe_name="Testbrot", notes="Zwei Zeilen\nNotiz")
        assert target.read_bytes().startswith(b"%PDF")

    def test_empty_analysis_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(report.ReportError, match="keine Zutaten"):
            report.write_report(tmp_path / "x.pdf", analyze([], baked_weight_g=100))

    def test_missing_prices_are_mentioned(self, tmp_path: Path) -> None:
        free = Ingredient(name="Sauerteig")
        analysis = analyze([ResolvedItem(free, 100.0)], baked_weight_g=90.0)
        target = tmp_path / "bericht.pdf"
        report.write_report(target, analysis)
        assert target.exists()

    def test_unwritable_path_raises(self, tmp_path: Path, flour: Ingredient) -> None:
        analysis = analyze([ResolvedItem(flour, 100.0)], baked_weight_g=90.0)
        with pytest.raises(report.ReportError):
            report.write_report(tmp_path / "fehlt" / "x" / "y.pdf", analysis)
