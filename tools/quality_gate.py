#!/usr/bin/env python3
"""Führt alle Qualitätsprüfungen in einem Durchgang aus.

Genau dieser Befehl läuft auch in der CI. Dass lokal und in der Pipeline
dasselbe ausgeführt wird, ist der ganze Zweck dieser Datei - "bei mir lief es
durch" entsteht durch abweichende Befehle.

Aufruf::

    python tools/quality_gate.py            # alles
    python tools/quality_gate.py --fast     # ohne Testabdeckung
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = "src/brotrechner"
TESTS = "tests"
MIN_COVERAGE = 90


@dataclass(frozen=True, slots=True)
class Step:
    """Ein Prüfschritt mit Anzeigename und Befehl."""

    name: str
    command: list[str]
    hint: str = ""


def build_steps(*, fast: bool, audit: bool) -> list[Step]:
    """Stellt die Prüfschritte zusammen."""
    python = [sys.executable, "-m"]
    steps = [
        Step(
            "Lint",
            [*python, "ruff", "check", SRC, TESTS, "tools"],
            "ruff check --fix behebt die meisten Punkte automatisch.",
        ),
        Step(
            "Format",
            [*python, "ruff", "format", "--check", SRC, TESTS, "tools"],
            "ruff format schreibt die Dateien um.",
        ),
        Step("Typen", [*python, "mypy", SRC], "mypy läuft im Strict-Modus; siehe pyproject.toml."),
    ]

    test_command = [*python, "pytest", TESTS, "-q"]
    if not fast:
        test_command += [
            f"--cov={SRC}",
            "--cov-branch",
            "--cov-report=term-missing",
            f"--cov-fail-under={MIN_COVERAGE}",
        ]
    steps.append(Step("Tests", test_command))

    steps.append(
        Step(
            "Startdatenbank",
            [sys.executable, "tools/build_seed_database.py"],
            "Die erzeugte Datei muss zusammen mit dem Generator eingecheckt werden.",
        )
    )

    if audit:
        steps.append(Step("Abhängigkeiten", [*python, "pip_audit", "--progress-spinner", "off"]))
    return steps


def main() -> int:
    """Führt alle Schritte aus und meldet eine Zusammenfassung."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fast", action="store_true", help="Ohne Abdeckungsmessung.")
    parser.add_argument("--audit", action="store_true", help="Zusätzlich pip-audit ausführen.")
    args = parser.parse_args()

    results: list[tuple[Step, bool]] = []
    for step in build_steps(fast=args.fast, audit=args.audit):
        print(f"\n\033[1m── {step.name} " + "─" * max(0, 60 - len(step.name)) + "\033[0m")
        print(f"$ {' '.join(step.command)}\n")
        completed = subprocess.run(step.command, cwd=ROOT, check=False)
        results.append((step, completed.returncode == 0))

    print("\n" + "═" * 64)
    print("ZUSAMMENFASSUNG")
    print("═" * 64)
    for step, ok in results:
        mark = "\033[32mOK  \033[0m" if ok else "\033[31mFEHL\033[0m"
        print(f"  [{mark}]  {step.name}")
        if not ok and step.hint:
            print(f"          {step.hint}")

    failed = [step.name for step, ok in results if not ok]
    print("═" * 64)
    if failed:
        print(f"ERGEBNIS: {len(failed)} Schritt(e) fehlgeschlagen: {', '.join(failed)}")
        return 1
    print("ERGEBNIS: alles grün.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
