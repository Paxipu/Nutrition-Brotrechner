"""Erlaubt den Start über ``python -m brotrechner``."""

from __future__ import annotations

from brotrechner.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
