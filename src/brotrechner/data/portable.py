"""Austausch einzelner Zutaten über eigenständige JSON-Dateien.

Damit lassen sich Zutaten zwischen Rechnern weitergeben oder aus fremden
Quellen übernehmen, ohne die ganze Datenbank zu tauschen. Das Dateiformat ist
absichtlich dasselbe wie in der Hauptdatenbank, nur mit einem zusätzlichen
Feld ``kind``::

    {
      "schema_version": 2,
      "kind": "ingredient",
      "generator": "brotrechner 5.0.0",
      "ingredients": [ { "name": "Roggenvollkornmehl", "manufacturer": "Bauck", ... } ]
    }

Beim Import werden drei Formate akzeptiert:

* das obige Austauschformat (eine oder mehrere Zutaten),
* eine vollständige Datenbankdatei (Schema 2),
* eine einzelne Zutat als nacktes Objekt ``{"name": ..., ...}``.

Zusätzlich erkennt der Import Dateien im **Altformat** (deutsche Feldnamen)
und migriert sie, damit alte Exporte weiter nutzbar bleiben.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from brotrechner import __version__
from brotrechner.core.models import Ingredient
from brotrechner.data import migration
from brotrechner.data.repository import (
    SCHEMA_VERSION,
    IngredientStore,
    RepositoryError,
    read_json,
    write_json_atomic,
)

__all__ = [
    "ConflictPolicy",
    "ImportPreview",
    "ImportResult",
    "apply_import",
    "export_ingredients",
    "parse_ingredient_file",
    "preview_import",
]


class ConflictPolicy(Enum):
    """Verhalten, wenn eine importierte Zutat bereits existiert."""

    SKIP = "skip"
    """Vorhandene Zutat behalten, Import verwerfen."""

    REPLACE = "replace"
    """Vorhandene Zutat durch die importierte ersetzen."""

    KEEP_BOTH = "keep_both"
    """Beide behalten; die importierte bekommt einen Namenszusatz."""

    @property
    def label(self) -> str:
        return {
            ConflictPolicy.SKIP: "Vorhandene behalten",
            ConflictPolicy.REPLACE: "Vorhandene ersetzen",
            ConflictPolicy.KEEP_BOTH: "Beide behalten",
        }[self]


@dataclass(frozen=True, slots=True)
class ImportPreview:
    """Was ein Import bewirken würde - vor der Übernahme anzeigbar."""

    new: tuple[Ingredient, ...] = ()
    conflicting: tuple[tuple[Ingredient, Ingredient], ...] = ()
    """Paare aus (importiert, vorhanden)."""

    @property
    def total(self) -> int:
        return len(self.new) + len(self.conflicting)

    @property
    def has_conflicts(self) -> bool:
        return bool(self.conflicting)


@dataclass(slots=True)
class ImportResult:
    """Ergebnis eines durchgeführten Imports."""

    added: list[Ingredient] = field(default_factory=list)
    replaced: list[Ingredient] = field(default_factory=list)
    renamed: list[Ingredient] = field(default_factory=list)
    skipped: list[Ingredient] = field(default_factory=list)

    @property
    def changed(self) -> int:
        return len(self.added) + len(self.replaced) + len(self.renamed)

    def summary(self) -> str:
        """Einzeilige Zusammenfassung für Statusleiste und Meldungen."""
        parts = []
        if self.added:
            parts.append(f"{len(self.added)} neu")
        if self.replaced:
            parts.append(f"{len(self.replaced)} ersetzt")
        if self.renamed:
            parts.append(f"{len(self.renamed)} umbenannt übernommen")
        if self.skipped:
            parts.append(f"{len(self.skipped)} übersprungen")
        return ", ".join(parts) if parts else "keine Änderungen"


def export_ingredients(path: Path, ingredients: Sequence[Ingredient]) -> None:
    """Schreibt Zutaten in eine Austauschdatei.

    Args:
        path: Zieldatei (``.json``).
        ingredients: Zu exportierende Zutaten, mindestens eine.

    Raises:
        ValueError: Wenn keine Zutat übergeben wurde.
        RepositoryError: Wenn die Datei nicht geschrieben werden kann.
    """
    if not ingredients:
        raise ValueError("Es wurde keine Zutat zum Exportieren ausgewählt")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "ingredient",
        "generator": f"brotrechner {__version__}",
        "exported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "ingredients": [i.to_dict() for i in ingredients],
    }
    write_json_atomic(path, payload, backup=False)


def parse_ingredient_file(path: Path) -> list[Ingredient]:
    """Liest Zutaten aus einer Austausch-, Datenbank- oder Altformat-Datei.

    Args:
        path: Zu lesende Datei.

    Returns:
        Alle enthaltenen Zutaten in Dateireihenfolge.

    Raises:
        RepositoryError: Wenn die Datei unlesbar ist oder kein bekanntes
            Format hat.
    """
    raw = read_json(path)
    return _parse_payload(raw, source=path)


def _parse_payload(raw: Any, *, source: Path) -> list[Ingredient]:
    """Erkennt das Format und übersetzt es in Zutaten."""
    if isinstance(raw, list):
        return _parse_entries(raw, source=source)

    if not isinstance(raw, dict):
        raise RepositoryError(
            f"{source}: Objekt oder Liste erwartet, {type(raw).__name__} gefunden"
        )

    if migration.looks_like_legacy_ingredients(raw):
        ingredients, _ = migration.migrate_ingredients(raw)
        return ingredients

    entries = raw.get("ingredients")
    if isinstance(entries, list):
        version = raw.get("schema_version", SCHEMA_VERSION)
        if version != SCHEMA_VERSION:
            raise RepositoryError(
                f"{source}: Schemaversion {version!r} wird nicht unterstützt "
                f"(erwartet {SCHEMA_VERSION})"
            )
        return _parse_entries(entries, source=source)

    # Reihenfolge ist wesentlich: Eine einzelne Zutat im Altformat enthält
    # ebenfalls ein Feld "name". Würde zuerst darauf geprüft, liefe sie durch
    # den v2-Leser, der die deutschen Nährwertfelder nicht kennt - und die
    # Zutat käme still mit lauter Nullen an.
    if migration.LEGACY_NUTRIENT_MAP.keys() & raw.keys():  # nackte Altformat-Zutat
        return [migration.migrate_ingredient(raw)]

    if "name" in raw:  # nackte Einzelzutat im aktuellen Format
        return _parse_entries([raw], source=source)

    raise RepositoryError(f"{source}: kein erkennbares Zutatenformat")


def _parse_entries(entries: Iterable[Any], *, source: Path) -> list[Ingredient]:
    """Wandelt Rohobjekte in Zutaten; erste Fehlerstelle bricht ab."""
    ingredients: list[Ingredient] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise RepositoryError(f"{source}: Eintrag #{index} ist kein Objekt")
        try:
            ingredients.append(Ingredient.from_dict(entry))
        except ValueError as exc:
            raise RepositoryError(f"{source}: Eintrag #{index} ist fehlerhaft - {exc}") from exc
    if not ingredients:
        raise RepositoryError(f"{source}: enthält keine Zutat")
    return ingredients


def preview_import(ingredients: Sequence[Ingredient], store: IngredientStore) -> ImportPreview:
    """Ermittelt, welche Zutaten neu wären und welche kollidieren.

    Args:
        ingredients: Zu importierende Zutaten.
        store: Zieldatenbank.

    Returns:
        Vorschau ohne jede Änderung am Store.
    """
    new: list[Ingredient] = []
    conflicting: list[tuple[Ingredient, Ingredient]] = []
    for ingredient in ingredients:
        existing = store.get(ingredient.key)
        if existing is None:
            new.append(ingredient)
        else:
            conflicting.append((ingredient, existing))
    return ImportPreview(tuple(new), tuple(conflicting))


def apply_import(
    ingredients: Sequence[Ingredient],
    store: IngredientStore,
    policy: ConflictPolicy = ConflictPolicy.SKIP,
) -> ImportResult:
    """Übernimmt Zutaten in die Datenbank.

    Args:
        ingredients: Zu importierende Zutaten.
        store: Zieldatenbank; wird verändert.
        policy: Verhalten bei Namenskollisionen.

    Returns:
        Bericht darüber, was tatsächlich passiert ist.
    """
    result = ImportResult()
    for ingredient in ingredients:
        if store.get(ingredient.key) is None:
            store.add(ingredient)
            result.added.append(ingredient)
            continue

        if policy is ConflictPolicy.SKIP:
            result.skipped.append(ingredient)
        elif policy is ConflictPolicy.REPLACE:
            store.add(ingredient, replace_existing=True)
            result.replaced.append(ingredient)
        else:
            renamed = _with_unique_name(ingredient, store)
            store.add(renamed)
            result.renamed.append(renamed)
    return result


def _with_unique_name(ingredient: Ingredient, store: IngredientStore) -> Ingredient:
    """Hängt einen Zähler an, bis der Name frei ist."""
    for counter in range(2, 1000):
        candidate = ingredient.copy(name=f"{ingredient.name} ({counter})")
        if store.get(candidate.key) is None:
            return candidate
    # Praktisch unerreichbar; sicherer Ausweg mit Zeitstempel.
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return ingredient.copy(name=f"{ingredient.name} ({stamp})")
