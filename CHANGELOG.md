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

- **Die Nährwerte auf dem Etikett waren nicht nach EU-Regel gerundet.** Jeder
  Wert stand mit einer Nachkommastelle da, Salz mit zweien: 45,34 g
  Kohlenhydrate als „45,3 g“ statt „45 g“, 0,43 g Zucker als „0,4 g“ statt
  „< 0,5 g“, 1,234 g Salz als „1,23 g“ statt „1,2 g“. Etikett und PDF-Bericht
  runden jetzt nach der Leitlinie der EU-Kommission von Dezember 2012,
  kaufmännisch statt mit Pythons Rundung auf die gerade Zahl.

- **Die Spalte „Bandbreite“ zeigte nicht, was ihr Tooltip versprach.** Dort
  stand die Summe der Toleranzen aller Zutaten, gewichtet nach Menge - nicht
  die zulässige Abweichung des Brots, auf die sich die EU-Toleranzen beziehen.
  Bei einem Weizenbrot ergab das ±5,3 g Kohlenhydrate statt ±8 g; reines Salz
  ging mit ±20 % seines Gehalts ein, obwohl die eingewogene Menge genau bekannt
  ist. Rechner und Bericht zeigen jetzt die Toleranz des fertigen Brots. Eine
  Zutat mit negativem Wert ließ die alte Rechnung zudem abbrechen.
- **Eine einzige kaputte Zahl konnte die Datenprüfung abstürzen lassen.** Ein
  Nährwert „unendlich“ - Pythons JSON-Leser akzeptiert ihn aus fremden
  Importdateien - ließ die Prüfung mit `OverflowError` abbrechen; weil die
  Statusleiste bei jeder Änderung die ganze Datenbank prüft, stand damit das
  Programm. `NaN` rutschte dagegen durch jede Prüfung, weil jeder Vergleich
  damit falsch ist. Beides meldet die Prüfung jetzt als Fehler „keine Zahl“.
  Ein Eigenschaftstest setzt dafür beliebige Gleitkommawerte ein.
- **Texte überlappten sich auf dem kleinen Etikett oder liefen über den
  Rand.** Der Aufbau maß bisher nur die Höhe, nicht die Breite. Auf 54 mm
  Breite lief „davon gesättigte Fettsäuren“ in den eigenen Wert, „Brennwert“
  stieß an „996 kJ / 238 kcal“, „Nettogewicht 2,96 kg“ ragte über den Rand,
  der Titel wurde mitten im Wort getrennt („Roggenmischb / rot“), eine lange
  Fußzeile lief über beide Ränder, und das „…“ eines gekürzten
  Zutatenverzeichnisses hing über den Rand hinaus. Jetzt bricht die
  Beschriftung einer Tabellenzeile um (notfalls rückt der Wert in eine eigene
  Zeile), der Titel wird kleiner statt getrennt, Nettogewicht, Datumszeilen
  und Fußzeile brechen um. Außerdem stehen Wert und Beschriftung einer
  Tabellenzeile jetzt auf derselben Grundlinie - die Werte saßen sichtbar
  höher - und mehrzeilige Texte in gleichmäßigem Zeilenabstand. Ein Test
  zeichnet jede Textausgabe auf und prüft Rand und Überdeckung für alle
  Formate, ein Eigenschaftstest mit beliebig langen Texten.
- **Sicherungen verdrängten sich gegenseitig.** Jedes Speichern legte eine
  Sicherung an, auch das automatische beim Beenden. Nach zehnmal Schließen
  ohne Änderung waren die zehn aufbewahrten Sicherungen zehn gleiche Kopien,
  und jeder ältere Stand war verloren. Außerdem trugen die Namen nur Sekunden:
  Zwei Speichervorgänge in derselben Sekunde schrieben dieselbe Sicherung.
  Jetzt wird nur geschrieben und gesichert, wenn sich der Inhalt ändert - ein
  neuer Zeitstempel allein zählt nicht -, die Namen sind eindeutig, und keine
  Sicherung verdoppelt die jüngste. „Sicherung anlegen“ sichert nun den
  jetzigen Stand, nicht nur den vorherigen.
