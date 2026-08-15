"""Brotrechner - Nährwert-, Kosten- und Bäckerprozent-Rechner für selbstgebackenes Brot.

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

__version__ = "5.0.0"
__all__ = ["__version__"]
