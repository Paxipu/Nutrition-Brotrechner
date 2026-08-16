"""Migration des Altformats (Brot-Kalkulator v4) auf das aktuelle Schema.

Das Altformat war ein Dict, das nach dem Zutatennamen indiziert war und
deutsche Feldnamen verwendete. Der Hersteller steckte als Klammerzusatz im
Namen (``"Roggenvollkornmehl (Bauck)"``), Mehl wurde über Namens-Schlüsselwörter
erraten.

Diese Migration
    * übersetzt die Feldnamen,
    * zieht bekannte Hersteller aus dem Namen in ein eigenes Feld,
    * setzt :attr:`~brotrechner.core.models.Ingredient.is_flour` einmalig
      anhand derselben Heuristik wie früher, damit sich das Verhalten
      bestehender Rezepte nicht ändert,
    * und führt Zutaten zusammen, die sich nur in Groß-/Kleinschreibung
      unterscheiden.

Die Migration ist verlustfrei bezogen auf alle Werte, die das Altformat
tatsächlich gespeichert hat.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Final

from brotrechner.core.models import (
    Category,
    Ingredient,
    PriceEntry,
    Recipe,
    RecipeItem,
    Source,
    as_aware,
    normalize_key_part,
)
from brotrechner.core.nutrients import Nutrients
from brotrechner.core.validation import KNOWN_MANUFACTURERS

__all__ = [
    "LEGACY_CATEGORY_MAP",
    "LEGACY_NUTRIENT_MAP",
    "looks_like_legacy_ingredients",
    "looks_like_legacy_recipes",
    "migrate_ingredient",
    "migrate_ingredients",
    "migrate_recipes",
    "split_manufacturer",
]

#: Altes deutsches Feld → neues Feld im Nährwertvektor.
LEGACY_NUTRIENT_MAP: Final[dict[str, str]] = {
    "kalorien": "energy_kcal",
    "fett": "fat",
    "fett_gesaettigt": "saturated_fat",
    "kohlenhydrate": "carbs",
    "zucker": "sugar",
    "eiweiss": "protein",
    "salz": "salt",
    "ballaststoffe": "fiber",
    "wassergehalt": "water",
}

#: Alte Kategoriebezeichnung → Kategorie.
LEGACY_CATEGORY_MAP: Final[dict[str, Category]] = {
    "mehl": Category.FLOUR,
    "saaten & kerne": Category.SEEDS_NUTS,
    "getreide & flocken": Category.GRAINS,
    "triebmittel": Category.LEAVENING,
    "grundzutaten": Category.BASICS,
    "fette & öle": Category.FATS_OILS,
    "milchprodukte": Category.DAIRY,
    "gewürze": Category.SPICES,
    "sonstiges": Category.OTHER,
}

#: Schlüsselwörter der alten Mehl-Heuristik. Sie wird ausschließlich bei der
#: Migration angewandt; danach steht das Ergebnis als Feld in den Daten.
_LEGACY_FLOUR_KEYWORDS: Final = ("mehl", "stärke", "kartoffelstärke")

#: Zutaten, die die alte Heuristik fälschlich als Mehl erkannt hat: Paniermehl
#: ist bereits gebackenes Brot und gehört im Bäckerprozent nicht zur Mehlmenge.
#: Leinmehl und Sojamehl bleiben bewusst Mehl - dort ist die Zuordnung eine
#: Ermessensfrage, und das bisherige Verhalten soll sich nicht ändern. Über das
#: Feld ``is_flour`` lässt sich das jederzeit einzeln umstellen.
_NOT_FLOUR_OVERRIDES: Final = (
    "altbrot",
    "paniermehl",
)

_PARENTHESES = re.compile(r"\s*\(([^()]*)\)\s*")


def split_manufacturer(raw_name: str) -> tuple[str, str]:
    """Trennt einen bekannten Hersteller vom Zutatennamen.

    Nur Klammerzusätze, die einem Eintrag aus
    :data:`~brotrechner.core.validation.KNOWN_MANUFACTURERS` entsprechen, werden
    abgetrennt. Fachliche Zusätze wie ``"(blau)"``, ``"(frisch)"`` oder
    ``"(natur, 3,5%)"`` bleiben damit unangetastet.

    Args:
        raw_name: Zutatenname aus dem Altformat.

    Returns:
        Tupel ``(name, hersteller)``; ``hersteller`` ist leer, wenn keiner
        erkannt wurde.

    Examples:
        >>> split_manufacturer("Roggenvollkornmehl (Bauck)")
        ('Roggenvollkornmehl', 'Bauck')
        >>> split_manufacturer("Hafer (ganz)(dm)")
        ('Hafer (ganz)', 'dm')
        >>> split_manufacturer("Mohn (blau)")
        ('Mohn (blau)', '')
    """
    manufacturer = ""
    name = raw_name

    for match in reversed(list(_PARENTHESES.finditer(raw_name))):
        content = match.group(1).strip()
        hit = next(
            (m for m in KNOWN_MANUFACTURERS if m.casefold() == content.casefold()),
            None,
        )
        if hit is not None:
            manufacturer = hit
            name = (raw_name[: match.start()] + " " + raw_name[match.end() :]).strip()
            break

    return " ".join(name.split()), manufacturer


def _legacy_is_flour(name: str, category: Category) -> bool:
    """Reproduziert die alte Mehl-Heuristik, korrigiert um klare Fehlgriffe."""
    lowered = name.casefold()
    if any(token in lowered for token in _NOT_FLOUR_OVERRIDES):
        return False
    return category is Category.FLOUR or any(kw in lowered for kw in _LEGACY_FLOUR_KEYWORDS)


def migrate_ingredient(raw: dict[str, Any], *, fallback_name: str = "") -> Ingredient:
    """Übersetzt einen Zutateneintrag des Altformats.

    Args:
        raw: Eintrag aus ``brot_zutaten.json``.
        fallback_name: Name aus dem Dict-Schlüssel, falls im Eintrag keiner steht.

    Returns:
        Migrierte Zutat.

    Raises:
        ValueError: Wenn weder Eintrag noch Schlüssel einen Namen liefern.
    """
    raw_name = str(raw.get("name") or fallback_name or "").strip()
    if not raw_name:
        raise ValueError("Zutat ohne Namen im Altformat")

    name, manufacturer = split_manufacturer(raw_name)
    category = LEGACY_CATEGORY_MAP.get(
        str(raw.get("kategorie") or "").strip().casefold(), Category.OTHER
    )
    nutrients = Nutrients.from_dict(
        {new: raw.get(old, 0.0) for old, new in LEGACY_NUTRIENT_MAP.items()}
    )

    history = [
        PriceEntry(
            recorded_at=_parse_legacy_datetime(entry.get("datum")),
            package_price=float(entry.get("preis") or 0.0),
            package_size_g=float(entry.get("groesse") or 0.0),
        )
        for entry in raw.get("preis_historie") or []
    ]

    return Ingredient(
        name=name,
        manufacturer=manufacturer,
        category=category,
        nutrients=nutrients,
        is_flour=_legacy_is_flour(raw_name, category),
        package_price=float(raw.get("preis_pro_packung") or 0.0),
        package_size_g=float(raw.get("packungsgroesse") or 0.0),
        price_history=history,
        nutrition_source=Source.LABEL if manufacturer else Source.REFERENCE,
        water_source=Source.ESTIMATED,
    )


def migrate_ingredients(raw: dict[str, Any]) -> tuple[list[Ingredient], list[str]]:
    """Migriert eine komplette Zutatendatei des Altformats.

    Zutaten, deren Schlüssel nach der Normalisierung zusammenfällt (also reine
    Groß-/Kleinschreibungs-Dubletten), werden zusammengeführt. Der Eintrag mit
    den meisten gesetzten Feldern gewinnt.

    Args:
        raw: Inhalt von ``brot_zutaten.json``.

    Returns:
        Tupel aus Zutatenliste und einer Liste von Hinweistexten zu
        zusammengeführten oder übersprungenen Einträgen.
    """
    by_key: dict[str, Ingredient] = {}
    notes: list[str] = []

    for raw_key, entry in raw.items():
        if not isinstance(entry, dict):
            notes.append(f"Eintrag {raw_key!r} übersprungen: kein Objekt")
            continue
        try:
            ingredient = migrate_ingredient(entry, fallback_name=str(raw_key))
        except ValueError as exc:
            notes.append(f"Eintrag {raw_key!r} übersprungen: {exc}")
            continue

        existing = by_key.get(ingredient.key)
        if existing is None:
            by_key[ingredient.key] = ingredient
            continue

        notes.append(
            f"{ingredient.display_name!r} und {existing.display_name!r} zusammengeführt "
            f"(unterscheiden sich nur in der Schreibweise)"
        )
        if _completeness(ingredient) > _completeness(existing):
            by_key[ingredient.key] = ingredient

    return list(by_key.values()), notes


def _completeness(ingredient: Ingredient) -> int:
    """Zählt gesetzte Felder - Entscheidungshilfe beim Zusammenführen."""
    n = ingredient.nutrients
    score = sum(1 for f in n.to_dict().values() if f)
    if ingredient.has_price:
        score += 2
    if ingredient.notes:
        score += 1
    return score


def migrate_recipes(
    raw: dict[str, Any],
    ingredients: dict[str, Ingredient],
) -> tuple[list[Recipe], list[str]]:
    """Migriert die Rezeptdatei des Altformats.

    Rezeptzeilen verwiesen früher über den vollen Namen inklusive Hersteller-
    Klammer auf die Zutat. Hier wird derselbe Namensabgleich vorgenommen wie
    bei den Zutaten, damit die Verweise erhalten bleiben.

    Args:
        raw: Inhalt von ``brot_rezepte.json``.
        ingredients: Bereits migrierte Zutaten, indiziert nach Schlüssel.

    Returns:
        Tupel aus Rezeptliste und Hinweistexten zu nicht auflösbaren Zutaten.
    """
    recipes: list[Recipe] = []
    notes: list[str] = []

    for raw_key, entry in raw.items():
        if not isinstance(entry, dict):
            notes.append(f"Rezept {raw_key!r} übersprungen: kein Objekt")
            continue

        name = str(entry.get("name") or raw_key).strip()
        items: list[RecipeItem] = []
        for pair in entry.get("zutaten") or []:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                notes.append(f"Rezept {name!r}: Zutatenzeile {pair!r} übersprungen")
                continue
            raw_ingredient_name, amount = pair
            item_name, manufacturer = split_manufacturer(str(raw_ingredient_name))
            key = f"{normalize_key_part(item_name)}|{normalize_key_part(manufacturer)}"
            if key not in ingredients:
                notes.append(
                    f"Rezept {name!r}: Zutat {raw_ingredient_name!r} nicht in der Datenbank"
                )
            items.append(
                RecipeItem(
                    ingredient_key=key,
                    name=item_name,
                    manufacturer=manufacturer,
                    amount_g=float(amount or 0.0),
                )
            )

        created = _parse_legacy_datetime(entry.get("erstellt_am"))
        recipes.append(
            Recipe(
                name=name,
                items=items,
                baked_weight_g=float(entry.get("gewicht_gebacken") or 0.0),
                dough_weight_g=float(entry.get("gewicht_rohteig") or 0.0),
                energy_kwh=float(entry.get("energie_kwh") or 0.0),
                notes=str(entry.get("notizen") or ""),
                created_at=created,
                modified_at=created,
            )
        )

    return recipes, notes


def looks_like_legacy_ingredients(raw: object) -> bool:
    """Erkennt eine Zutatendatei im Altformat."""
    if not isinstance(raw, dict) or "schema_version" in raw:
        return False
    return any(isinstance(v, dict) and ("kalorien" in v or "kategorie" in v) for v in raw.values())


def looks_like_legacy_recipes(raw: object) -> bool:
    """Erkennt eine Rezeptdatei im Altformat."""
    if not isinstance(raw, dict) or "schema_version" in raw:
        return False
    return any(isinstance(v, dict) and "zutaten" in v for v in raw.values())


def _parse_legacy_datetime(value: object) -> datetime:
    """Liest einen ISO-Zeitstempel des Altformats als zonenbehaftete Zeit.

    Das Altprogramm schrieb Zeitstempel ohne Zonenangabe. Sie werden hier als
    lokale Zeit gedeutet, damit sie sich mit neu entstandenen Einträgen
    vergleichen lassen.
    """
    if isinstance(value, str) and value:
        try:
            return as_aware(datetime.fromisoformat(value))
        except ValueError:
            pass
    return datetime.now(timezone.utc)