- **Eine unlesbare Datendatei wurde beim Beenden überschrieben.** Ließ sich
  die Zutaten- oder Rezeptdatei beim Start nicht lesen, startete das Programm
  leer und versprach, die Datei nicht zu verändern - beim Schließen schrieb es
  dann die leere Datenbank darüber. Jetzt wird die Datei unverändert
  beiseitegelegt (etwa `ingredients.defekt-20260925_101500.json`), die Meldung
  sagt wo und wie man den alten Stand zurückholt. Die Zutaten beginnen dann
  mit der Startdatenbank, die Rezepte leer. Lässt sich die Datei nicht
  beiseitelegen, schreibt das Programm in dieser Sitzung nicht hinein.
- **Rezeptnotizen fehlten im PDF-Bericht.** Der Bericht kann Notizen
  drucken, das Hauptfenster reichte sie aber nie weiter. Jetzt stehen die
  Notizen eines gespeicherten Rezepts in seinem Bericht.
- **Ein Rezept ließ sich nicht in anderer Schreibweise umbenennen.** Namen
  gelten ohne Rücksicht auf Groß- und Kleinschreibung als gleich; wer
  „roggenbrot“ in „Roggenbrot“ ändern wollte, bekam „Es gibt bereits ein
  Rezept namens …“ - gemeint war das Rezept selbst. Außerdem übernimmt der
  Rechner jetzt den neuen Namen, wenn das Rezept dort geladen ist; das
  nächste Speichern legte sonst ein Duplikat unter dem alten Namen an.
- **Die Auswertung eines Rezepts ließ sich nicht als CSV speichern.** Die
  Funktion dafür gab es, erreichbar war aber nur „Zutaten als CSV“ - die
  Datenbank, nicht das Rezept. Jetzt gibt es „Datei → Auswertung als CSV …“
  mit Mengen, Anteilen, Bäckerprozenten und Kosten je Zutat.
- **Der PDF-Bericht schrieb Zahlen mit Dezimalpunkt.** Beträge und Prozente
  standen dort als „1.99 €“ und „60.0 %“, während Rechner, Etikett und CSV das
  Komma verwenden. Dasselbe galt für die Anteilsspalte im Rechner („60.0 %“
  neben „600,0“ g), Skalierungsfaktor und Backverlust dort sowie die Meldungen
  zu Backverlust, Massenbilanz und Mehlanteil. Jetzt steht überall das Komma.
- **Die Kostenübersicht im PDF-Bericht wurde über den Seitenumbruch
  verteilt.** Reichte der Platz nicht, standen die letzten Zeilen allein oben
  auf der nächsten Seite. Jetzt rückt die Übersicht als Ganzes weiter.
- **Ungespeicherte Arbeit im Rechner ging ohne Rückfrage verloren.** „Neu /
  leeren“, das Laden eines anderen Rezepts und das Beenden verwarfen den
  Rechner ohne ein Wort. Jetzt fragt das Programm „Speichern, Verwerfen oder
  Abbrechen?“, sobald der Rechner vom zuletzt geladenen oder gespeicherten
  Stand abweicht - ein neuer Preis in der Zutatendatenbank zählt dabei nicht
  als Änderung. Wer beim Speichern den Namen abbricht, behält den Rechner.
- **Ein Tippfehler in `settings.json` verhinderte den Start.** Jeder Wert
  wurde ungeprüft übernommen: `"theme": "blau"` ließ das Programm mit
  `ValueError` abbrechen, ein Strompreis `"abc"` scheiterte erst beim
  Rechnen. Jetzt wird jeder Wert auf Typ und Bereich geprüft; für einen
  ungültigen gilt die Vorgabe, die übrigen bleiben erhalten, und das
  Protokoll nennt ihn. Ein Eigenschaftstest liest beliebige JSON-Inhalte.
- **Unerwartete Fehler verschwanden spurlos.** Beim Start per Doppelklick
  gibt es keine Konsole. Eine Ausnahme in einer Aktion ließ deshalb einfach
  einen Knopf nicht reagieren, und scheiterte der Aufbau des Hauptfensters -
  etwa an einer beschädigten Einstellung -, schloss sich das Programm
  wortlos. Jetzt erscheint eine Meldung mit ausklappbarem Hergang, und alles
  steht in `brotrechner.log` im Datenverzeichnis (rotierend, höchstens rund
  1,5 MB). Auch der Doppelklick-Starter fängt Abstürze ab und meldet sie.
- **Das Etikett wurde auf die ganze Druckseite gestreckt.** Ein Etikett von
  70 × 100 mm kam auf A4 rund 200 mm breit aus dem Drucker. Außerdem zählte
  der Druckerrand doppelt, das Etikett saß um den Rand versetzt. Gedruckt wird
  jetzt in Originalgröße, mitten auf dem Papier, auf jedem Drucker gleich: Die
  Lage wird in Millimetern ab der Papierkante berechnet und erst zuletzt mit
  der Auflösung des Druckers umgerechnet. Nachgemessen an einem gedruckten
  PDF: 70,1 × 100,3 mm bei 0,25 mm Messauflösung.

