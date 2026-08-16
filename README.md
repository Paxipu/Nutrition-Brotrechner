# Nutrition-Brotrechner

Nährwerte, Kosten, Bäckerprozent und Teigausbeute für selbstgebackenes Brot –
mit druckfertigem Etikett nach EU-Kennzeichnungsrecht.

Läuft unter **Linux, Windows und macOS**.

> **Vollständig KI-generiert.** Der gesamte Quelltext dieses Projekts wurde von
> Claude (Anthropic) erzeugt. Kein Teil ist von Hand geschrieben. Die fachlichen
> Vorgaben, die Entscheidungen über Aufbau und Funktionsumfang sowie die Abnahme
> stammen von **Martin Kraus**.

![Rechner](docs/bilder/rechner.png)

## Was das Programm kann

**Rechnen.** Zutaten zusammenstellen, Gewicht des fertigen Brots eintragen –
Nährwerte je 100 g, Bäckerprozent, Teigausbeute, Hydration und Kosten stehen
sofort daneben. Ohne Knopfdruck: Jede Änderung wird unmittelbar übernommen.

**Etikettieren.** Ein Nährwert-Etikett in vier Formaten und drei Farbstimmungen,
mit Vorschau. Speichern, „Speichern unter“ oder direkt in den Druckdialog –
ohne Umweg über eine Datei. Aufbau und Reihenfolge folgen Anhang XV der
VO (EU) Nr. 1169/2011.

**Prüfen.** Eine eingebaute Plausibilitätsprüfung findet Datenfehler, bevor sie
in einer Auswertung landen: verletzte Massenbilanz, ein Brennwert, der nicht zu
den Nährstoffen passt, unmögliche Wassergehalte, Dubletten. Auch von der
Kommandozeile aus, etwa in einer CI-Pipeline.

**Verwalten.** Zutaten mit eigenem Herstellerfeld, Preisen samt Quelle und
Preisstand, Preishistorie, Import und Export einzelner Zutaten als JSON,
Rezeptverwaltung mit Skalierung, PDF-Bericht, CSV-Export.

| Zutatenverwaltung | Etikett mit Vorschau |
|---|---|
| ![Zutaten](docs/bilder/zutaten.png) | ![Etikett](docs/bilder/etikett.png) |

## Installation

```bash
git clone https://github.com/Paxipu/Nutrition-Brotrechner.git
cd Nutrition-Brotrechner
python -m venv .venv
source .venv/bin/activate        # Windows:  .venv\Scripts\activate
pip install -e ".[pdf]"
```

Danach starten:

```bash
brotrechner                      # Oberfläche
python -m brotrechner            # dasselbe, ohne Installation eines Skripts
```

Unter Linux braucht Qt zusätzlich die üblichen X11- bzw. Wayland-Bibliotheken.
Auf Debian/Ubuntu genügt in aller Regel:

```bash
sudo apt install libxcb-cursor0 libxkbcommon-x11-0
```

Der PDF-Bericht ist optional. Ohne `reportlab` fehlt nur diese eine Schaltfläche,
alles andere funktioniert unverändert.

## Kommandozeile

```bash
brotrechner check                # Datenprüfung, Exit-Code 1 bei Fehlern
brotrechner check --strict       # auch Warnungen führen zu Exit-Code 1
brotrechner export-csv out.csv   # Zutatendatenbank als CSV
brotrechner info                 # Pfade und Bestand
brotrechner --data-dir ./daten   # abweichendes Datenverzeichnis
```

## Wo die Daten liegen

Nutzerdaten liegen im dafür vorgesehenen Verzeichnis des Betriebssystems, damit
ein Programmupdate sie nie überschreibt:

| System    | Verzeichnis                                                 |
|-----------|-------------------------------------------------------------|
| Linux/BSD | `$XDG_DATA_HOME/brotrechner` bzw. `~/.local/share/brotrechner` |
| Windows   | `%APPDATA%\Brotrechner`                                      |
| macOS     | `~/Library/Application Support/Brotrechner`                  |

Zwei Auswege: Die Umgebungsvariable `BROTRECHNER_DATA_DIR` setzt das
Verzeichnis unabhängig vom System, und ein Ordner `data` neben dem
Projektverzeichnis schaltet den *portablen Modus* ein – praktisch für den
Betrieb vom USB-Stick.

Vor jedem Überschreiben legt das Programm eine Sicherung in `<Daten>/backups`
an und hält die zehn jüngsten Stände. Geschrieben wird atomar: Ein Absturz
mitten im Speichern kann keine halbe JSON-Datei hinterlassen.

### Übernahme aus der Vorgängerversion

Liegen im Startverzeichnis die Dateien `brot_zutaten.json` und
`brot_rezepte.json` des alten Einzelskripts, werden sie beim ersten Start
automatisch übernommen und migriert. Die Originaldateien bleiben unverändert
liegen. Was dabei passiert, steht in
[`docs/DATENKORREKTUREN.md`](docs/DATENKORREKTUREN.md).

## Fachliche Grundlagen

