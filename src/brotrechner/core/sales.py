"""Pflichtangaben eines Etiketts für verpackt verkauftes Brot.

Artikel 9 Abs. 1 VO (EU) Nr. 1169/2011 zählt auf, was auf einem vorverpackten
Lebensmittel stehen muss. Für Brot sind das:

======  ==============================================  ===========================
Art. 9  Angabe                                          auf dem Etikett
======  ==============================================  ===========================
a       Bezeichnung des Lebensmittels                   Titel
b       Zutatenverzeichnis                              "Zutaten"
c       Allergene, hervorgehoben (Art. 21)              fett im Verzeichnis
e       Nettofüllmenge                                  "Nettogewicht"
f       Mindesthaltbarkeitsdatum                        "mindestens haltbar bis"
h       Name und Anschrift des Lebensmittelunternehmers eigene Zeile
l       Nährwertdeklaration                             Tabelle
======  ==============================================  ===========================

Die Nährwertdeklaration ist nach Anhang V Nr. 19 für handwerklich
hergestellte Lebensmittel, die in kleinen Mengen direkt an Verbraucher oder
den örtlichen Einzelhandel abgegeben werden, freiwillig - hier wird sie
deshalb nicht verlangt. Wird sie gedruckt, gelten Rundung und Mindestschrift.

Diese Prüfung betrifft die *Inhalte*. Ob alles in ausreichender Schriftgröße
auf das gewählte Format passt, prüft das Etikett selbst
(:func:`brotrechner.export.label.measure_label`). Eine Rechtsberatung ersetzt
beides nicht; die Verantwortung für die Kennzeichnung trägt, wer verkauft.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from brotrechner.core.labeling import IngredientList

__all__ = ["SaleIssue", "check_sale"]


@dataclass(frozen=True, slots=True)
class SaleIssue:
    """Eine fehlende oder unzulässige Pflichtangabe."""

    code: str
    message: str


def check_sale(
    *,
    title: str,
    producer: str,
    baked_on: date | None,
    best_before: date | None,
    show_ingredients: bool,
    listing: IngredientList,
    net_weight_g: float,
) -> list[SaleIssue]:
    """Prüft die Inhalte eines Verkaufsetiketts auf Vollständigkeit.

    Args:
        title: Bezeichnung des Lebensmittels.
        producer: Name und Anschrift des Lebensmittelunternehmers.
        baked_on: Backtag, sofern angegeben.
        best_before: Mindesthaltbarkeitsdatum, sofern angegeben.
        show_ingredients: Wird das Zutatenverzeichnis gedruckt?
        listing: Das Zutatenverzeichnis des Rezepts.
        net_weight_g: Nettofüllmenge in Gramm.

    Returns:
        Fehlende oder widersprüchliche Angaben; leer, wenn alles da ist.
    """
    issues: list[SaleIssue] = []
    if not title.strip():
        issues.append(SaleIssue("title_missing", "Bezeichnung des Lebensmittels fehlt (Art. 9 a)"))
    if not producer.strip():
        issues.append(
            SaleIssue(
                "producer_missing",
                "Name und Anschrift des Lebensmittelunternehmers fehlen (Art. 9 h)",
            )
        )
    if best_before is None:
        issues.append(SaleIssue("best_before_missing", "Mindesthaltbarkeitsdatum fehlt (Art. 9 f)"))
    elif baked_on is not None and best_before < baked_on:
        issues.append(
            SaleIssue(
                "best_before_before_baking",
                "Das Mindesthaltbarkeitsdatum liegt vor dem Backtag (Art. 9 f)",
            )
        )
    if not show_ingredients or not listing.entries:
        issues.append(
            SaleIssue(
                "ingredients_hidden",
                "Das Zutatenverzeichnis ist für den Verkauf vorgeschrieben (Art. 9 b)",
            )
        )
    if listing.unknown:
        names = ", ".join(listing.unknown)
        issues.append(
            SaleIssue(
                "allergens_unknown",
                f"Allergene nicht erfasst: {names} - Packung prüfen und in der "
                f"Zutatenverwaltung eintragen (Art. 21, Anhang II)",
            )
        )
    if net_weight_g <= 0:
        issues.append(SaleIssue("net_weight_missing", "Nettofüllmenge fehlt (Art. 9 e)"))
    return issues
