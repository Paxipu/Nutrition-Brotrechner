"""Bezeichnungen im Zutatenverzeichnis und ihre Hervorhebung.

Allergene müssen im Zutatenverzeichnis so hervorgehoben sein, dass sie sich
vom übrigen Text abheben (Artikel 21 VO (EU) Nr. 1169/2011) - auf dem Etikett
durch Fettdruck. Welcher Teil einer Bezeichnung das Allergen ist, steht in
``*Sternchen*``: ``*Weizen*mehl Type 550`` oder, bei einer zusammengesetzten
Zutat, ``Roggensauerteig (*Roggen*vollkornmehl, Wasser)``.

Ein einzelnes, nicht geschlossenes Sternchen bleibt als Zeichen stehen; die
Datenprüfung meldet es als Fehler.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass

__all__ = [
    "Run",
    "has_emphasis",
    "has_unmatched_mark",
    "list_runs",
    "parse_emphasis",
    "plain_text",
]

_MARK = "*"


@dataclass(frozen=True, slots=True)
class Run:
    """Ein Textstück in einheitlicher Auszeichnung."""

    text: str
    bold: bool = False


def parse_emphasis(text: str) -> tuple[Run, ...]:
    """Zerlegt eine Bezeichnung in normale und hervorgehobene Stücke.

    Args:
        text: Bezeichnung mit ``*Hervorhebung*``.

    Returns:
        Nicht leere Stücke; benachbarte gleicher Auszeichnung zusammengefasst.
    """
    parts = text.split(_MARK)
    if len(parts) % 2 == 0:
        # Ungerade Zahl von Sternchen: Das letzte bleibt als Zeichen stehen.
        parts[-2:] = [parts[-2] + _MARK + parts[-1]]

    runs: list[Run] = []
    for index, part in enumerate(parts):
        if not part:
            continue
        bold = index % 2 == 1
        if runs and runs[-1].bold == bold:
            runs[-1] = Run(runs[-1].text + part, bold)
        else:
            runs.append(Run(part, bold))
    return tuple(runs)


def plain_text(text: str) -> str:
    """Bezeichnung ohne Markierung, etwa für Listen und die CSV-Ausgabe."""
    return "".join(run.text for run in parse_emphasis(text))


def has_emphasis(text: str) -> bool:
    """True, wenn mindestens ein Teil hervorgehoben ist."""
    return any(run.bold for run in parse_emphasis(text))


def has_unmatched_mark(text: str) -> bool:
    """True bei einer ungeraden Zahl von Sternchen."""
    return text.count(_MARK) % 2 == 1


def list_runs(label: str, allergens: Collection[object] | None) -> tuple[Run, ...]:
    """Die Bezeichnung einer Zutat, wie sie im Zutatenverzeichnis steht.

    Enthält die Zutat Allergene, ohne dass etwas hervorgehoben ist, wird die
    ganze Bezeichnung fett gesetzt - das Allergen darf im Verzeichnis nicht
    unauffällig bleiben. Die Datenprüfung meldet diesen Fall, damit er bewusst
    so gewollt ist.

    Args:
        label: Bezeichnung mit ``*Hervorhebung*``.
        allergens: Enthaltene Allergene; ``None`` oder leer heißt: nichts
            zusätzlich hervorheben.
    """
    runs = parse_emphasis(label)
    if allergens and runs and not any(run.bold for run in runs):
        return (Run(plain_text(label), bold=True),)
    return runs
