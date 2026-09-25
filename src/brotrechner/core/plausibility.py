"""Plausibilitätsprüfung der Prozessdaten eines Rezepts.

Die Datenprüfung (:mod:`brotrechner.core.validation`) sieht sich einzelne
Zutaten an. Hier geht es um das, was beim Backen eingetragen wird: Einwaage,
Rohteig und das Gewicht des fertigen Brots. Ein Tippfehler dort verzerrt jede
Angabe je 100 g - aus 75 statt 750 g wurden bisher ohne Warnung 2273 kcal je
100 g, mehr als reines Fett haben kann.

==================  ========  ================================================
Code                Schwere   Bedeutung
==================  ========  ================================================
``baked_heavier``   Fehler    Das Brot ist schwerer als der Teig.
``below_dry_mass``  Fehler    Das Brot ist leichter als die Trockenmasse der
                              Zutaten - es wäre mehr Wasser verdunstet, als im
                              Teig war.
``energy_impossible``  Fehler  Mehr als 900 kcal je 100 g, also mehr als reines
                              Fett (9 kcal/g nach Anhang XIV).
``bake_loss``       Warnung   Backverlust außerhalb von 5 bis 35 %.
``dough_heavier``   Warnung   Gewogener Rohteig über 3 % schwerer als die
                              Einwaage.
``dough_loss``      Warnung   Gewogener Rohteig über 10 % leichter als die
                              Einwaage.
``portion_too_heavy``  Warnung  Eine Portion wiegt mehr als das ganze Brot.
==================  ========  ================================================

Fehler beschreiben Zustände, die physikalisch nicht vorkommen; mit ihnen darf
kein Etikett entstehen. Warnungen sind ungewöhnlich, aber möglich.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from brotrechner.core.analysis import RecipeAnalysis
from brotrechner.core.nutrients import ENERGY_FACTORS_KCAL_PER_G
from brotrechner.core.validation import Severity

__all__ = [
    "MAX_BAKE_LOSS_PERCENT",
    "MAX_ENERGY_KCAL_PER_100G",
    "MIN_BAKE_LOSS_PERCENT",
    "ProcessFinding",
    "check_process",
    "has_errors",
]

#: Backverlust, unterhalb dessen eine Warnung erscheint. Große Laibe verlieren
#: etwa 10 %, Brötchen 20 bis 25 %; unter 5 % wurde meist vor dem Auskühlen
#: gewogen oder das Gewicht vertauscht.
MIN_BAKE_LOSS_PERCENT: Final = 5.0

#: Backverlust, oberhalb dessen eine Warnung erscheint.
MAX_BAKE_LOSS_PERCENT: Final = 35.0

#: Reines Fett hat nach Anhang XIV der VO (EU) Nr. 1169/2011 9 kcal je Gramm,
#: 100 g also 900 kcal. Mehr kann kein Lebensmittel haben.
MAX_ENERGY_KCAL_PER_100G: Final = ENERGY_FACTORS_KCAL_PER_G["fat"] * 100.0

#: Rohteig darf leicht schwerer sein als die Einwaage (Streumehl, Waagen-
#: genauigkeit), aber nicht um mehr als diesen Anteil.
_DOUGH_GAIN_LIMIT: Final = 1.03

#: Mehr als dieser Anteil an Teigrest in der Schüssel ist unwahrscheinlich.
_DOUGH_REMAINDER_LIMIT: Final = 0.90

#: Rechentoleranz, damit genau auf einer Grenze liegende Werte nicht wegen
#: Gleitkommarundung gemeldet werden.
_EPSILON: Final = 1e-6


@dataclass(frozen=True, slots=True)
class ProcessFinding:
    """Ein Befund zu den Prozessdaten."""

    code: str
    severity: Severity
    message: str

    def __str__(self) -> str:
        return f"[{self.severity.label}] {self.message}"


def check_process(analysis: RecipeAnalysis) -> list[ProcessFinding]:
    """Prüft Einwaage, Rohteig und Backgewicht auf Plausibilität.

    Args:
        analysis: Auswertung eines Rezepts.

    Returns:
        Befunde, Fehler zuerst. Leer, solange nichts auffällt - auch dann, wenn
        noch kein Backgewicht eingetragen ist.
    """
    if analysis.is_empty:
        return []

    findings = _dough_findings(analysis)
    if analysis.baked_weight_g <= 0:
        return findings

    weight_errors = _baked_weight_errors(analysis)
    findings.extend(weight_errors)
    # Die zu hohen Nährwerte folgen dann aus dem Gewicht; eine Meldung genügt.
    if not weight_errors:
        findings.extend(_energy_findings(analysis))
        findings.extend(_bake_loss_findings(analysis))
    findings.extend(_portion_findings(analysis))

    findings.sort(key=lambda f: -f.severity.rank)
    return findings


def has_errors(findings: Iterable[ProcessFinding]) -> bool:
    """True, wenn mindestens ein Befund ein Fehler ist."""
    return any(f.severity is Severity.ERROR for f in findings)


def _dough_findings(analysis: RecipeAnalysis) -> list[ProcessFinding]:
    """Gewogener Rohteig gegen die Einwaage der Zutaten."""
    weighed = analysis.weighed_mass_g
    dough = analysis.dough_weight_g
    if weighed <= 0:
        return []
    if dough > weighed * _DOUGH_GAIN_LIMIT + _EPSILON:
        return [
            ProcessFinding(
                "dough_heavier",
                Severity.WARNING,
                f"Der Rohteig ({dough:.0f} g) ist schwerer als alle Zutaten zusammen "
                f"({weighed:.0f} g). Alle Mengen werden entsprechend hochgerechnet - "
                f"stimmt das Rohteiggewicht?",
            )
        ]
    if dough < weighed * _DOUGH_REMAINDER_LIMIT - _EPSILON:
        return [
            ProcessFinding(
                "dough_loss",
                Severity.WARNING,
                f"Der Rohteig ({dough:.0f} g) wiegt {100 - dough / weighed * 100:.0f} % weniger "
                f"als die Zutaten ({weighed:.0f} g). So viel Teig bleibt selten in der "
                f"Schüssel - stimmt das Rohteiggewicht?",
            )
        ]
    return []


def _baked_weight_errors(analysis: RecipeAnalysis) -> list[ProcessFinding]:
    """Gewicht des Brots, das es physikalisch nicht geben kann."""
    baked = analysis.baked_weight_g
    dough = analysis.dough_weight_g
    if baked > dough + _EPSILON:
        return [
            ProcessFinding(
                "baked_heavier",
                Severity.ERROR,
                f"Das Brot ({baked:.0f} g) ist schwerer als sein Teig ({dough:.0f} g). "
                f"Beim Backen verdunstet Wasser, das Brot wird leichter - Tippfehler?",
            )
        ]
    dry_mass = dough - analysis.total.water
    if baked < dry_mass - _EPSILON:
        return [
            ProcessFinding(
                "below_dry_mass",
                Severity.ERROR,
                f"Das Brot ({baked:.0f} g) wiegt weniger als die Trockenmasse der Zutaten "
                f"({dry_mass:.0f} g). So viel Wasser kann beim Backen nicht verdunsten - "
                f"Tippfehler?",
            )
        ]
    return []


def _energy_findings(analysis: RecipeAnalysis) -> list[ProcessFinding]:
    """Brennwert, den kein Lebensmittel haben kann."""
    energy = analysis.per_100g.energy_kcal
    if energy > MAX_ENERGY_KCAL_PER_100G + _EPSILON:
        return [
            ProcessFinding(
                "energy_impossible",
                Severity.ERROR,
                f"{energy:.0f} kcal je 100 g sind mehr als reines Fett "
                f"({MAX_ENERGY_KCAL_PER_100G:.0f} kcal). Ein Zutatenwert stimmt nicht - "
                f"siehe Datenprüfung.",
            )
        ]
    return []


def _bake_loss_findings(analysis: RecipeAnalysis) -> list[ProcessFinding]:
    """Backverlust außerhalb des Üblichen."""
    loss = analysis.water_loss_percent
    if MIN_BAKE_LOSS_PERCENT - _EPSILON <= loss <= MAX_BAKE_LOSS_PERCENT + _EPSILON:
        return []
    return [
        ProcessFinding(
            "bake_loss",
            Severity.WARNING,
            f"Backverlust {loss:.1f} % ist ungewöhnlich; üblich sind etwa 10 bis 25 %. "
            f"Stimmen Rohteig- und Brotgewicht?",
        )
    ]


def _portion_findings(analysis: RecipeAnalysis) -> list[ProcessFinding]:
    """Eine Portion, die schwerer ist als das Brot, aus dem sie stammt."""
    portion = analysis.portion
    if portion is None or portion.fits_into(analysis.baked_weight_g):
        return []
    return [
        ProcessFinding(
            "portion_too_heavy",
            Severity.WARNING,
            f"Die Portion „{portion.title}“ wiegt mehr als das ganze Brot "
            f"({analysis.baked_weight_g:.0f} g). Stimmt das Portionsgewicht?",
        )
    ]
