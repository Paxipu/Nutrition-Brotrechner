"""Startdatei der Kommandozeile im Windows-Paket (``brotrechner-cli.exe``).

Mit ihr lässt sich das fertige Paket ohne Oberfläche prüfen:
``brotrechner-cli selftest`` schreibt Etikett und Bericht eines Beispielbrots.
"""

from __future__ import annotations

from brotrechner.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
