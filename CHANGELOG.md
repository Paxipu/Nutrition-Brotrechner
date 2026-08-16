# Änderungsverlauf

Format nach [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
Versionierung nach [Semantic Versioning](https://semver.org/lang/de/).

## [5.0.1] – 2026-08-16

### Behoben

- **Rezepte ließen sich nach der Datenübernahme nicht speichern.** Die aus der
  Vorgängerversion übernommenen Rezepte trugen Zeitstempel ohne Zeitzone, neu
  angelegte dagegen mit. Beim Sortieren beider zusammen brach Python mit
  `TypeError: can't compare offset-naive and offset-aware datetimes` ab. Weil
  das Speichern in einem Qt-Signal steckt, verschwand die Meldung ungesehen:
  Für den Anwender passierte schlicht nichts - kein Rezept, keine Fehlermeldung.
  Eingelesene Zeitangaben ohne Zone werden jetzt als lokale Zeit gedeutet.
- **Die Vorschlagsliste der Zutatensuche schnitt Text ab.** Bei genau einem
  Treffer fehlten die Unterlängen von "g" und "ß". QCompleter berechnet die
  Höhe seiner Klappliste aus dem Platzbedarf einer Zeile, zeichnet aber mit der
  eingestellten Zeilenhöhe; beide Zahlen stammten aus verschiedenen Quellen.
  Sie kommen jetzt aus einer.
- **Zweistellige Tage im Kalender erschienen als "…".** Die allgemeine
  Tabellenregel des Stylesheets gab jeder Zelle 6 Pixel Polsterung an beiden
  Seiten; bei rund 31 Pixel Spaltenbreite blieb für "27" kein Platz. Der
  Kalender hat jetzt eigene Regeln - samt Navigationsleiste in der Programmfarbe.

### Geändert

- Nach dem Speichern wechselt das Programm auf die Rezepteseite und markiert
  den frischen Eintrag. Vorher blieb offen, ob das Speichern geklappt hat.
- Der **Ablageort der Daten steht dauerhaft in der Statusleiste** und öffnet
  auf Klick den Ordner. Die Frage "wo liegen meine Rezepte eigentlich?" soll
  man nicht suchen müssen.

## [5.0.0] – 2026-08-16

Vollständiger Umbau des früheren Einzelskripts (Brot-Kalkulator 4.0) zu einem
modularen Paket. Die Daten der Vorgängerversion werden beim ersten Start
automatisch übernommen.

### Hinzugefügt

- **Start per Doppelklick.** `Brotrechner starten.pyw` im Hauptordner öffnet
  das Programm ohne Installation und ohne Konsolenfenster. Fehlt eine
  Voraussetzung, erscheint eine verständliche Meldung statt eines Fensters,
  das sich wortlos wieder schließt.
- **Programmsymbol** für Fenster, Taskleiste und Verknüpfungen, erzeugt von
  `tools/build_icon.py` in allen von Windows verlangten Größen.
- **Hersteller als eigenes Feld.** Die Identität einer Zutat ist jetzt das Paar
  aus Name und Hersteller. Dadurch sind Filter, Vergleiche und die
  Zutatenauswahl nach Hersteller möglich.
- **Import und Export einzelner Zutaten** als eigenständige JSON-Dateien, mit
  Vorschau und wählbarem Verhalten bei Namenskollisionen.
- **Etikett-Vorschau** mit vier Formaten, drei Farbstimmungen und wählbarer
  Auflösung. Ausgabe wahlweise als Datei im Standardordner, über „Speichern
  unter“ oder direkt in den Druckdialog des Systems.
- **Plausibilitätsprüfung** der Zutatendatenbank: Massenbilanz, Brennwert nach
  Anhang XIV, Wassergehalt je Kategorie, Dubletten, Preiskonsistenz. Erreichbar
  über die Oberfläche und über `brotrechner check`.
- **Kommandozeile** mit `check`, `export-csv` und `info` – auch ohne Bildschirm
  nutzbar.
- **Preisherkunft und Preisstand** je Zutat; Preisänderungen landen in einer
  Historie.
- **Feld „zählt als Mehl“** je Zutat, frei änderbar.
- Hell- und Dunkelmodus, wahlweise nach Systemvorgabe.

### Geändert

- **Lizenz auf GPL-3.0-or-later** festgelegt. Urheberrechtsvermerk, Hinweis
  auf die fehlende Gewährleistung und die Herkunft des Quelltextes stehen im
  Programm unter *Hilfe → Über Brotrechner*.
- **Oberfläche auf PySide6 (Qt) umgestellt.** wxPython lässt sich unter Linux
  nur mit erheblichem Aufwand installieren; PySide6 kommt als fertiges Paket
  für alle drei Systeme.
- **Rechner in zwei Spalten neu gegliedert**: links die Eingabe, rechts die
  Auswertung in Karten. Die frühere Abfolge aus Eingabemaske, Rechnen-Taste und
  vier Monospace-Reitern entfällt; gerechnet wird laufend.
- **Teigausbeute** zählt das tatsächlich enthaltene Wasser einer Zutat statt
  ihrer vollen Masse. Für Rezepte aus Mehl, Wasser und Salz bleibt das Ergebnis
  gleich; bei Milch, Joghurt oder Sauerteig fällt die TA korrekt niedriger aus.
- **Nutzerdaten** liegen im Datenverzeichnis des Betriebssystems statt neben
  dem Skript. Speichern erfolgt atomar mit rotierender Sicherung.
- **Zutatendatenbank** wird aus `tools/build_seed_database.py` erzeugt; jeder
  Wert trägt eine Quelle, der Brennwert wird berechnet.

### Behoben

- **Deklarationstoleranzen** entsprechen jetzt Tabelle 1 der EU-Guidance von
  Dezember 2012. Bisher galten abweichende Bänder (±1,5 g statt ±2 g für
  Kohlenhydrate unter 10 g, ±25 % statt ±8 g oberhalb 40 g, pauschal ±20 % für
  Salz). Der Brennwert bekommt keine erfundene Toleranz mehr, sondern wird aus
  den Nährstoffgrenzen abgeleitet.
- **Referenzmengen und Ampel** waren beide als „EU-Vorgabe“ ausgewiesen. Die
  Referenzmengen stammen aus Anhang XIII, die Ampelschwellen dagegen aus der
  britischen Front-of-Pack-Kennzeichnung; Ballaststoffe haben gar keine
  EU-Referenzmenge. Alles drei ist jetzt korrekt benannt.
- **„Altbrot (Paniermehl)“** zählte wegen der Silbe „mehl“ als Mehl und
  verfälschte damit Bäckerprozent und Teigausbeute.
- **Doppelte Zutat** „Kürbiskernöl (dm Bio)“ / „KürbiskernÖl (dm Bio)“
  zusammengeführt; Namen werden jetzt unabhängig von der Schreibweise verglichen.
- **92 Zutaten mit korrigierten Nährwerten**, darunter 15 mit verletzter
  Massenbilanz und 15 mit unstimmigem Brennwert. Einzelheiten in
  [`docs/DATENKORREKTUREN.md`](docs/DATENKORREKTUREN.md).
- **Preise für alle 107 Zutaten** hinterlegt, mit Quellenangabe und Preisstand.
- Ein Zeilenumbruch im Rezeptnamen brachte die Etikettausgabe zum Absturz.
- Ein langes Zutatenverzeichnis lief über die Fußzeile des Etiketts hinaus.
- Die Zutatensuche nahm bei mehreren Treffern kommentarlos den ersten. Jetzt
  wird nur eine eindeutige Übereinstimmung übernommen.
- Die Schriftsuche der Etikettausgabe war auf `arial.ttf` festgelegt und fiel
  unter Linux stillschweigend auf eine Bitmap-Schrift zurück.
