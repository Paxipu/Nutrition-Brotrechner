"""Brotrechner - Nährwert-, Kosten- und Bäckerprozent-Rechner für selbstgebackenes Brot.

Copyright (C) 2026 Martin Kraus

Dieses Programm ist freie Software: Sie können es unter den Bedingungen der
GNU General Public License, Version 3 oder (nach Ihrer Wahl) jeder späteren
Version, weitergeben und/oder verändern. Es wird in der Hoffnung verbreitet,
dass es nützlich ist, jedoch **ohne jede Gewährleistung**; auch ohne die
implizite Gewährleistung der Marktreife oder der Eignung für einen bestimmten
Zweck. Einzelheiten stehen in der GNU General Public License, die diesem
Programm als Datei ``LICENSE`` beiliegt und unter
<https://www.gnu.org/licenses/> abrufbar ist.

Der Quelltext wurde vollständig von Claude (Anthropic) erzeugt, nach Vorgabe
und fachlicher Abnahme durch Martin Kraus.

Das Paket ist in klar getrennte Schichten aufgeteilt:

``brotrechner.core``
    Reine Fachlogik ohne jede GUI- oder Datei-Abhängigkeit: Datenmodell,
    Nährwert-Aggregation, Bäckerprozent/Teigausbeute, EU-Toleranzen,
    Kostenrechnung und Plausibilitätsprüfung.
``brotrechner.data``
    Persistenz: Laden/Speichern der JSON-Datenbanken, Schema-Migration und
    der Austausch einzelner Zutaten über eigenständige JSON-Dateien.
``brotrechner.export``
    Ausgabeformate: PNG-Etikett, PDF-Bericht, CSV.
``brotrechner.gui``
    Qt-Oberfläche (PySide6). Enthält keine Fachlogik.

Alle Schichten dürfen nur "nach unten" importieren: GUI → export/data → core.
"""

from __future__ import annotations

__version__ = "5.1.0"
__author__ = "Martin Kraus"
__license__ = "GPL-3.0-or-later"

__all__ = ["__author__", "__license__", "__version__"]
