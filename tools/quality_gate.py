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
import io
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Regeln, die ruff derzeit noch als Vorschau führt, in einer neueren Fassung
#: aber fest einschaltet. Sie werden gesondert geprüft, damit die CI nicht
#: Verstöße meldet, die es lokal noch gar nicht gibt.
_PREVIEW_RULES = "PLR0917"
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
            [*python, "ruff", "check", SRC, TESTS, "tools", "packaging"],
            "ruff check --fix behebt die meisten Punkte automatisch.",
        ),
        Step(
            "Format",
            [*python, "ruff", "format", "--check", SRC, TESTS, "tools", "packaging"],
            "ruff format schreibt die Dateien um.",
        ),
        # Vorschau-Regeln, die eine kommende ruff-Fassung fest einschalten wird.
        # Ohne diesen Schritt fällt so etwas erst in der CI auf, weil dort eine
        # neuere Fassung installiert wird als auf dem Entwicklungsrechner - genau
        # das ist hier zweimal passiert.
        Step(
            "Lint (Vorschau)",
            [
                *python,
                "ruff",
                "check",
                "--preview",
                "--select",
                _PREVIEW_RULES,
                SRC,
                TESTS,
                "tools",
                "packaging",
            ],
            "Diese Regeln gelten ab der nächsten ruff-Nebenversion.",
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
        # Geprüft werden die *deklarierten* Abhängigkeiten des Projekts, nicht
        # die aktive Umgebung. Ohne virtuelle Umgebung würde sonst der gesamte
        # Paketbestand des Systems bewertet - dessen Befunde haben mit diesem
        # Projekt nichts zu tun und würden das Tor dauerhaft rot färben.
        steps.append(
            Step(
                "Abhängigkeiten",
                [*python, "pip_audit", "--progress-spinner", "off", "-r", _requirements_file()],
                "Betroffene Untergrenze in pyproject.toml anheben.",
            )
        )
    return steps


#: Liest die Einträge aus dem Block ``dependencies = [ ... ]``.
_DEPENDENCY_BLOCK = re.compile(r"^dependencies\s*=\s*\[(.*?)\]", re.MULTILINE | re.DOTALL)
_QUOTED = re.compile(r'"([^"]+)"')


def _requirements_file() -> str:
    """Schreibt die deklarierten Laufzeitabhängigkeiten in eine temporäre Datei.

    Bewusst mit einem kleinen regulären Ausdruck statt mit ``tomllib``: Das
    Projekt unterstützt Python 3.10, wo ``tomllib`` noch fehlt, und eine
    zusätzliche Abhängigkeit allein für diesen Zweck wäre unverhältnismäßig.
    """
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = _DEPENDENCY_BLOCK.search(text)
    if match is None:  # pragma: no cover - pyproject.toml ist Teil des Projekts
        raise SystemExit("In pyproject.toml wurde kein dependencies-Block gefunden.")

    requirements = _QUOTED.findall(match.group(1))
    target = Path(tempfile.mkdtemp()) / "requirements.txt"
    target.write_text("\n".join(requirements) + "\n", encoding="utf-8")
    return str(target)


def _utf8_output() -> dict[str, str]:
    """Stellt die Ausgabe auf UTF-8 um und liefert die Umgebung für die Prüfschritte.

    Unter Windows schreibt Python in eine Pipe oder Datei in der ANSI-Codepage
    (cp1252), die „─“ nicht kennt - die CI brach daran mit UnicodeEncodeError
    ab. Die Prüfschritte schreiben in dieselbe Ausgabe und bekommen deshalb
    dieselbe Kodierung. Bewusst nur für die Ein- und Ausgabe und nicht als
    UTF-8-Modus: Die Tests sollen weiterhin auffallen, wenn irgendwo eine
    Datei ohne ``encoding=`` geöffnet wird.
    """
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    return {**os.environ, "PYTHONIOENCODING": "utf-8"}


def main() -> int:
    """Führt alle Schritte aus und meldet eine Zusammenfassung."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fast", action="store_true", help="Ohne Abdeckungsmessung.")
    parser.add_argument("--audit", action="store_true", help="Zusätzlich pip-audit ausführen.")
    args = parser.parse_args()

    env = _utf8_output()
    results: list[tuple[Step, bool]] = []
    for step in build_steps(fast=args.fast, audit=args.audit):
        print(f"\n\033[1m── {step.name} " + "─" * max(0, 60 - len(step.name)) + "\033[0m")
        print(f"$ {' '.join(step.command)}\n", flush=True)
        completed = subprocess.run(step.command, cwd=ROOT, check=False, env=env)
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
