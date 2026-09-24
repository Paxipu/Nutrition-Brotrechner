"""Persistenz der Zutaten- und Rezeptdatenbank.

Alle Schreibvorgänge sind **atomar**: Es wird in eine temporäre Datei im selben
Verzeichnis geschrieben und diese anschließend über ``os.replace`` an ihren
Platz gezogen. Ein Absturz mitten im Speichern kann so keine halbe JSON-Datei
hinterlassen - im schlimmsten Fall bleibt der vorherige Stand erhalten.

Vor jedem Überschreiben wird zusätzlich eine rotierende Sicherung angelegt.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Final

from brotrechner import __version__
from brotrechner.core.models import Ingredient, Recipe, normalize_key_part
from brotrechner.data import migration

__all__ = [
    "SCHEMA_VERSION",
    "IngredientStore",
    "LoadResult",
    "RecipeStore",
    "load_ingredients",
    "load_recipes",
    "read_json",
    "save_ingredients",
    "save_recipes",
    "write_json_atomic",
]

log = logging.getLogger(__name__)

#: Version des Dateiformats. 1 = Brot-Kalkulator v4 (deutsch, nach Namen
#: indiziert), 2 = aktuelles Format (englische Schlüssel, Liste, Hersteller).
SCHEMA_VERSION: Final = 2

#: Anzahl aufbewahrter Sicherungen je Datei.
MAX_BACKUPS: Final = 10

#: Zutatenfelder, die erst nach Version 5.1 hinzugekommen sind. Fehlen sie in
#: einem Eintrag, hat ihn ein älteres Programm geschrieben; die Datenschicht
#: kann sie dann aus der Startdatenbank ergänzen (siehe ``seed``).
TRACKED_INGREDIENT_FIELDS: Final[tuple[str, ...]] = ("flour_percent",)


class RepositoryError(RuntimeError):
    """Fehler beim Lesen oder Schreiben einer Datenbankdatei."""


@dataclass(slots=True)
class LoadResult:
    """Ergebnis eines Ladevorgangs inklusive Hinweisen aus der Migration."""

    migrated: bool = False
    """True, wenn die Datei im Altformat vorlag und übersetzt wurde."""
    notes: list[str] = field(default_factory=list)
    """Meldungen zu übersprungenen oder zusammengeführten Einträgen."""
    missing_fields: dict[str, list[str]] = field(default_factory=dict)
    """Je Feld aus :data:`TRACKED_INGREDIENT_FIELDS` die Schlüssel der
    Einträge, denen es in der Datei fehlte."""
    upgrades: list[str] = field(default_factory=list)
    """Ergänzungen aus der Startdatenbank, die der Anwender einmal sehen soll."""


# ── Container ──────────────────────────────────────────────────────────────


class IngredientStore:
    """Zutatendatenbank, indiziert nach :attr:`Ingredient.key`.

    Der Container kapselt die Schlüsselvergabe: Beim Umbenennen einer Zutat
    ändert sich ihr Schlüssel, und genau dieser Fall wurde in der Vorversion an
    mehreren Stellen einzeln - und unterschiedlich - behandelt.
    """

    def __init__(self, ingredients: Iterable[Ingredient] = ()) -> None:
        self._items: dict[str, Ingredient] = {}
        for ingredient in ingredients:
            self.add(ingredient, replace_existing=True)

    # Abbildungsprotokoll
    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[Ingredient]:
        return iter(self._items.values())

    def __contains__(self, key: object) -> bool:
        return str(key) in self._items

    def __getitem__(self, key: str) -> Ingredient:
        return self._items[key]

    def get(self, key: str, default: Ingredient | None = None) -> Ingredient | None:
        """Zutat nach Schlüssel, oder ``default``."""
        return self._items.get(key, default)

    def as_dict(self) -> dict[str, Ingredient]:
        """Flache Kopie der Schlüssel→Zutat-Abbildung."""
        return dict(self._items)

    def sorted(self) -> list[Ingredient]:
        """Alle Zutaten, alphabetisch nach Anzeigename."""
        return sorted(self._items.values(), key=lambda i: i.display_name.casefold())

    # Änderungen
    def add(self, ingredient: Ingredient, *, replace_existing: bool = False) -> None:
        """Fügt eine Zutat ein.

        Raises:
            KeyError: Wenn der Schlüssel belegt ist und ``replace_existing``
                nicht gesetzt wurde.
        """
        key = ingredient.key
        if key in self._items and not replace_existing:
            raise KeyError(f"Zutat {ingredient.display_name!r} existiert bereits")
        self._items[key] = ingredient

    def remove(self, key: str) -> Ingredient:
        """Entfernt eine Zutat und gibt sie zurück.

        Raises:
            KeyError: Wenn der Schlüssel unbekannt ist.
        """
        return self._items.pop(key)

    def replace(self, old_key: str, ingredient: Ingredient) -> None:
        """Ersetzt eine Zutat und berücksichtigt einen geänderten Schlüssel.

        Raises:
            KeyError: Wenn der neue Schlüssel bereits von einer *anderen*
                Zutat belegt ist.
        """
        new_key = ingredient.key
        if new_key != old_key and new_key in self._items:
            raise KeyError(f"Zutat {ingredient.display_name!r} existiert bereits")
        self._items.pop(old_key, None)
        self._items[new_key] = ingredient

    def find_by_name(self, name: str, manufacturer: str = "") -> Ingredient | None:
        """Sucht über Name und Hersteller statt über den fertigen Schlüssel."""
        return self._items.get(f"{normalize_key_part(name)}|{normalize_key_part(manufacturer)}")

    @property
    def manufacturers(self) -> list[str]:
        """Alle vorkommenden Hersteller, alphabetisch, ohne Leereintrag."""
        return sorted({i.manufacturer for i in self._items.values() if i.manufacturer})


class RecipeStore:
    """Rezeptdatenbank, indiziert nach dem Rezeptnamen (normalisiert)."""

    def __init__(self, recipes: Iterable[Recipe] = ()) -> None:
        self._items: dict[str, Recipe] = {}
        for recipe in recipes:
            self.add(recipe, replace_existing=True)

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[Recipe]:
        return iter(self._items.values())

    def __contains__(self, name: object) -> bool:
        return normalize_key_part(str(name)) in self._items

    def get(self, name: str) -> Recipe | None:
        """Rezept nach Name (Groß-/Kleinschreibung egal)."""
        return self._items.get(normalize_key_part(name))

    def add(self, recipe: Recipe, *, replace_existing: bool = False) -> None:
        """Fügt ein Rezept ein.

        Raises:
            KeyError: Wenn der Name belegt ist und nicht überschrieben werden darf.
        """
        key = normalize_key_part(recipe.name)
        if key in self._items and not replace_existing:
            raise KeyError(f"Rezept {recipe.name!r} existiert bereits")
        self._items[key] = recipe

    def remove(self, name: str) -> Recipe:
        """Entfernt ein Rezept.

        Raises:
            KeyError: Wenn der Name unbekannt ist.
        """
        return self._items.pop(normalize_key_part(name))

    def sorted_by_date(self) -> list[Recipe]:
        """Rezepte, neueste zuerst."""
        return sorted(self._items.values(), key=lambda r: r.created_at, reverse=True)

    def sorted_by_name(self) -> list[Recipe]:
        return sorted(self._items.values(), key=lambda r: r.name.casefold())


# ── Datei-Ein-/Ausgabe ─────────────────────────────────────────────────────


def read_json(path: Path) -> Any:
    """Liest eine JSON-Datei.

    Raises:
        RepositoryError: Bei Lese- oder Syntaxfehlern - mit Angabe der Zeile,
            damit sich eine kaputte Datei von Hand reparieren lässt.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RepositoryError(f"{path} konnte nicht gelesen werden: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RepositoryError(
            f"{path} ist kein gültiges JSON (Zeile {exc.lineno}, Spalte {exc.colno}): {exc.msg}"
        ) from exc
    except RecursionError as exc:
        # Eine Datei mit zehntausenden verschachtelten Klammern bringt den
        # JSON-Leser an die Rekursionsgrenze. Beim Import fremder Dateien darf
        # das eine Fehlermeldung geben, aber nicht das Programm beenden.
        raise RepositoryError(
            f"{path} ist zu tief verschachtelt und wurde nicht eingelesen"
        ) from exc


