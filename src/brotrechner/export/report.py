"""PDF-Bericht zu einem ausgewerteten Rezept.

Anders als das Etikett enthält der Bericht **alle** Angaben inklusive Preisen -
er ist für die eigene Kalkulation gedacht, nicht zum Verschenken.

``reportlab`` ist eine optionale Abhängigkeit. Fehlt sie, meldet
:func:`is_available` das, und die Oberfläche schaltet den Knopf ab, statt beim
Klick mit einem Importfehler abzustürzen.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from brotrechner import __version__
from brotrechner.core.analysis import RecipeAnalysis
from brotrechner.core.nutrients import KCAL_TO_KJ
from brotrechner.core.reference import reference_intake_percent, traffic_light
from brotrechner.i18n import NUTRIENT_LABELS, format_number

__all__ = ["ReportError", "is_available", "write_report"]

try:  # pragma: no cover - abhängig von der Installation
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        HRFlowable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    _HAS_REPORTLAB = True
except ImportError:  # pragma: no cover
    _HAS_REPORTLAB = False


class ReportError(RuntimeError):
    """Der PDF-Bericht konnte nicht erzeugt werden."""


def is_available() -> bool:
    """True, wenn ``reportlab`` installiert ist."""
    return _HAS_REPORTLAB


_ACCENT = "#2F6B3A"
_SECONDARY = "#1B5E86"
_DANGER = "#B3261E"


def write_report(
    path: Path,
    analysis: RecipeAnalysis,
    *,
    recipe_name: str = "Unbenanntes Rezept",
    notes: str = "",
) -> Path:
    """Schreibt den Bericht als PDF.

    Args:
        path: Zieldatei.
        analysis: Auswertung des Rezepts.
        recipe_name: Überschrift des Berichts.
        notes: Freitext, der als eigener Abschnitt erscheint.

    Returns:
        Der geschriebene Pfad.

    Raises:
        ReportError: Wenn ``reportlab`` fehlt oder das Schreiben scheitert.
    """
    if not _HAS_REPORTLAB:
        raise ReportError(
            "Für den PDF-Bericht wird reportlab benötigt. Installation: pip install reportlab"
        )
    if analysis.is_empty:
        raise ReportError("Das Rezept enthält keine Zutaten.")

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "BrTitle",
        parent=styles["Heading1"],
        alignment=TA_CENTER,
        fontSize=20,
        spaceAfter=6,
        textColor=colors.HexColor(_ACCENT),
    )
    h2 = ParagraphStyle(
        "BrH2",
        parent=styles["Heading2"],
        fontSize=13,
        spaceBefore=16,
        spaceAfter=8,
        textColor=colors.HexColor(_SECONDARY),
    )
    small = ParagraphStyle("BrSmall", parent=styles["Normal"], fontSize=7.5, textColor=colors.grey)
    centred = ParagraphStyle("BrCentred", parent=styles["Normal"], alignment=TA_CENTER)

    story: list[Any] = [
        Paragraph(recipe_name, title_style),
        Paragraph(
            f"Erstellt am {datetime.now().strftime('%d.%m.%Y um %H:%M')} "
            f"&middot; Brotrechner {__version__}",
            centred,
        ),
        Spacer(1, 8),
        HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#CCCCCC")),
        Paragraph("Eckdaten", h2),
        _facts_table(analysis),
        Paragraph("Nährwerte je 100 g gebackenes Brot", h2),
        _nutrition_table(analysis),
        Paragraph(
            "% RM = Anteil an der Referenzmenge für einen durchschnittlichen Erwachsenen "
            "(8400 kJ / 2000 kcal, Anhang XIII VO (EU) Nr. 1169/2011). "
            "Ballaststoffe haben keine EU-Referenzmenge; verglichen wird mit dem "
            "DGE-Richtwert von 30 g je Tag. "
            "Die Bandbreite folgt den Deklarationstoleranzen der EU-Guidance von 2012.",
            small,
        ),
        Paragraph("Zutaten, Bäckerprozent und Kosten", h2),
        _ingredients_table(analysis),
        Spacer(1, 10),
        _cost_summary(analysis),
    ]

    if analysis.lines_without_price:
        missing = ", ".join(line.ingredient.display_name for line in analysis.lines_without_price)
        story.append(Spacer(1, 6))
        story.append(
            Paragraph(
                f"<b>Hinweis:</b> Für folgende Zutaten ist kein Preis hinterlegt, "
                f"die Kostenrechnung ist daher unvollständig: {missing}.",
                small,
            )
        )

    if notes:
        story.append(Paragraph("Notizen", h2))
        story.append(Paragraph(notes.replace("\n", "<br/>"), styles["Normal"]))

    try:
        document = SimpleDocTemplate(
            str(path),
            pagesize=A4,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            topMargin=1.8 * cm,
            bottomMargin=1.8 * cm,
            title=f"Brotrechner - {recipe_name}",
            author="Brotrechner",
        )
        document.build(story)
    except OSError as exc:
        raise ReportError(f"{path} konnte nicht geschrieben werden: {exc}") from exc
    return path


def _facts_table(analysis: RecipeAnalysis) -> Any:
    """Zweispaltige Tabelle mit den Prozesskennzahlen."""
    rows = [
        [
            "Einwaage Zutaten",
            f"{analysis.weighed_mass_g:.0f} g",
            "Mehlmenge",
            f"{analysis.flour_mass_g:.0f} g",
        ],
        [
            "Rohteig",
            f"{analysis.dough_weight_g:.0f} g",
            "Schüttwasser",
            f"{analysis.water_mass_g:.0f} g",
        ],
        [
            "Gebacken",
            f"{analysis.baked_weight_g:.0f} g",
            "Teigausbeute",
            f"{analysis.dough_yield:.0f}" if analysis.dough_yield else "-",
        ],
        [
            "Backverlust",
            f"{analysis.water_loss_percent:.1f} %",
            "Hydration",
            f"{analysis.hydration_percent:.0f} %" if analysis.dough_yield else "-",
        ],
    ]
    table = Table(rows, colWidths=[3.6 * cm, 3.0 * cm, 3.6 * cm, 3.0 * cm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
                ("TEXTCOLOR", (2, 0), (2, -1), colors.grey),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("ALIGN", (3, 0), (3, -1), "RIGHT"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _nutrition_table(analysis: RecipeAnalysis) -> Any:
    """Nährwerttabelle mit Bandbreite, Referenzmenge und Ampel."""
    nutrients = analysis.per_100g
    header = ["Nährstoff", "je 100 g", "Bandbreite", "% RM", "Ampel"]
    rows: list[list[str]] = [header]

    order = [
        "energy_kcal",
        "fat",
        "saturated_fat",
        "carbs",
        "sugar",
        "fiber",
        "protein",
        "salt",
    ]
    for name in order:
        value = getattr(nutrients, name)
        value_range = analysis.ranges_per_100g.get(name)
        if name == "energy_kcal":
            shown = f"{value * KCAL_TO_KJ:.0f} kJ / {value:.0f} kcal"
            band = (
                f"{value_range.minimum:.0f} - {value_range.maximum:.0f} kcal"
                if value_range
                else "-"
            )
        else:
            decimals = 2 if name == "salt" else 1
            shown = f"{format_number(value, decimals)} g"
            band = (
                f"{format_number(value_range.minimum, decimals)} - "
                f"{format_number(value_range.maximum, decimals)} g"
                if value_range
                else "-"
            )
        percent = reference_intake_percent(name, value)
        light = traffic_light(name, value)
        rows.append(
            [
                NUTRIENT_LABELS[name],
                shown,
                band,
                f"{percent:.0f} %" if percent is not None else "-",
                light.label,
            ]
        )

    table = Table(rows, colWidths=[5.0 * cm, 3.6 * cm, 3.6 * cm, 1.8 * cm, 2.0 * cm], hAlign="LEFT")
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF2EC")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#DDDDDD")),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    # Untergeordnete Zeilen ("davon ...") optisch zurücknehmen.
    for index, name in enumerate(order, start=1):
        if name in ("saturated_fat", "sugar"):
            style.append(("TEXTCOLOR", (0, index), (-1, index), colors.grey))
    table.setStyle(TableStyle(style))
    return table


def _ingredients_table(analysis: RecipeAnalysis) -> Any:
    """Zutatentabelle mit Hersteller, Anteil, Bäckerprozent und Kosten."""
    rows: list[list[str]] = [
        ["Zutat", "Hersteller", "Menge", "Anteil", "Bäcker%", "€/100 g", "Kosten"]
    ]
    for line in analysis.lines:
        ingredient = line.ingredient
        rows.append(
            [
                ingredient.name,
                ingredient.manufacturer or "-",
                f"{line.amount_g:.0f} g",
                f"{line.share_percent:.1f} %",
                f"{line.baker_percent:.0f} %" if analysis.flour_mass_g else "-",
                format_number(ingredient.price_per_100g, 3) if ingredient.has_price else "-",
                f"{line.cost:.2f} €" if ingredient.has_price else "-",
            ]
        )

    table = Table(
        rows,
        colWidths=[4.6 * cm, 2.6 * cm, 1.8 * cm, 1.6 * cm, 1.6 * cm, 1.8 * cm, 2.0 * cm],
        hAlign="LEFT",
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF2EC")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#DDDDDD")),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 3.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ]
        )
    )
    return table


def _cost_summary(analysis: RecipeAnalysis) -> Any:
    """Kostenzusammenfassung rechtsbündig."""
    rows = [
        ["Materialkosten", f"{analysis.material_cost:.2f} €"],
        [
            f"Energie ({format_number(analysis.energy_kwh, 2)} kWh × "
            f"{format_number(analysis.energy_price, 2)} €/kWh)",
            f"{analysis.energy_cost:.2f} €",
        ],
        ["Gesamtkosten", f"{analysis.total_cost:.2f} €"],
        ["", ""],
        ["Preis je 100 g", f"{analysis.cost_per_100g:.2f} €"],
        ["Preis je Kilogramm", f"{analysis.cost_per_kg:.2f} €"],
    ]
    table = Table(rows, colWidths=[8.0 * cm, 3.4 * cm], hAlign="RIGHT")
    table.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("LINEABOVE", (0, 2), (-1, 2), 0.8, colors.black),
                ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
                ("FONTNAME", (0, 4), (-1, -1), "Helvetica-Bold"),
                ("TEXTCOLOR", (0, 4), (-1, -1), colors.HexColor(_DANGER)),
            ]
        )
    )
    return table
