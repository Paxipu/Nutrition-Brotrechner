# Änderungsverlauf

Format nach [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
Versionierung nach [Semantic Versioning](https://semver.org/lang/de/).

## [Unveröffentlicht]

### Behoben

- **Sauerteig und Vorteige verfälschten Teigausbeute und Bäckerprozent.** Eine
  Zutat war bisher entweder Mehl oder keins. Ein Anstellgut aus gleichen Teilen
  Mehl und Wasser zählte deshalb gar nicht zur Mehlmenge, sein Wasser aber
  vollständig zum Schüttwasser - einschließlich der Eigenfeuchte des Mehls. Ein
  Roggenbrot aus 400 g Mehl, 200 g Anstellgut, 250 g Wasser und 10 g Salz kam
  so auf TA 191 und 2,5 % Salz statt auf TA 170 und 2,0 %. Jede Zutat hat jetzt
  einen **Mehlanteil** in Prozent: 100 % bei Mehl, 50 % beim Anstellgut (TA 200),
  66,7 % bei Lievito Madre (TA 150). Als Schüttwasser zählt nur das Wasser
  außerhalb dieses Anteils.

### Geändert

- Im Zutatendialog ersetzt das Feld **„Mehlanteil“** das Ankreuzfeld „Zählt als
  Mehl“. Ein Hinweis daneben nennt die Teigausbeute, der ein Anteil entspricht.
- Zutatendateien aus Version 5.1 werden beim ersten Start ergänzt: Sauerteige
  und Vorteige, die es in der Startdatenbank gibt, bekommen deren Mehlanteil.
  Das Programm meldet die Ergänzung einmal. Ein ausdrücklich gespeicherter
  Anteil wird nie verändert. Ältere Programmfassungen lesen die Dateien weiter:
  Reines Mehl bleibt dort Mehl.
- Die CSV-Ausgabe der Zutaten hat statt „Zählt als Mehl“ die Spalte
  „Mehlanteil (%)“.
- Die Datenprüfung meldet einen Mehlanteil außerhalb von 0 bis 100 % als Fehler.

## [5.1.0] – 2026-08-17

### Hinzugefügt

- **Das Backdatum des Etiketts lässt sich wählen.** Bisher war es fest der
  heutige Tag; wer das Etikett erst am Tag danach druckte, bekam ein falsches
  Datum aufs Brot und konnte nichts dagegen tun. Jetzt steht dort ein Feld mit
  Kalender.
- **Die Mindesthaltbarkeit folgt dem Backdatum – aber nur in diese Richtung.**
  Wird der Backtag verschoben, wandert die Haltbarkeit um dieselbe Spanne mit.
  Wird die Haltbarkeit von Hand gesetzt, bleibt das Backdatum unangetastet und
  die gewählte Spanne gilt fortan auch für den nächsten Backtag: Wer einmal
  14 Tage einstellt, meint 14 Tage. Die Haltbarkeit kann nicht mehr vor dem
  Backtag liegen.
- **Notizen zu einem Rezept sind jederzeit nachträglich zu ändern.** Auf der
  Rezepteseite gibt es dafür die Schaltfläche „Notizen …“ mit einem
  mehrzeiligen Feld. Erfahrungen sammeln sich erst über mehrere Backvorgänge an
  – sie zu ergänzen soll nicht bedeuten, das ganze Rezept in den Rechner laden
  und neu speichern zu müssen. Der Text erscheint in der Rezeptvorschau,
  Zeilenumbrüche bleiben erhalten.
- **Jedes erstellte Etikett vermerkt seinen Backtag am Rezept**, zusammen mit
  der Mindesthaltbarkeit. Die Rezeptvorschau zeigt beides an, sodass beim
  nächsten Aufruf ohne Suchen sichtbar ist, wann zuletzt gebacken wurde. Nur
  ein wirklich gespeichertes oder gedrucktes Etikett zählt – den Dialog bloß
  anzusehen datiert kein Rezept um. Die Druckvorschau zählt bewusst nicht mit.

### Geändert

- **Der Kalender beginnt immer beim heutigen Tag**, auch wenn das Rezept
  zuletzt vor Monaten gebacken wurde. Sonst müsste man sich zum Nachbacken
  monateweise nach vorn klicken. Der frühere Backtag steht stattdessen als
  Hinweis unter dem Feld.
- Notizen werden beim Speichern eines Rezepts in einem eigenen Dialog erfasst
  statt in einer einzeiligen Abfrage – es sind meist mehrere Sätze.
- Beim **Überschreiben eines Rezepts** bleiben neben Anlagedatum und Notizen
  jetzt auch Backtag und Haltbarkeit erhalten. Sie gehören zur Geschichte des
  Rezepts, nicht zu den Werten aus dem Rechner.
- Der Etikettdialog ist 40 Pixel höher: Mit den beiden Datumsfeldern passte die
  Seitenspalte sonst um 13 Pixel nicht mehr in die Mindesthöhe, was die
  Schaltflächen gestaucht hätte. Ein Test misst das jetzt nach.

## [5.0.3] – 2026-08-16

### Behoben

- **„Ja“ tat dasselbe wie „Nein“: Jede Rückfrage blieb wirkungslos.** Ein
  bearbeitetes Rezept ließ sich nicht unter demselben Namen überschreiben - die
  Nachfrage erschien, danach standen weiterhin die alten Werte in der Datei.
  Ebenso wenig ließ sich ein Rezept löschen. Ursache: PySide6 gibt die
  angeklickte Schaltfläche von `QMessageBox.question` nicht als Enum-Mitglied
  zurück, sondern als blanke Zahl (nachgemessen mit 6.11: `type(antwort)` ist
  `int`). Der Code verglich sie mit `is` gegen `StandardButton.Yes` - und das
  ist bei zwei verschiedenen Objekten immer falsch, gleichgültig welche
  Schaltfläche der Anwender gewählt hat. Die Bestätigungszweige brachen deshalb
  ausnahmslos ab; sichtbar war davon nichts, hörbar nur der Systemton des
  Dialogs. Betroffen waren fünf Rückfragen: Rezept überschreiben, Rezept
  löschen, Zutat löschen, Etikettdatei überschreiben und „Trotzdem speichern?“
  bei bemängelten Zutatenwerten. Verglichen wird jetzt an jeder Qt-Grenze mit
  `==`, gebündelt in `gui/qt_compat.confirmed()`.
- **Eine bemängelte Zutat ließ sich überhaupt nicht speichern.** Meldete die
  Prüfung einen Fehler, fragte der Zutatendialog „Trotzdem speichern?“ - und
  verwarf die Eingabe auch dann, wenn man zustimmte. Dieselbe Ursache.

### Geändert

- Ein Test durchsucht das gesamte Paket nach Identitätsvergleichen gegen
  Qt-Enums und schlägt an, sobald einer auftaucht. Damit ist nicht nur diese
  eine Stelle behoben, sondern der ganze Fehlertyp ausgeschlossen - Qt reicht
  Enum-Werte je nach Fassung mal als Mitglied, mal als Zahl heraus (die Rolle
  in `headerData` ist schon heute eine Zahl).
- Die früheren Tests liefen an diesem Fehler vorbei, weil ihre Dialogattrappen
  das Enum-Mitglied zurückgaben statt der Zahl, die Qt tatsächlich liefert. Sie
  bilden das Verhalten jetzt originalgetreu ab.

## [5.0.2] – 2026-08-16

### Behoben

- **Das Etikett wird jetzt gemessen, bevor es gezeichnet wird.** Bisher standen
  feste Millimeterabstände im Code, abgestimmt auf ein einziges Format. Auf dem
  kleinen Aufkleber (54 × 86 mm) schoben sich dadurch Nettogewicht, Fußnote und
  Zutatenüberschrift übereinander, und das Verzeichnis fehlte ganz - das Format
  war unbenutzbar. Der Aufbau ermittelt nun für jede Typografiestufe den
  Platzbedarf und zeichnet mit der größten, die passt.
- **Backdatum und Mindesthaltbarkeit stehen auf getrennten Zeilen.** Zusammen
  in einer Zeile liefen sie auf jedem Format über beide Ränder hinaus. Zwei
  Zeilen sind auch inhaltlich richtiger - es sind zwei verschiedene Angaben.
- Das **vollständige Zutatenverzeichnis hat Vorrang vor der Schriftgröße**.
  Passt es nicht, wird zuerst die Typografie eine Stufe kleiner gewählt und
  erst danach gekürzt. Es ist die gesetzlich vorgeschriebene Angabe.

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
