"""Kommandozeile.

Ohne Unterbefehl startet die Oberfläche. Die übrigen Befehle sind für den
Betrieb ohne Bildschirm gedacht - etwa um die Datenbank in einer CI-Pipeline
zu prüfen oder eine Sicherung zu exportieren::

    brotrechner                 # Oberfläche
    brotrechner check           # Datenprüfung, Exit-Code 1 bei Fehlern
    brotrechner export-csv out.csv
    brotrechner info            # Pfade und Bestand
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from brotrechner import __version__, paths
from brotrechner.core.validation import Severity, validate_database
from brotrechner.data.repository import RepositoryError, load_ingredients, load_recipes
from brotrechner.data.seed import ensure_user_database
from brotrechner.export import table

__all__ = ["main", "main_gui"]

log = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="brotrechner",
        description="Nährwerte, Kosten und Bäckerprozent für selbstgebackenes Brot.",
    )
    parser.add_argument("--version", action="version", version=f"brotrechner {__version__}")
    parser.add_argument(
        "--data-dir",
        type=Path,
        metavar="PFAD",
        help="Abweichendes Datenverzeichnis (sonst das Standardverzeichnis des Systems).",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Ausführliche Protokollausgabe."
    )

    sub = parser.add_subparsers(dest="command")
    sub.add_parser("gui", help="Oberfläche starten (Standard).")

    check = sub.add_parser("check", help="Zutatendatenbank auf Plausibilität prüfen.")
    check.add_argument(
        "--strict",
        action="store_true",
        help="Auch Warnungen führen zu einem Exit-Code ungleich 0.",
    )

    export = sub.add_parser("export-csv", help="Zutaten als CSV schreiben.")
    export.add_argument("target", type=Path, help="Zieldatei.")

    sub.add_parser("info", help="Pfade und Bestand anzeigen.")
    return parser


def _resolve_data_dir(argument: Path | None) -> Path:
    """Ermittelt das Datenverzeichnis und legt es an."""
    if argument is None:
        return paths.data_dir()
    path = argument.expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def main(argv: list[str] | None = None) -> int:
    """Einstiegspunkt der Kommandozeile.

    Returns:
        Exit-Code: 0 bei Erfolg, 1 bei fachlichen Fehlern, 2 bei Datei- oder
        Formatfehlern.
    """
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    data_dir = _resolve_data_dir(args.data_dir)
    command = args.command or "gui"

    if command == "gui":
        from brotrechner.gui.app import run  # noqa: PLC0415 - Qt nur bei Bedarf laden

        return run(data_dir=data_dir)

    try:
        ensure_user_database(
            data_dir / paths.INGREDIENTS_FILE,
            data_dir / paths.RECIPES_FILE,
            legacy_dir=Path.cwd(),
        )
        ingredients, _ = load_ingredients(data_dir / paths.INGREDIENTS_FILE)
        recipes, _ = load_recipes(data_dir / paths.RECIPES_FILE, ingredients)
    except RepositoryError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2

    if command == "check":
        return _run_check(ingredients, strict=args.strict)
    if command == "export-csv":
        return _run_export_csv(args.target, ingredients)
    return _run_info(data_dir, len(ingredients), len(recipes))


def _run_export_csv(target: Path, ingredients: object) -> int:
    """Schreibt die Zutaten als CSV."""
    try:
        count = table.write_ingredients_csv(target, ingredients)  # type: ignore[arg-type]
    except OSError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2
    print(f"{count} Zutaten nach {target} geschrieben")
    return 0


def _run_info(data_dir: Path, ingredient_count: int, recipe_count: int) -> int:
    """Gibt Pfade und Bestand aus."""
    print(f"brotrechner {__version__}")
    print(f"Datenverzeichnis : {data_dir}")
    print(f"Sicherungen      : {paths.backup_dir(create=False)}")
    print(f"Ausgabeordner    : {paths.default_export_dir()}")
    print(f"Zutaten          : {ingredient_count}")
    print(f"Rezepte          : {recipe_count}")
    return 0


def _run_check(ingredients: object, *, strict: bool) -> int:
    """Führt die Datenprüfung aus und gibt die Befunde aus."""
    findings = validate_database(ingredients)  # type: ignore[arg-type]
    errors = [f for f in findings if f.severity is Severity.ERROR]
    warnings = [f for f in findings if f.severity is Severity.WARNING]
    infos = [f for f in findings if f.severity is Severity.INFO]

    for finding in errors + warnings:
        print(finding)

    print(
        f"\n{len(errors)} Fehler, {len(warnings)} Warnungen, {len(infos)} Hinweise "
        f"bei {len(list(ingredients))} Zutaten"  # type: ignore[call-overload]
    )
    if errors:
        return 1
    if strict and warnings:
        return 1
    return 0


def main_gui(argv: list[str] | None = None) -> int:
    """Einstiegspunkt für den Fenster-Start ohne Konsole (Windows)."""
    from brotrechner.gui.app import run  # noqa: PLC0415

    del argv
    return run(data_dir=paths.data_dir())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