def write_json_atomic(path: Path, payload: Any, *, backup: bool = True) -> None:
    """Schreibt JSON atomar und legt vorher eine Sicherung an.

    Args:
        path: Zieldatei.
        payload: JSON-serialisierbares Objekt.
        backup: Vorherigen Stand sichern, falls die Datei existiert.

    Raises:
        RepositoryError: Wenn das Schreiben fehlschlägt.
    """
    tmp_path: Path | None = None
    try:
        # Auch das Anlegen des Verzeichnisses gehört in die Fehlerbehandlung:
        # Liegt an der Stelle des Ordners bereits eine Datei, meldet mkdir einen
        # OSError, der sonst ungekapselt bis in die Oberfläche durchschlüge.
        path.parent.mkdir(parents=True, exist_ok=True)
        if backup and path.exists():
            _rotate_backup(path)

        # Temporärdatei im Zielverzeichnis, damit das abschließende Ersetzen
        # nicht über Dateisystemgrenzen hinweg arbeiten muss - dort wäre es
        # nicht atomar.
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        tmp_path = Path(tmp_name)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        tmp_path.replace(path)
        tmp_path = None
    except OSError as exc:
        raise RepositoryError(f"{path} konnte nicht geschrieben werden: {exc}") from exc
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def _rotate_backup(path: Path) -> None:
    """Legt eine Sicherung an und hält nur die jüngsten :data:`MAX_BACKUPS`.

    Die Sicherungen liegen in ``backups`` **neben** der gesicherten Datei, nicht
    in einem festen Verzeichnis. Damit stimmt der Ablageort auch dann, wenn das
    Programm mit ``--data-dir`` auf ein anderes Verzeichnis gerichtet wurde.
    """
    try:
        target_dir = path.parent / "backups"
        target_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(path, target_dir / f"{path.stem}_{stamp}{path.suffix}")

        existing = sorted(target_dir.glob(f"{path.stem}_*{path.suffix}"))
        for stale in existing[:-MAX_BACKUPS]:
            stale.unlink(missing_ok=True)
    except OSError as exc:
        # Eine fehlgeschlagene Sicherung darf das Speichern nicht verhindern.
        log.warning("Sicherung von %s fehlgeschlagen: %s", path, exc)


