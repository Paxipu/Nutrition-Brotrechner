# Datenkorrekturen

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


## Befunde vorher und nachher

| | Vorgängerversion | geprüfte Fassung |
|---|---:|---:|
| Fehler (Bilanz verletzt) | 15 | 0 |
| Warnungen | 14 | 0 |
| Hinweise (fehlender Preis) | 107 | 0 |
| Zutaten insgesamt | 107 | 107 |
| davon mit Preis | 0 | 107 |

## Zusammengeführte Einträge

- 'KürbiskernÖl (dm Bio)' und 'Kürbiskernöl (dm Bio)' zusammengeführt (unterscheiden sich nur in der Schreibweise)

## Geänderte Nährwerte (92 von 107 Zutaten)

| Zutat | Änderung | Begründung |
|---|---|---|
| Altbrot (Paniermehl) | Energie 395,0 → 366,0; Fett 5,0 → 5,3; davon gesättigte Fettsäuren 1,0 → 1,2; Kohlenhydrate 72,0 → 64,0; Eiweiß 13,0 → 13,4; Ballaststoffe 4,0 → 4,5; Wassergehalt 6,0 → 6,5 | Zählt nicht mehr als Mehl: Paniermehl ist bereits gebackenes Brot und gehört im Bäckerprozent nicht zur Mehlmenge. Die alte Namens-Heuristik hatte es wegen der Silbe 'mehl' als Mehl gewertet. |
| Amaranth | Energie 371,0 → 365,0; Kohlenhydrate 56,0 → 58,6; Eiweiß 14,5 → 13,6; Ballaststoffe 7,0 → 6,7; Wassergehalt 12,0 → 11,3 | an die Referenzwerte angeglichen |
| Anissamen | Energie 337,0 → 384,0; Fett 16,0 → 15,9; davon Zucker 0,5 → 0,0; Wassergehalt 9,0 → 9,5 | an die Referenzwerte angeglichen |
| Apfel (frisch) | Energie 52,0 → 54,0 | an die Referenzwerte angeglichen |
| Backmalz (inaktiv) | Energie 340,0 → 346,0 | an die Referenzwerte angeglichen |
| Backpulver | Energie 53,0 → 91,0; Fett 0,0 → 0,1; davon gesättigte Fettsäuren 0,0 → 0,1; Kohlenhydrate 28,0 → 22,0; Eiweiß 0,0 → 0,1; Salz 27,0 → 44,0 | Werte nach Dr. Oetker Backin als Marktstandard. Formulierungen anderer Hersteller weichen im Salzgehalt deutlich ab. |
| Brotgewürz (Mischung) | Energie 300,0 → 367,0; Fett 14,0 → 17,0; Kohlenhydrate 35,0 → 20,0; davon Zucker 2,0 → 1,5; Eiweiß 12,0 → 16,0; Salz 0,3 → 0,1; Ballaststoffe 20,0 → 35,0; Wassergehalt 10,0 → 9,0 | Aus den Einzelgewürzen Koriander, Fenchel, Kümmel und Anis gemittelt; die alte Massenbilanz war nicht schlüssig. |
| Buchweizenmehl | Energie 340,0 → 332,0; Kohlenhydrate 71,0 → 68,0; Ballaststoffe 3,7 → 4,5; Wassergehalt 13,0 → 12,5 | an die Referenzwerte angeglichen |
| Butter | Fett 83,0 → 82,0 | an die Referenzwerte angeglichen |
| Buttermilch | Energie 38,0 → 34,0 | an die Referenzwerte angeglichen |
| Chiasamen | Energie 486,0 → 442,0; Fett 31,0 → 30,7; Eiweiß 17,0 → 16,5; Ballaststoffe 34,0 → 34,4 | an die Referenzwerte angeglichen |
| Cranberries (getrocknet) | Energie 308,0 → 313,0 | an die Referenzwerte angeglichen |
| Crème fraîche | Energie 302,0 → 291,0 | an die Referenzwerte angeglichen |
| Dinkel (ganz) | Energie 338,0 → 335,0; Fett 2,7 → 2,4; davon gesättigte Fettsäuren 0,5 → 0,4; Kohlenhydrate 63,0 → 58,5; davon Zucker 1,5 → 2,6; Eiweiß 14,5 → 14,6; Ballaststoffe 10,0 → 10,7; Wassergehalt 13,0 → 11,0 | Massenbilanz lag vorher bei 103,2 g je 100 g. |
| Dinkel (ganz) (Alnatura) | Energie 338,0 → 335,0; Fett 2,7 → 2,4; davon gesättigte Fettsäuren 0,5 → 0,4; Kohlenhydrate 63,0 → 58,5; davon Zucker 1,5 → 2,6; Eiweiß 14,5 → 14,6; Ballaststoffe 10,0 → 10,7; Wassergehalt 13,0 → 11,0 | an die Referenzwerte angeglichen |
| Dinkelmehl Type 1050 | Fett 2,0 → 1,8; davon Zucker 0,5 → 1,0; Eiweiß 12,5 → 12,0; Ballaststoffe 6,5 → 6,0 | an die Referenzwerte angeglichen |
| Dinkelmehl Type 630 | Energie 348,0 → 341,0; Fett 1,5 → 1,4; Kohlenhydrate 70,0 → 69,0; davon Zucker 0,5 → 1,0; Ballaststoffe 3,9 → 4,0 | an die Referenzwerte angeglichen |
| Dinkelmehl Type 630 (Aldi) | Energie 348,0 → 341,0; Fett 1,5 → 1,4; Kohlenhydrate 70,0 → 69,0; davon Zucker 0,5 → 1,0; Ballaststoffe 3,9 → 4,0 | an die Referenzwerte angeglichen |
| Dinkelmehl Type 630 (Rewe) | Energie 348,0 → 341,0; Fett 1,5 → 1,4; Kohlenhydrate 70,0 → 69,0; davon Zucker 0,5 → 1,0; Ballaststoffe 3,9 → 4,0 | an die Referenzwerte angeglichen |
| Dinkelvollkornmehl | Energie 330,0 → 329,0; Fett 2,5 → 2,4; davon gesättigte Fettsäuren 0,5 → 0,4; Kohlenhydrate 61,0 → 59,0; davon Zucker 0,6 → 1,2; Eiweiß 14,0 → 13,0; Wassergehalt 13,0 → 12,5 | an die Referenzwerte angeglichen |
| Dinkelvollkornmehl (Alnatura) | Energie 330,0 → 329,0; Fett 2,5 → 2,4; davon gesättigte Fettsäuren 0,5 → 0,4; Kohlenhydrate 61,0 → 59,0; davon Zucker 0,6 → 1,2; Eiweiß 14,0 → 13,0; Wassergehalt 13,0 → 12,5 | an die Referenzwerte angeglichen |
| Dinkelvollkornmehl (dm Bio) | Energie 330,0 → 329,0; Fett 2,5 → 2,4; davon gesättigte Fettsäuren 0,5 → 0,4; Kohlenhydrate 61,0 → 59,0; davon Zucker 0,6 → 1,2; Eiweiß 14,0 → 13,0; Wassergehalt 13,0 → 12,5 | an die Referenzwerte angeglichen |
| Ei | Energie 155,0 → 150,0; Fett 11,0 → 10,6; davon gesättigte Fettsäuren 3,3 → 3,2; Eiweiß 13,0 → 12,6 | Packungsgröße = 10 Eier Größe M ohne Schale (je rund 50 g). |
| Einkornmehl Vollkorn | Energie 338,0 → 331,0; Kohlenhydrate 62,5 → 58,0; davon Zucker 0,9 → 1,2; Eiweiß 14,0 → 14,5; Ballaststoffe 7,5 → 8,0; Wassergehalt 13,0 → 12,5 | an die Referenzwerte angeglichen |
| Emmermehl Vollkorn | Energie 335,0 → 328,0; Fett 2,5 → 2,4; Kohlenhydrate 62,0 → 58,0; davon Zucker 0,8 → 1,0; Eiweiß 14,5 → 14,0; Ballaststoffe 8,5 → 9,0; Wassergehalt 13,0 → 12,5 | an die Referenzwerte angeglichen |
| Feigen (getrocknet) | Energie 249,0 → 253,0 | an die Referenzwerte angeglichen |
| Fenchelsamen | Energie 345,0 → 327,0; Kohlenhydrate 36,6 → 12,5; davon Zucker 0,5 → 0,0; Wassergehalt 9,0 → 8,8 | Kohlenhydrate von 36,6 auf 12,5 g korrigiert; die Massenbilanz lag vorher bei 116,2 g je 100 g. |
| Flohsamenschalen | Energie 21,0 → 188,0 | Brennwert von 21 auf 188 kcal korrigiert. Anhang XIV der VO (EU) 1169/2011 schreibt für Ballaststoffe 2 kcal/g vor; viele Etiketten lassen diesen Anteil weg. |
| Frischkäse (Doppelrahm) | Energie 262,0 → 256,0 | an die Referenzwerte angeglichen |
| Gluten (Weizenkleber) | Energie 370,0 → 373,0 | an die Referenzwerte angeglichen |
| Gluten rein (Grünland) | Energie 370,0 → 373,0 | an die Referenzwerte angeglichen |
| Grünkern | Energie 337,0 → 328,0; Kohlenhydrate 63,0 → 60,0; Eiweiß 12,0 → 11,6; Ballaststoffe 7,0 → 8,8 | an die Referenzwerte angeglichen |
| Grünkern fränkisch (dm) | Energie 337,0 → 328,0; Kohlenhydrate 63,0 → 60,0; Eiweiß 12,0 → 11,6; Ballaststoffe 7,0 → 8,8 | an die Referenzwerte angeglichen |
| Hafer (ganz) | Energie 352,0 → 369,0; Fett 7,1 → 7,0; Kohlenhydrate 55,7 → 58,0; davon Zucker 1,1 → 1,0; Eiweiß 11,7 → 13,5; Ballaststoffe 9,7 → 10,0; Wassergehalt 13,0 → 11,0 | an die Referenzwerte angeglichen |
| Hafer (ganz) (dm) | Energie 352,0 → 369,0; Fett 7,1 → 7,0; Kohlenhydrate 55,7 → 58,0; davon Zucker 1,1 → 1,0; Eiweiß 11,7 → 13,5; Ballaststoffe 9,7 → 10,0; Wassergehalt 13,0 → 11,0 | an die Referenzwerte angeglichen |
| Haferflocken | davon gesättigte Fettsäuren 1,2 → 1,3; Kohlenhydrate 63,3 → 58,7; Wassergehalt 12,0 → 10,0 | Kohlenhydrate von 63,3 auf 58,7 g und Wasser von 12 auf 10 % korrigiert; die Massenbilanz lag vorher bei 105,8 g je 100 g. |
| Haferflocken Großblatt (Bauck) | davon gesättigte Fettsäuren 1,2 → 1,3; Kohlenhydrate 63,3 → 58,7; Wassergehalt 12,0 → 10,0 | an die Referenzwerte angeglichen |
| Haferkleie | Energie 246,0 → 366,0; Kohlenhydrate 30,0 → 50,8; davon Zucker 1,0 → 1,5; Wassergehalt 9,0 → 6,6 | Brennwert von 246 auf 367 kcal und Kohlenhydrate von 30 auf 50,8 g korrigiert. |
| Haferkleie (dm Bio) | Energie 246,0 → 366,0; Kohlenhydrate 30,0 → 50,8; davon Zucker 1,0 → 1,5; Wassergehalt 9,0 → 6,6 | an die Referenzwerte angeglichen |
| Hanfsamen (geschält) | Energie 553,0 → 592,0; Kohlenhydrate 2,8 → 4,7 | an die Referenzwerte angeglichen |
| Haselnüsse | Energie 644,0 → 655,0; Fett 61,6 → 60,8; Kohlenhydrate 6,0 → 7,0; Eiweiß 12,0 → 15,0; Ballaststoffe 8,2 → 9,7; Wassergehalt 5,0 → 5,3 | an die Referenzwerte angeglichen |
| Hefe (frisch) | Energie 94,0 → 105,0; Fett 0,5 → 1,9; davon gesättigte Fettsäuren 0,1 → 0,4; Kohlenhydrate 2,0 → 5,0; davon Zucker 2,0 → 1,0; Eiweiß 11,4 → 14,0; Salz 0,1 → 0,1; Ballaststoffe 0,0 → 6,0 | Brennwert von 94 auf 105 kcal korrigiert; die alten Kohlenhydrate (2 g) passten nicht zum angegebenen Brennwert. |
| Hirse | Energie 360,0 → 356,0; Fett 3,9 → 4,2; Kohlenhydrate 69,0 → 64,4; davon Zucker 1,0 → 0,0; Eiweiß 10,6 → 11,0; Ballaststoffe 3,8 → 8,5; Wassergehalt 12,0 → 8,7 | an die Referenzwerte angeglichen |
| Honig | Energie 304,0 → 321,0; Kohlenhydrate 75,0 → 80,0; davon Zucker 75,0 → 80,0; Eiweiß 0,4 → 0,3; Wassergehalt 18,0 → 17,0 | an die Referenzwerte angeglichen |
| Joghurt (1,5% Fett) | Energie 49,0 → 50,0 | an die Referenzwerte angeglichen |
| Joghurt (griechisch, 10%) | Energie 133,0 → 132,0 | an die Referenzwerte angeglichen |
| Joghurt (natur, 3,5%) | Energie 62,0 → 65,0 | an die Referenzwerte angeglichen |
| Kartoffelstärke | Energie 333,0 → 325,0; Kohlenhydrate 83,1 → 81,0 | Kartoffelstärke ist stark hygroskopisch und hält handelsüblich 18-20 % Wasser. |
| Kokosöl | Energie 862,0 → 884,0 | an die Referenzwerte angeglichen |
| Koriandersamen | Energie 298,0 → 346,0; Kohlenhydrate 13,6 → 13,1; Ballaststoffe 42,0 → 41,9; Wassergehalt 8,0 → 8,9 | an die Referenzwerte angeglichen |
| Kümmel | Energie 375,0 → 334,0; Fett 22,3 → 14,6; Kohlenhydrate 33,7 → 11,9; Wassergehalt 10,0 → 9,9 | Kohlenhydrate von 33,7 auf 11,9 g korrigiert; die Massenbilanz lag vorher bei 124 g je 100 g. |
| Kürbiskerne | Energie 559,0 → 593,0; davon gesättigte Fettsäuren 9,0 → 8,7; Kohlenhydrate 10,7 → 4,7 | Kohlenhydrate von 10,7 auf 4,7 g korrigiert: der alte Wert enthielt die Ballaststoffe noch (US-Konvention). |
| Leinmehl (teilentölt) | Energie 290,0 → 336,0 | an die Referenzwerte angeglichen |
| Leinmehl (teilentölt) (Rapunzel) | Energie 290,0 → 336,0 | an die Referenzwerte angeglichen |
| Leinsamen | Energie 534,0 → 514,0 | an die Referenzwerte angeglichen |
| Lievito Madre (Weizensauer) | Energie 160,0 → 213,0; Fett 0,5 → 0,7; Kohlenhydrate 33,0 → 43,0; davon Zucker 1,0 → 0,5; Eiweiß 5,0 → 7,3; Ballaststoffe 1,5 → 2,7; Wassergehalt 50,0 → 42,3 | Neu berechnet für einen festen Weizensauer mit Teigausbeute 150 abzüglich rund 8 % Gärverlust. |
| Maismehl | Energie 355,0 → 343,0; Kohlenhydrate 76,0 → 74,0; Ballaststoffe 3,9 → 4,0 | an die Referenzwerte angeglichen |
| Mandeln | Energie 576,0 → 595,0; Fett 49,4 → 49,9; davon gesättigte Fettsäuren 3,7 → 3,8; Kohlenhydrate 5,7 → 9,1; davon Zucker 4,2 → 4,4; Ballaststoffe 12,2 → 12,5; Wassergehalt 5,0 → 4,4 | an die Referenzwerte angeglichen |
| Milchpulver (Vollmilch) | Energie 496,0 → 499,0 | an die Referenzwerte angeglichen |
| Mohn (blau) | Energie 525,0 → 520,0; Fett 42,0 → 41,6; davon gesättigte Fettsäuren 4,6 → 4,5; Kohlenhydrate 4,0 → 8,6; davon Zucker 1,0 → 3,0; Eiweiß 20,0 → 18,0; Ballaststoffe 20,0 → 19,5 | an die Referenzwerte angeglichen |
| Oliven (schwarz) | Energie 115,0 → 119,0 | Packungsgröße = Abtropfgewicht. |
| Quark (Magerquark) | Energie 73,0 → 71,0 | an die Referenzwerte angeglichen |
| Quinoa | Energie 346,0 → 354,0; Kohlenhydrate 58,5 → 57,2; davon Zucker 3,0 → 2,0; Wassergehalt 13,0 → 13,3 | an die Referenzwerte angeglichen |
| Reismehl | Energie 366,0 → 347,0; Kohlenhydrate 80,0 → 78,5; Ballaststoffe 1,0 → 2,0 | an die Referenzwerte angeglichen |
| Roggenmehl Type 1150 | Energie 325,0 → 321,0; Fett 1,7 → 1,2; Kohlenhydrate 60,7 → 65,0; davon Zucker 0,9 → 1,3; Eiweiß 9,5 → 8,0; Ballaststoffe 8,6 → 9,0; Wassergehalt 14,0 → 13,5 | an die Referenzwerte angeglichen |
| Roggenmehl Type 1370 | Energie 320,0 → 317,0; Fett 1,8 → 1,4; Kohlenhydrate 58,0 → 62,0; davon Zucker 1,0 → 1,4; Eiweiß 10,0 → 8,5; Ballaststoffe 10,5 → 11,0; Wassergehalt 14,0 → 13,5 | an die Referenzwerte angeglichen |
| Roggenmehl Type 997 | Energie 330,0 → 324,0; Fett 1,3 → 1,0; Kohlenhydrate 65,0 → 68,0; davon Zucker 1,0 → 1,2; Eiweiß 8,4 → 7,0; Ballaststoffe 7,7 → 7,5; Wassergehalt 14,0 → 13,5 | an die Referenzwerte angeglichen |
| Roggenvollkornmehl | Energie 323,0 → 317,0; Fett 2,0 → 1,7; Kohlenhydrate 62,0 → 60,0; davon Zucker 0,9 → 1,0; Eiweiß 13,0 → 8,5; Ballaststoffe 13,4 → 14,0; Wassergehalt 14,0 → 13,0 | Eiweiß korrigiert: 13 g war ein Wert für Weizen; Roggenvollkorn liegt bei 8-9 g. |
| Roggenvollkornmehl (Alnatura) | Energie 323,0 → 317,0; Fett 2,0 → 1,7; Kohlenhydrate 62,0 → 60,0; davon Zucker 0,9 → 1,0; Eiweiß 13,0 → 8,5; Ballaststoffe 13,4 → 14,0; Wassergehalt 14,0 → 13,0 | an die Referenzwerte angeglichen |
| Roggenvollkornmehl (Bauck) | Energie 323,0 → 317,0; Fett 2,0 → 1,7; Kohlenhydrate 62,0 → 60,0; davon Zucker 0,9 → 1,0; Eiweiß 13,0 → 8,5; Ballaststoffe 13,4 → 14,0; Wassergehalt 14,0 → 13,0 | an die Referenzwerte angeglichen |
| Roggenvollkornmehl (Spielberger) | Energie 323,0 → 317,0; Fett 2,0 → 1,7; Kohlenhydrate 62,0 → 60,0; davon Zucker 0,9 → 1,0; Eiweiß 13,0 → 8,5; Ballaststoffe 13,4 → 14,0; Wassergehalt 14,0 → 13,0 | an die Referenzwerte angeglichen |
| Rosinen | Energie 299,0 → 296,0 | an die Referenzwerte angeglichen |
| Rübenkraut | Energie 300,0 → 302,0; Kohlenhydrate 73,0 → 74,0; davon Zucker 73,0 → 66,0; Eiweiß 0,5 → 1,5; Salz 0,0 → 0,1; Wassergehalt 25,0 → 22,0 | an die Referenzwerte angeglichen |
| Sahne | Energie 309,0 → 308,0 | an die Referenzwerte angeglichen |
| Sauerteig Anstellgut (Roggen) | Energie 63,0 → 149,0; Fett 0,3 → 0,9; Kohlenhydrate 12,0 → 27,5; Eiweiß 2,5 → 4,3; Ballaststoffe 1,0 → 7,0; Wassergehalt 65,0 → 56,5 | Neu berechnet für Anstellgut mit Teigausbeute 200 (Mehl : Wasser = 1 : 1) abzüglich rund 8 % Gärverlust. Die alten Werte (63 kcal, 12 g KH) entsprachen keiner nachvollziehbaren Führung. |
| Sauerteigpulver | Energie 300,0 → 306,0; Fett 1,0 → 1,5; davon gesättigte Fettsäuren 0,2 → 0,3; Eiweiß 8,0 → 9,0; Salz 2,0 → 0,1; Ballaststoffe 4,0 → 8,0 | an die Referenzwerte angeglichen |
| Schwarzkümmel (Nigella) | Energie 345,0 → 487,0; Fett 22,0 → 35,0; davon gesättigte Fettsäuren 1,5 → 3,0; Kohlenhydrate 21,0 → 12,0; davon Zucker 2,3 → 2,0; Eiweiß 16,0 → 20,0; Ballaststoffe 11,0 → 22,0 | an die Referenzwerte angeglichen |
| Sesam | Energie 573,0 → 588,0; Kohlenhydrate 10,0 → 11,7 | an die Referenzwerte angeglichen |
| Skyr | Energie 63,0 → 62,0 | an die Referenzwerte angeglichen |
| Sojamehl | Energie 430,0 → 441,0; Fett 20,0 → 20,7; Kohlenhydrate 6,0 → 24,3; davon Zucker 6,0 → 7,5; Eiweiß 37,0 → 34,5; Ballaststoffe 12,0 → 9,6; Wassergehalt 7,0 → 5,2 | an die Referenzwerte angeglichen |
| Sonnenblumenkerne | Energie 584,0 → 589,0; Kohlenhydrate 12,3 → 12,0; Eiweiß 22,5 → 21,0; Ballaststoffe 6,3 → 8,0 | an die Referenzwerte angeglichen |
| Tomatenmark | Energie 82,0 → 78,0 | an die Referenzwerte angeglichen |
| Trockenhefe | Energie 325,0 → 333,0 | an die Referenzwerte angeglichen |
| Walnüsse | Energie 654,0 → 689,0 | an die Referenzwerte angeglichen |
| Weizenkeime | Energie 360,0 → 361,0; Fett 10,9 → 9,7; davon gesättigte Fettsäuren 1,9 → 1,7; Kohlenhydrate 37,0 → 38,6; davon Zucker 6,0 → 8,0; Eiweiß 32,0 → 23,2; Ballaststoffe 17,0 → 13,2; Wassergehalt 11,0 → 11,1 | Eiweiß von 32 auf 23,2 g korrigiert; die Massenbilanz lag vorher bei 107,9 g je 100 g. |
| Weizenkleie | Energie 216,0 → 274,0; Kohlenhydrate 21,0 → 21,7; davon Zucker 0,5 → 0,4; Wassergehalt 10,0 → 9,9 | an die Referenzwerte angeglichen |
| Weizenmehl Type 1050 | Energie 333,0 → 334,0; Fett 1,8 → 1,4; Kohlenhydrate 67,0 → 66,0; davon Zucker 0,4 → 0,9; Ballaststoffe 5,2 → 5,5; Wassergehalt 13,0 → 13,5 | an die Referenzwerte angeglichen |
| Weizenmehl Type 405 | Energie 348,0 → 344,0; davon Zucker 0,3 → 0,7; Eiweiß 10,3 → 10,0; Ballaststoffe 3,0 → 3,5 | an die Referenzwerte angeglichen |
| Weizenmehl Type 550 | Energie 342,0 → 341,0; Kohlenhydrate 71,6 → 70,0; davon Zucker 0,3 → 0,7; Eiweiß 10,0 → 11,0; Ballaststoffe 3,2 → 4,0; Wassergehalt 14,0 → 13,5 | an die Referenzwerte angeglichen |
| Weizenmehl Type 550 (Aldi) | Energie 342,0 → 341,0; Kohlenhydrate 71,6 → 70,0; davon Zucker 0,3 → 0,7; Eiweiß 10,0 → 11,0; Ballaststoffe 3,2 → 4,0; Wassergehalt 14,0 → 13,5 | an die Referenzwerte angeglichen |
| Weizenvollkornmehl | Fett 2,1 → 2,0; Kohlenhydrate 60,0 → 58,0; davon Zucker 0,8 → 1,2; Eiweiß 13,3 → 12,0; Ballaststoffe 10,0 → 11,0; Wassergehalt 14,0 → 13,0 | an die Referenzwerte angeglichen |
| Weizenvollkornmehl (Alnatura) | Fett 2,1 → 2,0; Kohlenhydrate 60,0 → 58,0; davon Zucker 0,8 → 1,2; Eiweiß 13,3 → 12,0; Ballaststoffe 10,0 → 11,0; Wassergehalt 14,0 → 13,0 | an die Referenzwerte angeglichen |


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