| Größe | Definition |
|---|---|
| **Bäckerprozent** | Jede Zutat relativ zur Gesamtmehlmenge, die per Definition 100 % ist. Was als Mehl zählt, ist je Zutat ein ausdrückliches Feld – keine Namensheuristik. |
| **Teigausbeute (TA)** | `(Mehl + Schüttwasser) / Mehl × 100`. Als Schüttwasser zählt das *tatsächlich enthaltene* Wasser aller Nicht-Mehl-Zutaten: 100 g Milch steuern 87,5 g bei, nicht 100 g. |
| **Hydration** | `Schüttwasser / Mehl × 100`, also stets `TA − 100`. |
| **Brennwert** | Berechnet nach Anhang XIV VO (EU) Nr. 1169/2011: Kohlenhydrate 4, Eiweiß 4, Fett 9, **Ballaststoffe 2 kcal/g**. Der Ballaststoffanteil fehlt auf vielen Etiketten. |
| **Kohlenhydrate** | Nach EU-Konvention **ohne** Ballaststoffe. Wer Werte aus US-Quellen übernimmt, muss die Ballaststoffe vorher abziehen. |
| **Toleranzen** | Tabelle 1 der EU-Guidance zu Deklarationstoleranzen, Dezember 2012. Für den Brennwert ist dort *keine* Toleranz definiert; er wird deshalb aus den Nährstoffgrenzen abgeleitet. |
| **Referenzmengen** | Anhang XIII Teil B VO (EU) Nr. 1169/2011 (8400 kJ / 2000 kcal). Ballaststoffe haben dort keine Referenzmenge – verglichen wird mit dem DGE-Richtwert von 30 g/Tag. |
| **Ampel** | Keine EU-Vorgabe, sondern die Kriterien der britischen Front-of-Pack-Kennzeichnung. Im Programm entsprechend gekennzeichnet. |

## Aufbau

```
src/brotrechner/
├── core/        Fachlogik, ohne GUI und ohne Dateizugriff
│   ├── nutrients.py    Nährwertvektor, Energieberechnung
│   ├── models.py       Zutat, Rezept, Kategorien
│   ├── analysis.py     Bäckerprozent, Teigausbeute, Kosten
│   ├── tolerances.py   EU-Deklarationstoleranzen
│   ├── reference.py    Referenzmengen und Ampel
│   └── validation.py   Plausibilitätsprüfung
├── data/        Laden, Speichern, Migration, Zutatenaustausch
├── export/      PNG-Etikett, PDF-Bericht, CSV
└── gui/         Qt-Oberfläche, enthält keine Fachlogik
```

Die Schichten importieren ausschließlich „nach unten“: `gui` → `export`/`data`
→ `core`. Deshalb lässt sich die gesamte Rechnung ohne Qt testen, und `core`
hat außer der Standardbibliothek keine Abhängigkeit.

## Entwicklung

```bash
pip install -e ".[dev]"
pytest                                   # Testlauf
ruff check . && ruff format --check .    # Stil
mypy src/brotrechner                     # Typprüfung (strict)
python tools/build_seed_database.py      # Startdatenbank neu erzeugen
```

Alles in einem Durchgang, so wie es auch die CI ausführt:

```bash
python tools/quality_gate.py
```

Die ausgelieferte Zutatendatenbank ist keine handgepflegte JSON-Datei, sondern
das Ergebnis von `tools/build_seed_database.py`. Dort steht zu jedem Wert die
Quelle, und der Brennwert wird gerechnet statt abgetippt. Änderungen gehören in
den Generator, nicht in die erzeugte Datei.

## Urheberschaft

Copyright © 2026 **Martin Kraus**

Konzept, fachliche Vorgaben, Entscheidungen über Aufbau und Funktionsumfang
sowie die Abnahme: Martin Kraus. Der gesamte Quelltext, die Testsuite und die
Dokumentation wurden von **Claude (Anthropic)** erzeugt.

Das gilt ausdrücklich auch für die mitgelieferte Zutatendatenbank: Sie ist die
Ausgabe eines Generators, in dem zu jedem Wert eine Quelle hinterlegt ist. Was
gegenüber der Vorgängerfassung geändert wurde und warum, steht nachprüfbar in
[`docs/DATENKORREKTUREN.md`](docs/DATENKORREKTUREN.md).

## Lizenz

**GNU General Public License, Version 3 oder später** (GPL-3.0-or-later) –
vollständiger Text in [LICENSE](LICENSE).

Dieses Programm ist freie Software: Sie dürfen es weitergeben und/oder
verändern. Es wird in der Hoffnung verbreitet, dass es nützlich ist, jedoch
**ohne jede Gewährleistung** – auch ohne die implizite Gewährleistung der
Marktreife oder der Eignung für einen bestimmten Zweck.

Wer das Programm weitergibt oder darauf aufbaut, muss den Quelltext des
abgeleiteten Werks ebenfalls unter der GPL zugänglich machen.

Die verwendeten Bibliotheken sind damit vereinbar: PySide6 steht unter der
LGPL, Pillow unter der MIT-CMU-Lizenz, reportlab unter der BSD-Lizenz.

## Haftungsausschluss zu den Nährwerten

Die Nährwerte der mitgelieferten Startdatenbank sind Referenz- und
Handelswerte und ersetzen **keine Laboranalyse**. Für Lebensmittel, die in
Verkehr gebracht werden, gelten die Anforderungen der VO (EU) Nr. 1169/2011;
die Verantwortung für die Richtigkeit einer Kennzeichnung liegt beim
Inverkehrbringer.
