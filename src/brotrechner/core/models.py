"""Datenmodell: Kategorien, Zutaten und Rezepte.

Zentrale Designentscheidung gegenüber der Vorgängerversion: Der **Hersteller
ist ein eigenes Feld**. Früher steckte er im Namen (``"Roggenvollkornmehl
(Bauck)"``), wodurch sich weder nach Hersteller filtern noch derselbe Artikel
verschiedener Hersteller sauber vergleichen ließ. Die Identität einer Zutat ist
jetzt das Paar ``(name, manufacturer)``; :attr:`Ingredient.key` bildet das auf
einen stabilen, normalisierten Schlüssel ab.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Final

from brotrechner.core.nutrients import Nutrients

__all__ = [
    "CATEGORY_LABELS",
    "Category",
    "Ingredient",
    "PriceEntry",
    "Recipe",
    "RecipeItem",
    "Source",
    "as_aware",
    "normalize_key_part",
]


class Category(Enum):
    """Zutatenkategorie. Der Wert ist der stabile Schlüssel in der JSON-Datei.

    Bewusst **keine** Ableitung von ``str``: PySide6 reicht ``str``-Enums beim
    Weg durch ``QVariant`` (etwa ``QComboBox.currentData``) als nackte
    Zeichenkette zurück, wodurch Identitätsvergleiche stillschweigend
    fehlschlagen würden.
    """

    FLOUR = "flour"
    GRAINS = "grains"
    SEEDS_NUTS = "seeds_nuts"
    LEAVENING = "leavening"
    BASICS = "basics"
    FATS_OILS = "fats_oils"
    DAIRY = "dairy"
    SPICES = "spices"
    OTHER = "other"

    @classmethod
    def parse(cls, value: object) -> Category:
        """Liest eine Kategorie aus Schlüssel *oder* deutscher Anzeige-Bezeichnung."""
        if isinstance(value, cls):
            return value
        text = str(value or "").strip()
        for member in cls:
            if text == member.value:
                return member
        for member, label in CATEGORY_LABELS.items():
            if text.casefold() == label.casefold():
                return member
        return cls.OTHER

    @property
    def label(self) -> str:
        """Deutsche Anzeige-Bezeichnung."""
        return CATEGORY_LABELS[self]


#: Deutsche Anzeigenamen der Kategorien - getrennt vom stabilen JSON-Schlüssel,
#: damit Umbenennungen in der Oberfläche keine Datenmigration auslösen.
CATEGORY_LABELS: Final[dict[Category, str]] = {
    Category.FLOUR: "Mehl",
    Category.GRAINS: "Getreide & Flocken",
    Category.SEEDS_NUTS: "Saaten & Kerne",
    Category.LEAVENING: "Triebmittel",
    Category.BASICS: "Grundzutaten",
    Category.FATS_OILS: "Fette & Öle",
    Category.DAIRY: "Milchprodukte",
    Category.SPICES: "Gewürze",
    Category.OTHER: "Sonstiges",
}


class Source(Enum):
    """Herkunft eines Datenwerts - entscheidet, ob er angefasst werden darf."""

    LABEL = "label"
    """Vom Produktetikett abgetippt. Diese Werte sind unantastbar."""

    REFERENCE = "reference"
    """Aus einer Nährwerttabelle (z. B. USDA FoodData Central)."""

    CALCULATED = "calculated"
    """Aus anderen Feldern oder aus der Rezeptur berechnet."""

    ESTIMATED = "estimated"
    """Fachlich begründete Schätzung, z. B. der Wassergehalt."""

    UNKNOWN = "unknown"

    @classmethod
    def parse(cls, value: object) -> Source:
        """Robustes Einlesen; unbekannte Werte werden zu :attr:`UNKNOWN`."""
        if isinstance(value, cls):
            return value
        text = str(value or "").strip().casefold()
        for member in cls:
            if text == member.value:
                return member
        return cls.UNKNOWN


def normalize_key_part(text: str) -> str:
    """Normalisiert einen Namensbestandteil für den Vergleich.

    Unicode-NFC, Kleinschreibung und zusammengefasste Leerzeichen. Damit gelten
    ``"KürbiskernÖl (dm Bio)"`` und ``"Kürbiskernöl (dm Bio)"`` als dieselbe
    Zutat - genau dieser Tippfehler steckte doppelt in der Altdatenbank.
    """
    normalized = unicodedata.normalize("NFC", text)
    return " ".join(normalized.split()).casefold()


@dataclass(frozen=True, slots=True)
class PriceEntry:
    """Ein historischer Preisstand."""

    recorded_at: datetime
    package_price: float
    package_size_g: float
    source: str = ""

    @property
    def price_per_100g(self) -> float:
        """Preis je 100 g, oder 0 wenn keine Packungsgröße hinterlegt ist."""
        if self.package_size_g <= 0:
            return 0.0
        return self.package_price / self.package_size_g * 100.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "recorded_at": self.recorded_at.isoformat(),
            "package_price": self.package_price,
            "package_size_g": self.package_size_g,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PriceEntry:
        return cls(
            recorded_at=_parse_datetime(data.get("recorded_at")),
            package_price=_as_float(data.get("package_price")),
            package_size_g=_as_float(data.get("package_size_g")),
            source=str(data.get("source") or ""),
        )


@dataclass(slots=True)
class Ingredient:
    """Eine Zutat mit Nährwerten je 100 g, Herkunftsangaben und Preis."""

    name: str
    category: Category = Category.OTHER
    manufacturer: str = ""
    nutrients: Nutrients = field(default_factory=Nutrients)

    #: Zählt die Zutat bei Bäckerprozent und Teigausbeute als Mehl?
    #: Früher wurde das über Namens-Schlüsselwörter geraten, was
    #: "Altbrot (Paniermehl)" und "Sojamehl" fälschlich zu Mehl machte.
    is_flour: bool = False

    package_price: float = 0.0
    package_size_g: float = 0.0
    price_history: list[PriceEntry] = field(default_factory=list)
    price_source: str = ""
    price_updated: date | None = None

    nutrition_source: Source = Source.UNKNOWN
    water_source: Source = Source.ESTIMATED
    notes: str = ""

    def __post_init__(self) -> None:
        """Normalisiert die Aufzählungsfelder.

        Der Konstruktor wird auch aus der Oberfläche heraus aufgerufen, wo Qt
        gelegentlich Zeichenketten statt der Aufzählungswerte liefert. Die
        Umwandlung hier verhindert, dass so ein Wert unbemerkt bis in die
        JSON-Datei durchschlägt.
        """
        self.category = Category.parse(self.category)
        self.nutrition_source = Source.parse(self.nutrition_source)
        self.water_source = Source.parse(self.water_source)

    # ── Identität ─────────────────────────────────────────────────────────

    @property
    def key(self) -> str:
        """Stabiler, normalisierter Schlüssel aus Name und Hersteller."""
        return f"{normalize_key_part(self.name)}|{normalize_key_part(self.manufacturer)}"

    @property
    def display_name(self) -> str:
        """Name inklusive Hersteller, wie er in Listen erscheint."""
        return f"{self.name} ({self.manufacturer})" if self.manufacturer else self.name

    # ── Preis ─────────────────────────────────────────────────────────────

    @property
    def price_per_100g(self) -> float:
        """Preis je 100 g; 0, wenn Preis oder Packungsgröße fehlen."""
        if self.package_size_g <= 0:
            return 0.0
        return self.package_price / self.package_size_g * 100.0

    @property
    def has_price(self) -> bool:
        """True, wenn ein verwertbarer Preis hinterlegt ist."""
        return self.package_price > 0 and self.package_size_g > 0

    def cost_for(self, amount_g: float) -> float:
        """Materialkosten für ``amount_g`` Gramm dieser Zutat."""
        if self.package_size_g <= 0:
            return 0.0
        return amount_g / self.package_size_g * self.package_price

    def update_price(
        self,
        package_price: float,
        package_size_g: float,
        *,
        source: str = "",
        today: date | None = None,
    ) -> None:
        """Setzt einen neuen Preis und schreibt den alten in die Historie.

        Ein unveränderter Preis erzeugt keinen Historieneintrag, damit wieder-
        holtes Speichern die Historie nicht aufbläht.
        """
        changed = (
            abs(self.package_price - package_price) > 1e-9
            or abs(self.package_size_g - package_size_g) > 1e-9
        )
        if changed and self.package_price > 0 and self.package_size_g > 0:
            self.price_history.append(
                PriceEntry(
                    recorded_at=datetime.now(timezone.utc),
                    package_price=self.package_price,
                    package_size_g=self.package_size_g,
                    source=self.price_source,
                )
            )
        self.package_price = package_price
        self.package_size_g = package_size_g
        if source:
            self.price_source = source
        if changed:
            self.price_updated = today or date.today()

    # ── Serialisierung ────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "manufacturer": self.manufacturer,
            "category": self.category.value,
            "is_flour": self.is_flour,
        }
        data.update(self.nutrients.to_dict())
        data.update(
            {
                "package_price": self.package_price,
                "package_size_g": self.package_size_g,
                "price_source": self.price_source,
                "price_updated": self.price_updated.isoformat() if self.price_updated else None,
                "nutrition_source": self.nutrition_source.value,
                "water_source": self.water_source.value,
                "notes": self.notes,
                "price_history": [e.to_dict() for e in self.price_history],
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Ingredient:
        """Liest eine Zutat aus dem v2-Format.

        Raises:
            ValueError: Wenn kein Name gesetzt ist oder Zahlenfelder unlesbar sind.
        """
        name = str(data.get("name") or "").strip()
        if not name:
            raise ValueError("Zutat ohne Namen kann nicht gelesen werden")
        return cls(
            name=name,
            manufacturer=str(data.get("manufacturer") or "").strip(),
            category=Category.parse(data.get("category")),
            nutrients=Nutrients.from_dict(data),
            is_flour=bool(data.get("is_flour", False)),
            package_price=_as_float(data.get("package_price")),
            package_size_g=_as_float(data.get("package_size_g")),
            price_history=[PriceEntry.from_dict(e) for e in data.get("price_history") or []],
            price_source=str(data.get("price_source") or ""),
            price_updated=_parse_date(data.get("price_updated")),
            nutrition_source=Source.parse(data.get("nutrition_source")),
            water_source=Source.parse(data.get("water_source")),
            notes=str(data.get("notes") or ""),
        )

    def copy(self, *, name: str | None = None, manufacturer: str | None = None) -> Ingredient:
        """Tiefe Kopie, optional mit neuem Namen/Hersteller (Duplizieren-Funktion)."""
        return Ingredient(
            name=self.name if name is None else name,
            manufacturer=self.manufacturer if manufacturer is None else manufacturer,
            category=self.category,
            nutrients=self.nutrients,
            is_flour=self.is_flour,
            package_price=self.package_price,
            package_size_g=self.package_size_g,
            price_history=list(self.price_history),
            price_source=self.price_source,
            price_updated=self.price_updated,
            nutrition_source=self.nutrition_source,
            water_source=self.water_source,
            notes=self.notes,
        )


@dataclass(frozen=True, slots=True)
class RecipeItem:
    """Eine Zeile in einem Rezept: Zutatenverweis plus Menge.

    Name und Hersteller werden mitgespeichert (denormalisiert), damit ein
    Rezept auch dann noch lesbar bleibt, wenn die Zutat aus der Datenbank
    gelöscht wurde.
    """

    ingredient_key: str
    name: str
    manufacturer: str
    amount_g: float

    @property
    def display_name(self) -> str:
        return f"{self.name} ({self.manufacturer})" if self.manufacturer else self.name

    def scaled(self, factor: float) -> RecipeItem:
        """Kopie mit skalierter Menge."""
        return RecipeItem(self.ingredient_key, self.name, self.manufacturer, self.amount_g * factor)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ingredient_key": self.ingredient_key,
            "name": self.name,
            "manufacturer": self.manufacturer,
            "amount_g": self.amount_g,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RecipeItem:
        name = str(data.get("name") or "").strip()
        manufacturer = str(data.get("manufacturer") or "").strip()
        key = str(data.get("ingredient_key") or "").strip()
        if not key:
            key = f"{normalize_key_part(name)}|{normalize_key_part(manufacturer)}"
        return cls(
            ingredient_key=key,
            name=name,
            manufacturer=manufacturer,
            amount_g=_as_float(data.get("amount_g")),
        )


@dataclass(slots=True)
class Recipe:
    """Ein Brotrezept mit Zutaten, Prozessdaten und Notizen."""

    name: str
    items: list[RecipeItem] = field(default_factory=list)
    baked_weight_g: float = 0.0
    dough_weight_g: float = 0.0
    energy_kwh: float = 0.0
    notes: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    modified_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    #: Backtag und Mindesthaltbarkeit des zuletzt gedruckten Etiketts. Sie
    #: gehören zum Rezept, nicht zum Etikett: Beim nächsten Aufruf soll ohne
    #: Suchen sichtbar sein, wann zuletzt gebacken wurde und wie lange das Brot
    #: damals halten sollte. ``None`` heißt: noch nie ein Etikett erstellt.
    last_baked_on: date | None = None
    last_best_before: date | None = None

    @property
    def total_amount_g(self) -> float:
        """Summe aller eingewogenen Zutaten."""
        return sum(item.amount_g for item in self.items)

    def scaled(self, factor: float, *, name: str | None = None) -> Recipe:
        """Neues Rezept mit allen Mengen und Gewichten × ``factor``.

        Raises:
            ValueError: Bei nicht-positivem oder nicht endlichem Faktor.
        """
        if not (factor > 0) or factor == float("inf"):
            raise ValueError(f"Skalierungsfaktor muss > 0 und endlich sein, war {factor!r}")
        return Recipe(
            name=name or f"{self.name} ×{factor:.2f}".replace(".", ","),
            items=[item.scaled(factor) for item in self.items],
            baked_weight_g=self.baked_weight_g * factor,
            dough_weight_g=self.dough_weight_g * factor,
            energy_kwh=self.energy_kwh,  # Backenergie skaliert nicht linear mit der Menge
            notes=self.notes,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "items": [i.to_dict() for i in self.items],
            "baked_weight_g": self.baked_weight_g,
            "dough_weight_g": self.dough_weight_g,
            "energy_kwh": self.energy_kwh,
            "notes": self.notes,
            "created_at": self.created_at.isoformat(),
            "modified_at": self.modified_at.isoformat(),
            "last_baked_on": self.last_baked_on.isoformat() if self.last_baked_on else None,
            "last_best_before": (
                self.last_best_before.isoformat() if self.last_best_before else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Recipe:
        name = str(data.get("name") or "").strip()
        if not name:
            raise ValueError("Rezept ohne Namen kann nicht gelesen werden")
        return cls(
            name=name,
            items=[RecipeItem.from_dict(i) for i in data.get("items") or []],
            baked_weight_g=_as_float(data.get("baked_weight_g")),
            dough_weight_g=_as_float(data.get("dough_weight_g")),
            energy_kwh=_as_float(data.get("energy_kwh")),
            notes=str(data.get("notes") or ""),
            created_at=_parse_datetime(data.get("created_at")),
            modified_at=_parse_datetime(data.get("modified_at") or data.get("created_at")),
            last_baked_on=_parse_date(data.get("last_baked_on")),
            last_best_before=_parse_date(data.get("last_best_before")),
        )


# ── Hilfsfunktionen für robustes Einlesen ─────────────────────────────────


def _as_float(value: object) -> float:
    """Wandelt einen JSON-Wert in float; ``None``/leer wird zu 0."""
    if value is None or value == "":
        return 0.0
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Zahlenwert erwartet, war {value!r}") from exc


def as_aware(moment: datetime) -> datetime:
    """Ergänzt bei einem Zeitstempel ohne Zeitzone die lokale Zone.

    Das Altprogramm schrieb ``datetime.now().isoformat()`` und damit
    Zeitstempel *ohne* Zonenangabe. Neue Einträge tragen dagegen UTC. Beides
    zusammen in eine Sortierung zu geben, wirft in Python einen ``TypeError``
    ("can't compare offset-naive and offset-aware datetimes") - und weil das
    Speichern in einem Qt-Signal steckt, verschwand die Meldung ungesehen und
    das Rezept wurde nicht gespeichert.

    Deshalb wird jede eingelesene Zeitangabe an dieser einen Stelle
    vereinheitlicht. Zeitstempel ohne Zone stammen aus der lokalen Zeit des
    Rechners, auf dem sie entstanden sind; genau so werden sie gedeutet.
    """
    return moment.astimezone() if moment.tzinfo is None else moment


def _parse_datetime(value: object) -> datetime:
    """Liest einen ISO-Zeitstempel als zonenbehaftete Zeit.

    Bei Unlesbarkeit wird die aktuelle Zeit eingesetzt: Ein Rezept ohne
    brauchbares Datum ist immer noch ein Rezept.
    """
    if isinstance(value, datetime):
        return as_aware(value)
    if isinstance(value, str) and value:
        try:
            return as_aware(datetime.fromisoformat(value))
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _parse_date(value: object) -> date | None:
    """Liest ein ISO-Datum; ``None`` bei fehlender oder unlesbarer Angabe."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None