### Hinzugefügt

- **Allergene und Bezeichnung im Zutatenverzeichnis je Zutat.** Für den
  Verkauf müssen Allergene im Zutatenverzeichnis hervorgehoben sein
  (Artikel 21 VO (EU) Nr. 1169/2011) - bisher kannte das Programm sie gar
  nicht. Jede Zutat hat jetzt ihre Allergene nach Anhang II, Getreide und
  Schalenfrüchte einzeln (eine „Enthält“-Angabe muss sie nennen), und eine
  Bezeichnung, in der das Allergen in Sternchen steht: `*Weizen*mehl Type 550`,
  `Roggensauerteig (*Roggen*vollkornmehl, Wasser)`. „Nicht erfasst“ ist dabei
  etwas anderes als „keine“: Eine nie geprüfte Zutat gilt nicht als
  allergenfrei. Die Startdatenbank bringt beides für alle 107 Zutaten mit;
  Margarine, Essig, Trockenfrüchte und Oliven bleiben „nicht erfasst“, weil es
  vom gekauften Produkt abhängt. Zutatendateien aus Version 5.1 übernehmen die
  Angaben beim ersten Start aus der Startdatenbank. Der Zutatendialog ist dafür
  zweispaltig; die Datenprüfung meldet nicht hervorgehobene Allergene und
  Hervorhebungen ohne Allergen, die Zutatenliste und die CSV zeigen beides.
- **Zutatenverzeichnis nach LMIV auf dem Etikett.** Bisher standen dort die
  Datenbanknamen („Hefe (frisch)“, „Sauerteig Anstellgut (Roggen)“), sortiert
  nach der Menge im Teig und ohne Hervorhebung. Jetzt: die Bezeichnung für das
  Zutatenverzeichnis; absteigend nach Gewicht, wobei zugefügtes Wasser mit dem
  zählt, was davon im fertigen Brot bleibt (Anhang VII Teil A) - bei hoher
  Hydration rückt es dadurch hinter das Mehl; gleichnamige Zutaten
  zusammengefasst; Allergene fett und in kräftigerer Farbe, auch mitten im Wort
  („**Weizen**mehl“). Wird kein Verzeichnis gedruckt, steht „Enthält: …“ mit den
  Allergenen auf dem Etikett (Artikel 21 Abs. 1).
- **Plausibilitätsprüfung der Gewichte.** Ein Tippfehler beim Brotgewicht -
  75 statt 750 g - ergab bisher ohne Warnung 2273 kcal je 100 g, mehr als
  reines Fett haben kann, und landete so auf dem Etikett. Der Rechner meldet
  jetzt unter „Backprozess“ ein Brot, das schwerer als sein Teig oder leichter
  als die Trockenmasse der Zutaten ist, und mehr als 900 kcal je 100 g als
  Fehler; einen Backverlust außerhalb von 5 bis 35 % und einen auffälligen
  Rohteig als Warnung. Mit einem Fehler lässt sich kein Etikett speichern oder
  drucken.
- **Etikett für den Verkauf.** Ein Schalter im Etikettdialog prüft laufend die
  Pflichtangaben für verpackt verkauftes Brot nach Artikel 9 VO (EU)
  Nr. 1169/2011: Bezeichnung, Zutatenverzeichnis, erfasste Allergene,
  Nettogewicht, Mindesthaltbarkeitsdatum (nicht vor dem Backtag) sowie Name
  und Anschrift des Herstellers, die neu auf dem Etikett stehen können - dazu
  ein Aufbewahrungshinweis. Im Verkaufsmodus hat jede Schrift mindestens
  1,2 mm x-Höhe (Artikel 13 Abs. 2, Anhang IV), gemessen an der Tinte der
  tatsächlich gezeichneten Schrift; die Ziffern des Nettogewichts erreichen die
  Mindesthöhe nach Fertigpackungsverordnung (bis 50 g 2 mm, bis 200 g 3 mm,
  bis 1 kg 4 mm, darüber 6 mm), und das Zutatenverzeichnis wird nicht mehr
  zugunsten der Schriftgröße gekürzt. Passt der Inhalt nicht, rückt der Fuß
  unter das Verzeichnis, statt es zu überdecken, und der Dialog nennt Abhilfe.
  Geprüft wird in Druckauflösung; offene Punkte stehen unter den
  Einstellungen, Speichern und Drucken fragen dann nach. Die Einstellungen des
  Dialogs liegen dafür in einem Rollbereich.
