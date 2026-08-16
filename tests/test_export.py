"""Tests der Ausgabeformate: Etikett, CSV und PDF-Bericht."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from PIL import Image

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
