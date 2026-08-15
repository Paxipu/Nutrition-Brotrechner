#!/usr/bin/env python3
"""Erzeugt ``docs/DATENKORREKTUREN.md`` aus dem Vergleich alt gegen neu.

Der Bericht wird nicht von Hand gepflegt, sondern aus den beiden Datenständen
berechnet. So kann er nicht auseinanderlaufen, und jede Zahl darin ist
nachprüfbar.

Aufruf::

    python tools/report_data_changes.py path/zu/brot_zutaten.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brotrechner.core.models import Ingredient
from brotrechner.core.nutrients import NUTRIENT_FIELDS
from brotrechner.core.validation import Severity, validate_database
from brotrechner.data.migration import migrate_ingredients
from brotrechner.i18n import NUTRIENT_LABELS, format_number

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "src/brotrechner/data/seed/ingredients.json"
OUTPUT = ROOT / "docs/DATENKORREKTUREN.md"

#: Unterhalb dieser Differenz gilt ein Wert als unverändert (Rundung).
EPSILON = 0.049

HEADER = """# Datenkorrekturen

Dieser Bericht wird von `tools/report_data_changes.py` erzeugt und vergleicht
die Zutatendatenbank der Vorgängerversion mit der geprüften Fassung, die
`tools/build_seed_database.py` erstellt.

## Wie geprüft wurde

Die Prüfung stützt sich ausschließlich auf nachrechenbare Kriterien, nicht auf
Einschätzung:

**Massenbilanz.** Fett + Kohlenhydrate + Eiweiß + Ballaststoffe + Salz + Wasser
kann je 100 g Lebensmittel nicht über 100 g liegen. Der Rest zu 100 g sind
Asche, organische Säuren und Messungenauigkeit.

**Brennwert.** Anhang XIV der VO (EU) Nr. 1169/2011 gibt die Umrechnung fest
vor: Kohlenhydrate 4, Eiweiß 4, Fett 9 und **Ballaststoffe 2 kcal/g**. Weicht
der angegebene Brennwert deutlich vom gerechneten ab, stimmt einer der Werte
nicht.

**Kohlenhydrat-Konvention.** In der EU werden Kohlenhydrate **ohne**
Ballaststoffe deklariert, in den USA einschließlich. Werden US-Werte
unverändert übernommen, zählt der Ballaststoffanteil doppelt – das war die
Ursache mehrerer Bilanzfehler.

**Wassergehalt.** Er steht auf keinem Etikett und wurde durchweg aus der
Handelsüblichkeit und der Massenbilanz abgeleitet.

"""

FOOTER = """
## Was beim Übernehmen der Altdaten tatsächlich passiert

Beim ersten Start greifen drei Regeln, damit selbst gepflegte Werte nicht
verloren gehen:

1. Zutaten **ohne Preis, ohne Notiz und ohne Preishistorie** gelten als
   unberührte Vorgabewerte der Altversion und werden vollständig durch die
   geprüfte Fassung ersetzt.
2. Selbst gepflegte Zutaten **behalten ihre Nährwerte**. Nur wenn sie die
   Plausibilitätsprüfung nicht bestehen und der Referenzeintrag sauber ist,
   werden sie korrigiert.
3. **Preise** werden ausschließlich dort eingetragen, wo bisher keiner stand.

Die Originaldateien der Vorgängerversion bleiben unverändert liegen,
zusätzlich legt das Programm vor jedem Schreiben eine Sicherung an.

## Preise

Die Preise stammen aus zwei Quellen, die je Zutat im Feld *Preisquelle*
ausgewiesen sind:

- **recherchiert** – im Onlineauftritt des jeweiligen Händlers nachgeschlagen,
  mit Angabe von Händler und Packungsgröße.
- **Schätzung Discounter-Niveau** – üblicher deutscher Discounterpreis für die
  jeweilige Warengruppe. Diese Werte sind ausdrücklich als Schätzung
  gekennzeichnet und im Programm jederzeit überschreibbar.

Für Zutaten, die man selbst herstellt (Anstellgut, Lievito Madre), ist der
Preis aus den Kosten von Mehl und Wasser berechnet.
"""


def main() -> int:
    """Erzeugt den Bericht."""
    if len(sys.argv) < 2:
        print(f"Aufruf: {sys.argv[0]} path/zu/brot_zutaten.json", file=sys.stderr)
        return 2

    legacy_path = Path(sys.argv[1])
    if not legacy_path.exists():
        print(f"Nicht gefunden: {legacy_path}", file=sys.stderr)
        return 2

    old, merge_notes = migrate_ingredients(json.loads(legacy_path.read_text(encoding="utf-8")))
    new = [
        Ingredient.from_dict(entry)
        for entry in json.loads(SEED.read_text(encoding="utf-8"))["ingredients"]
    ]
    old_by_key = {item.key: item for item in old}

    old_findings = validate_database(old)
    new_findings = validate_database(new)

    lines = [HEADER]
    lines.append("## Befunde vorher und nachher\n")
    lines.append("| | Vorgängerversion | geprüfte Fassung |")
    lines.append("|---|---:|---:|")
    for severity, label in (
        (Severity.ERROR, "Fehler (Bilanz verletzt)"),
        (Severity.WARNING, "Warnungen"),
        (Severity.INFO, "Hinweise (fehlender Preis)"),
    ):
        before = sum(1 for f in old_findings if f.severity is severity)
        after = sum(1 for f in new_findings if f.severity is severity)
        lines.append(f"| {label} | {before} | {after} |")
    lines.append(f"| Zutaten insgesamt | {len(old)} | {len(new)} |")
    priced_before = sum(1 for i in old if i.has_price)
    priced_after = sum(1 for i in new if i.has_price)
    lines.append(f"| davon mit Preis | {priced_before} | {priced_after} |")
    lines.append("")

    if merge_notes:
        lines.append("## Zusammengeführte Einträge\n")
        for note in merge_notes:
            lines.append(f"- {note}")
        lines.append("")

    changed: list[tuple[str, list[str], str]] = []
    for item in sorted(new, key=lambda i: i.display_name.casefold()):
        previous = old_by_key.get(item.key)
        if previous is None:
            continue
        diffs = []
        for field in NUTRIENT_FIELDS:
            before_value = getattr(previous.nutrients, field)
            after_value = getattr(item.nutrients, field)
            if abs(before_value - after_value) > EPSILON:
                diffs.append(
                    f"{NUTRIENT_LABELS[field]} {format_number(before_value, 1)} → "
                    f"{format_number(after_value, 1)}"
                )
        if diffs:
            changed.append((item.display_name, diffs, item.notes))

    lines.append(f"## Geänderte Nährwerte ({len(changed)} von {len(new)} Zutaten)\n")
    lines.append("| Zutat | Änderung | Begründung |")
    lines.append("|---|---|---|")
    for name, diffs, note in changed:
        reason = note.split("Nährwertquelle:")[0].strip() or "an die Referenzwerte angeglichen"
        lines.append(f"| {name} | {'; '.join(diffs)} | {reason} |")
    lines.append("")

    flag_changes = [
        item.display_name
        for item in new
        if (previous := old_by_key.get(item.key)) is not None and previous.is_flour != item.is_flour
    ]
    if flag_changes:
        lines.append("## Geänderte Mehl-Zuordnung\n")
        for name in sorted(flag_changes):
            lines.append(f"- **{name}** zählt nicht mehr zur Mehlmenge.")
        lines.append("")

    lines.append(FOOTER)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{OUTPUT} geschrieben ({len(changed)} geänderte Zutaten)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
