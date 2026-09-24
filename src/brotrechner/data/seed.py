"""Mitgelieferte Startdatenbank und Erstbefüllung des Nutzerverzeichnisses.

Beim ersten Start existiert im Nutzerverzeichnis noch keine Datenbank. Dann
greift folgende Reihenfolge:

1. Liegen im angegebenen Verzeichnis (üblicherweise dort, wo das alte
   Einzelskript lief) Dateien im Altformat, werden diese **migriert**. Damit
   geht keine selbst gepflegte Zutat verloren.
2. Andernfalls wird die mitgelieferte, geprüfte Startdatenbank kopiert.

Die Startdatenbank liegt als Paketressource unter ``data/seed/ingredients.json``
und wird beim Programmupdate mitgeliefert; die Nutzerdatenbank bleibt davon
unberührt.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from brotrechner.core.models import Ingredient
from brotrechner.data.repository import (
    IngredientStore,
    LoadResult,
    RecipeStore,
    RepositoryError,
    load_ingredients,
    load_recipes,
    save_ingredients,
    save_recipes,
)

__all__ = [
    "SeedResult",
    "ensure_user_database",
    "load_seed_ingredients",
    "load_user_ingredients",
    "seed_path",
    "upgrade_from_seed",
]

log = logging.getLogger(__name__)

#: Dateinamen des Altformats, die bei der Erstbefüllung gesucht werden.
LEGACY_INGREDIENTS_NAME = "brot_zutaten.json"
LEGACY_RECIPES_NAME = "brot_rezepte.json"


@dataclass(slots=True)
class SeedResult:
    """Bericht über die Erstbefüllung."""

    created_ingredients: bool = False
    created_recipes: bool = False
    imported_from_legacy: bool = False
    notes: list[str] = field(default_factory=list)


def seed_path() -> Path:
    """Pfad der mitgelieferten Startdatenbank innerhalb des Pakets."""
    return Path(str(resources.files("brotrechner.data") / "seed" / "ingredients.json"))


def load_seed_ingredients() -> IngredientStore:
    """Lädt die mitgelieferte Startdatenbank.

    Raises:
        RepositoryError: Wenn die Paketressource fehlt oder defekt ist -
            das wäre ein Installationsfehler und darf nicht stillschweigend
            zu einer leeren Datenbank führen.
    """
    path = seed_path()
    if not path.exists():
        raise RepositoryError(f"Mitgelieferte Startdatenbank fehlt: {path}")
    store, _ = load_ingredients(path)
    return store


def ensure_user_database(
    ingredients_file: Path,
    recipes_file: Path,
    *,
    legacy_dir: Path | None = None,
) -> SeedResult:
    """Legt fehlende Nutzerdateien an - aus dem Altbestand oder aus der Startdatenbank.

    Args:
        ingredients_file: Zielpfad der Zutatendatenbank.
        recipes_file: Zielpfad der Rezeptdatenbank.
        legacy_dir: Verzeichnis, in dem nach Dateien im Altformat gesucht wird.
            ``None`` überspringt die Altdatenübernahme.

    Returns:
        Bericht darüber, was angelegt wurde.
    """
    result = SeedResult()
    legacy_ingredients = legacy_dir / LEGACY_INGREDIENTS_NAME if legacy_dir else None
    legacy_recipes = legacy_dir / LEGACY_RECIPES_NAME if legacy_dir else None

    store: IngredientStore | None = None

    if not ingredients_file.exists():
        if legacy_ingredients and legacy_ingredients.exists():
            store, load_result = load_ingredients(legacy_ingredients)
            result.imported_from_legacy = True
            result.notes.extend(load_result.notes)
            result.notes.append(f"{len(store)} Zutaten aus {legacy_ingredients.name} übernommen")
            result.notes.extend(merge_seed_into(store))
        else:
            store = load_seed_ingredients()
            result.notes.append(f"{len(store)} Zutaten aus der Startdatenbank übernommen")
        save_ingredients(ingredients_file, store)
        result.created_ingredients = True

    if not recipes_file.exists():
        recipes = RecipeStore()
        if legacy_recipes and legacy_recipes.exists():
            if store is None:
                store, _ = load_ingredients(ingredients_file)
            recipes, load_result = load_recipes(legacy_recipes, store)
            result.imported_from_legacy = True
            result.notes.extend(load_result.notes)
            result.notes.append(f"{len(recipes)} Rezepte aus {legacy_recipes.name} übernommen")
        save_recipes(recipes_file, recipes)
        result.created_recipes = True

    return result


def load_user_ingredients(path: Path) -> tuple[IngredientStore, LoadResult]:
    """Lädt die Zutatendatenbank des Anwenders und bringt sie auf den neuen Stand.

    Felder, die ein älteres Programm noch nicht kannte, werden dabei aus der
    Startdatenbank ergänzt (:func:`upgrade_from_seed`) und sofort gespeichert,
    damit die Ergänzung nur ein einziges Mal geschieht. Scheitert dieses
    Speichern, wird trotzdem mit den ergänzten Daten weitergearbeitet: Ein
    schreibgeschütztes Verzeichnis soll das Laden nicht verhindern.

    Args:
        path: Zutatendatei des Anwenders.

    Returns:
        Tupel aus Store und Ladebericht; die Ergänzungen stehen in dessen
        ``upgrades``.

    Raises:
        RepositoryError: Wenn die Datei selbst nicht lesbar ist.
    """
    store, result = load_ingredients(path)
    upgrades = upgrade_from_seed(store, result.missing_fields)
    if upgrades:
        result.upgrades.extend(upgrades)
        try:
            save_ingredients(path, store)
        except RepositoryError as exc:
            log.warning("Ergänzte Zutatendatenbank nicht gespeichert: %s", exc)
            result.upgrades.append(f"Die Ergänzungen konnten nicht gespeichert werden: {exc}")
    return store, result


def upgrade_from_seed(store: IngredientStore, missing_fields: dict[str, list[str]]) -> list[str]:
    """Ergänzt Felder, die ältere Programmfassungen nicht kannten.

    Bis Version 5.1 gab es keinen Mehlanteil, nur "Mehl ja/nein". Ein
    Anstellgut stand deshalb mit 0 % in der Datei. Für Zutaten, die es in der
    Startdatenbank mit einem Mehlanteil zwischen 0 und 100 % gibt - also
    Sauerteige und Vorteige -, wird dieser übernommen. Alles andere bleibt,
    wie es war; insbesondere ein ausdrücklich gespeicherter Anteil.

    Args:
        store: Zutatendatenbank, die verändert wird.
        missing_fields: Aus :attr:`LoadResult.missing_fields`.

    Returns:
        Beschreibung der Ergänzungen, leer wenn nichts zu tun war.
    """
    keys = missing_fields.get("flour_percent", [])
    if not keys:
        return []
    try:
        seed = load_seed_ingredients()
    except RepositoryError as exc:  # pragma: no cover - Installationsfehler
        log.warning("Startdatenbank nicht lesbar: %s", exc)
        return []

    adopted = []
    for key in keys:
        own = store.get(key)
        reference = seed.get(key)
        if own is not None and reference is not None and _adopt_flour_share(own, reference):
            adopted.append(own.display_name)
    if not adopted:
        return []
    return [
        "Mehlanteil von Sauerteigen und Vorteigen aus der Startdatenbank ergänzt: "
        + ", ".join(sorted(adopted))
    ]


def _adopt_flour_share(own: Ingredient, reference: Ingredient) -> bool:
    """Übernimmt den Mehlanteil eines Vorteigs, wenn die eigene Zutat keinen hat.

    Returns:
        True, wenn etwas geändert wurde.
    """
    if own.flour_percent == 0.0 and 0.0 < reference.flour_percent < 100.0:
        own.flour_percent = reference.flour_percent
        return True
    return False


def _looks_unedited(ingredient: Ingredient) -> bool:
    """Schätzt ein, ob eine Zutat je von Hand angefasst wurde.

    Die Vorgängerversion lieferte ihre Zutaten ohne Preis und ohne Notiz aus.
    Wer eine Zutat wirklich gepflegt hat, hat mindestens eines von beidem
    ausgefüllt oder eine Preisänderung ausgelöst. Fehlt alles davon, handelt es
    sich mit hoher Wahrscheinlichkeit um einen unberührten Vorgabewert.
    """
    return not ingredient.has_price and not ingredient.notes and not ingredient.price_history


def merge_seed_into(store: IngredientStore) -> list[str]:
    """Ergänzt übernommene Altdaten aus der geprüften Startdatenbank.

    Die Altversion kannte kein Preisfeld und enthielt Nährwerte, die der
    Massenbilanz widersprechen. Beim einmaligen Übernehmen wird deshalb
    ergänzt - nach drei ausdrücklichen Regeln, damit selbst gepflegte Werte
    keinesfalls verloren gehen:

    1. **Unberührte Zutaten** (kein Preis, keine Notiz, keine Preishistorie)
       gelten als Vorgabewerte der Altversion und werden vollständig durch den
       geprüften Eintrag ersetzt.
    2. **Selbst gepflegte Zutaten** behalten ihre Nährwerte. Nur wenn sie die
       Plausibilitätsprüfung nicht bestehen und der Referenzeintrag sauber ist,
       werden die Nährwerte korrigiert.
    3. **Preise** werden ausschließlich dort eingetragen, wo bisher keiner
       stand. Ein selbst erfasster Preis wird nie überschrieben.
    4. **Mehlanteil**: Das Altprogramm kannte ihn nicht. Sauerteige und
       Vorteige bekommen den Anteil der Startdatenbank.

    Zutaten, die es in der Startdatenbank nicht gibt, bleiben unangetastet.

    Args:
        store: Zutatendatenbank, die verändert wird.

    Returns:
        Beschreibung der vorgenommenen Änderungen für die Anzeige beim ersten
        Start.
    """
    try:
        seed = load_seed_ingredients()
    except RepositoryError as exc:  # pragma: no cover - Installationsfehler
        log.warning("Startdatenbank nicht lesbar: %s", exc)
        return []

    # Lokaler Import: validation gehört zur Fachlogik und soll nicht am
    # Modulkopf der Persistenzschicht stehen.
    from brotrechner.core.validation import Severity, validate_ingredient  # noqa: PLC0415

    def has_problem(ingredient: Ingredient) -> bool:
        return any(f.severity is not Severity.INFO for f in validate_ingredient(ingredient))

    notes: list[str] = []
    adopted: list[str] = []
    corrections: list[str] = []
    prices = 0
    flour_shares = 0

    for reference in seed:
        own = store.get(reference.key)
        if own is None:
            continue

        if _looks_unedited(own):
            store.add(
                reference.copy(name=own.name, manufacturer=own.manufacturer), replace_existing=True
            )
            adopted.append(own.display_name)
            continue

        if not own.has_price and reference.has_price:
            own.package_price = reference.package_price
            own.package_size_g = reference.package_size_g
            own.price_source = reference.price_source
            own.price_updated = reference.price_updated
            prices += 1

        if has_problem(own) and not has_problem(reference):
            own.nutrients = reference.nutrients
            own.notes = reference.notes
            own.nutrition_source = reference.nutrition_source
            corrections.append(own.display_name)

        if _adopt_flour_share(own, reference):
            flour_shares += 1

    if adopted:
        notes.append(
            f"{len(adopted)} unveränderte Zutaten durch die geprüfte Fassung mit "
            f"korrigierten Nährwerten und aktuellen Preisen ersetzt"
        )
    if prices:
        notes.append(f"Preise für {prices} weitere Zutaten ergänzt")
    if flour_shares:
        notes.append(f"Mehlanteil von Sauerteigen und Vorteigen ergänzt ({flour_shares})")
    if corrections:
        notes.append(
            f"Nährwerte von {len(corrections)} selbst gepflegten Zutaten korrigiert, weil "
            f"sie die Plausibilitätsprüfung nicht bestanden: " + ", ".join(sorted(corrections))
        )
    return notes


def missing_from_seed(store: IngredientStore) -> list[Ingredient]:
    """Zutaten der Startdatenbank, die in ``store`` fehlen.

    Damit lässt sich eine gewachsene Nutzerdatenbank nachträglich um neue
    Standardzutaten ergänzen, ohne eigene Einträge zu überschreiben.
    """
    try:
        seed = load_seed_ingredients()
    except RepositoryError as exc:  # pragma: no cover - Installationsfehler
        log.warning("Startdatenbank nicht lesbar: %s", exc)
        return []
    return [ingredient for ingredient in seed if ingredient.key not in store]