- **Eigenes Etikettformat.** Neben den vier festen Formaten lässt sich jedes
  Format von 30 bis 297 mm je Seite einstellen - etwa die Maße der Etiketten
  auf einem Bogen, die auf dessen Verpackung stehen. Auch dort bricht jeder
  Text um, einschließlich der Abschnittsüberschriften und Tabellenwerte, die
  bisher fest in einer Zeile standen. Bilder über 40 Millionen Pixel (etwa
  A4 in 1200 dpi) lehnt das Etikett ab, statt den Speicher zu füllen.
- **Druckarten für Etikettendrucker, Etikettenbögen und A4.** Die Karte
  „Druck“ im Etikettdialog bietet: einzeln mitten aufs Blatt; am
  Etikettendrucker je Etikett eine Seite in Etikettgröße, auf Wunsch um 90°
  gedreht für Drucker, die quer einziehen; Etikettenbögen nach den Maßen auf
  der Verpackung (Spalten, Reihen, Rand, Abstand), ab dem ersten freien
  Etikett eines angebrochenen Bogens; mehrere auf A4 zum Ausschneiden - so
  viele, wie mit 10 mm Rand und 5 mm Schnittabstand passen. Dazu die Anzahl
  und eine Zeile, was entsteht („5 Etiketten auf 2 Bögen“). Ein Raster, das
  nicht aufs Blatt passt, wird angezeigt und verhindert Druck und
  Druckvorschau. Jedes Etikett behält seine Originalgröße.

- **Das Programm merkt sich, was man eingestellt hat.** Der Strompreis stand
  schon in den Einstellungen, der Rechner begann aber bei jedem Start mit der
  Vorgabe. Jetzt bleiben er und die Einstellungen des Etikettdialogs
  erhalten: Format samt eigenem Format, Farbe, Auflösung, Fußzeile, die
  Schalter für Backdatum, Ballaststoffe und Referenzhinweis, Verkaufsmodus mit
  Hersteller und Lagerhinweis, Druckart und Bogenraster. Nach einem Druck auf
  einen Etikettenbogen rückt „Beginnen bei“ hinter die gedruckten Etiketten -
  der angebrochene Bogen lässt sich beim nächsten Mal einfach weiterbedrucken.
  Die Haltbarkeit übernimmt der Dialog vom letzten Etikett des Rezepts, statt
  jedes Mal sieben Tage vorzuschlagen. Der Ausgabeordner lässt sich unter
  „Datei → Ausgabeordner wählen …“ festlegen; bisher nur durch Bearbeiten
  der Einstellungsdatei.
- **Nährwerte und Kosten je Portion.** Zu einem Rezept gehört auf Wunsch eine
  Portion: eine Bezeichnung (Scheibe, Stück, Brötchen oder frei eingetragen)
  und ihr Gewicht. Der Rechner nennt dann, wie viele Portionen das Brot ergibt
  („ergibt ca. 19 Scheiben“), und den Preis je Portion; die Nährwerttafel
  schaltet zwischen „je 100 g“ und „je Scheibe (45 g)“ um. Ampel und
  Bandbreite bleiben dabei je 100 g - einen anderen Bezug gibt es für sie
  nicht. Auch die Rezeptvorschau nennt Brennwert, Preis und Zahl der
  Portionen. Eine Portion, die schwerer ist als das ganze Brot, meldet die
  Plausibilitätsprüfung. Rezepte älterer Versionen haben keine Portion; eine
  unlesbare Portionsangabe kostet nicht das ganze Rezept. Der PDF-Bericht
  zeigt die Werte je Portion als eigene Spalte neben „je 100 g“, Portion und
  Zahl der Portionen in den Eckdaten und den Preis je Portion. Die
  Bezeichnung einer Portion hat höchstens 24 Zeichen, damit sie in die
  Tabellenköpfe passt.

### Geändert

- **„Brennwert“ statt „Energie“** auf dem Etikett, im Bericht, in der CSV und
  im Rechner. So heißt die Angabe in der deutschen Fassung der VO (EU)
  Nr. 1169/2011 (Artikel 30, Anhang XV). „Energie“ steht nur noch dort, wo der
  Strom fürs Backen gemeint ist.
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