# ── Zutaten ────────────────────────────────────────────────────────────────


def load_ingredients(path: Path) -> tuple[IngredientStore, LoadResult]:
    """Lädt die Zutatendatenbank und migriert bei Bedarf.

    Args:
        path: Pfad der Datei. Existiert sie nicht, wird ein leerer Store
            zurückgegeben.

    Returns:
        Tupel aus Store und Ladebericht.

    Raises:
        RepositoryError: Bei defekter Datei oder unbekannter Schemaversion.
    """
    result = LoadResult()
    if not path.exists():
        return IngredientStore(), result

    raw = read_json(path)

    if migration.looks_like_legacy_ingredients(raw):
        ingredients, notes = migration.migrate_ingredients(raw)
        result.migrated = True
        result.notes = notes
        return IngredientStore(ingredients), result

    if not isinstance(raw, dict):
        raise RepositoryError(f"{path}: Objekt erwartet, {type(raw).__name__} gefunden")

    version = raw.get("schema_version")
    if version != SCHEMA_VERSION:
        raise RepositoryError(
            f"{path}: Schemaversion {version!r} wird nicht unterstützt (erwartet {SCHEMA_VERSION})"
        )

    entries = raw.get("ingredients")
    if not isinstance(entries, list):
        raise RepositoryError(f"{path}: Feld 'ingredients' fehlt oder ist keine Liste")

    ingredients = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            result.notes.append(f"Eintrag #{index} übersprungen: kein Objekt")
            continue
        try:
            ingredient = Ingredient.from_dict(entry)
        except ValueError as exc:
            result.notes.append(f"Eintrag #{index} übersprungen: {exc}")
            continue
        ingredients.append(ingredient)
        for name in TRACKED_INGREDIENT_FIELDS:
            if name not in entry:
                result.missing_fields.setdefault(name, []).append(ingredient.key)

    return IngredientStore(ingredients), result


def save_ingredients(path: Path, store: IngredientStore) -> None:
    """Speichert die Zutatendatenbank atomar."""
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generator": f"brotrechner {__version__}",
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "ingredients": [i.to_dict() for i in store.sorted()],
    }
    write_json_atomic(path, payload)


# ── Rezepte ────────────────────────────────────────────────────────────────


def load_recipes(path: Path, ingredients: IngredientStore) -> tuple[RecipeStore, LoadResult]:
    """Lädt die Rezeptdatenbank und migriert bei Bedarf.

    Args:
        path: Pfad der Datei.
        ingredients: Zutatendatenbank; wird nur für die Migration der
            Zutatenverweise gebraucht.

    Returns:
        Tupel aus Store und Ladebericht.

    Raises:
        RepositoryError: Bei defekter Datei oder unbekannter Schemaversion.
    """
    result = LoadResult()
    if not path.exists():
        return RecipeStore(), result

    raw = read_json(path)

    if migration.looks_like_legacy_recipes(raw):
        recipes, notes = migration.migrate_recipes(raw, ingredients.as_dict())
        result.migrated = True
        result.notes = notes
        return RecipeStore(recipes), result

    if not isinstance(raw, dict):
        raise RepositoryError(f"{path}: Objekt erwartet, {type(raw).__name__} gefunden")

    version = raw.get("schema_version")
    if version != SCHEMA_VERSION:
        raise RepositoryError(
            f"{path}: Schemaversion {version!r} wird nicht unterstützt (erwartet {SCHEMA_VERSION})"
        )

    entries = raw.get("recipes")
    if not isinstance(entries, list):
        raise RepositoryError(f"{path}: Feld 'recipes' fehlt oder ist keine Liste")

    recipes = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            result.notes.append(f"Eintrag #{index} übersprungen: kein Objekt")
            continue
        try:
            recipes.append(Recipe.from_dict(entry))
        except ValueError as exc:
            result.notes.append(f"Eintrag #{index} übersprungen: {exc}")

    return RecipeStore(recipes), result


def save_recipes(path: Path, store: RecipeStore) -> None:
    """Speichert die Rezeptdatenbank atomar."""
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generator": f"brotrechner {__version__}",
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "recipes": [r.to_dict() for r in store.sorted_by_date()],
    }
    write_json_atomic(path, payload)
