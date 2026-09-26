# Mitwirken

Danke fürs Interesse. Ein paar Punkte, die das Zusammenarbeiten erleichtern.

## Vor dem ersten Beitrag

```bash
python -m venv .venv
source .venv/bin/activate        # Windows:  .venv\Scripts\activate
pip install -e ".[dev]"
```

## Vor jedem Pull Request

Ein Durchgang, derselbe, den die CI ausführt:

```bash
python tools/quality_gate.py
```

Das prüft in dieser Reihenfolge: `ruff check`, `ruff format --check`,
`mypy` im Strict-Modus, den Testlauf und die Testabdeckung (mindestens 90 %,
die Oberfläche eingeschlossen). Ein roter Durchgang wird nicht zusammengeführt.

**Oberflächentests** tragen die Markierung `gui` und laufen ohne Bildschirm
(`QT_QPA_PLATFORM=offscreen`). Jeder Dialog, den ein Test auslöst, muss dort
beantwortet werden – die Fixture `dialogs` erledigt das für die üblichen
Rückfragen. Bleibt ein modaler Dialog offen, schließt ihn ein Wächter nach
anderthalb Sekunden, und der Test scheitert mit dem Titel des Dialogs, statt
den ganzen Lauf anzuhalten.

## Grundsätze

**Fachlogik gehört nach `core`.** Dort gibt es weder Qt noch Dateizugriff.
Wenn eine Rechnung nur über die Oberfläche prüfbar wäre, sitzt sie an der
falschen Stelle.

**Die Schichten importieren nach unten.** `gui` → `export`/`data` → `core`,
nie umgekehrt.

**Zahlen bekommen eine Quelle.** Nährwerte, Referenzmengen und Toleranzen
tragen im Code eine Fundstelle – Verordnung mit Anhang, Tabellenwerk oder
Etikett. Ein Wert ohne Herkunft ist eine Behauptung.

**Die Zutatendatenbank wird erzeugt, nicht bearbeitet.**
`src/brotrechner/data/seed/ingredients.json` ist die Ausgabe von
`tools/build_seed_database.py`. Änderungen gehören in den Generator; danach
einmal laufen lassen und beides zusammen einchecken.

**Tests sind Teil der Änderung.** Neue Fachlogik braucht Tests für den
Normalfall, die Ränder und den Fehlerfall. Bei einem Fehler zuerst den Test
schreiben, der ihn zeigt, dann die Ursache beheben.

## Commit-Nachrichten

Konventionelles Format, deutscher oder englischer Text – Hauptsache, der Grund
ist erkennbar:

```
fix: Zutatenverzeichnis läuft nicht mehr in die Etikett-Fußzeile
feat: Hersteller als eigenes Feld
refactor: Auswertung aus der Oberfläche nach core verschoben
```

Umbauten ohne Verhaltensänderung und echte Änderungen bitte in getrennte
Commits: Ein Refactoring erkennt man daran, dass die Tests unverändert
weiterlaufen.
