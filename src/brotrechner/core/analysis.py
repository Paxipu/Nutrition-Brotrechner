"""Rezeptauswertung: Nährwerte, Bäckerprozent, Teigausbeute und Kosten.

Das Modul enthält **reine Funktionen**. :func:`analyze` bekommt Zutaten und
Prozessdaten herein und gibt ein unveränderliches :class:`RecipeAnalysis`
zurück; es gibt keinen versteckten Zustand und keine Abhängigkeit zur
Oberfläche. Genau deshalb ist die Rechnung vollständig testbar.

Fachliche Definitionen
----------------------

**Bäckerprozent** - jede Zutat relativ zur Gesamtmehlmenge, die per Definition
100 % ist. Zur Mehlmenge trägt jede Zutat mit ihrem ausdrücklich hinterlegten
Mehlanteil bei (:attr:`~brotrechner.core.models.Ingredient.flour_percent`):
Mehl mit 100 %, ein Anstellgut aus gleichen Teilen Mehl und Wasser mit 50 %.

**Teigausbeute (TA)** - ``(Mehl + Schüttwasser) / Mehl × 100``. Als Schüttwasser
zählt das *tatsächlich enthaltene Wasser* außerhalb des Mehlanteils, also
z. B. 87,5 g je 100 g Milch statt der vollen 100 g. Die Eigenfeuchte des
Mehlanteils gehört zum Mehl - bei reinem Mehl ebenso wie im Sauerteig.

.. note::
   Die Vorgängerversion zählte jede Zutat mit mindestens 50 % Wassergehalt
   vollständig als Flüssigkeit; 100 g Milch erhöhten die TA also so stark wie
   100 g Wasser, und 100 g Quark (80 % Wasser) ebenso. Für Rezepte aus Mehl,
   Wasser und Salz - also alle bisher gespeicherten - ändert sich das Ergebnis
   nicht, bei Milch, Joghurt oder Sauerteig fällt die TA jetzt korrekt niedriger
   aus.

**Hydration** - international übliche Schreibweise derselben Größe:
``Schüttwasser / Mehl × 100``, also stets ``TA - 100``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from brotrechner.core.models import Ingredient, RecipeItem
from brotrechner.core.nutrients import NUTRIENT_FIELDS, Nutrients
from brotrechner.core.portions import Portion
from brotrechner.core.rounding import as_declarable
from brotrechner.core.tolerances import ValueRange, nutrient_ranges

__all__ = [
    "DEFAULT_ENERGY_PRICE_EUR_PER_KWH",
    "FLOUR_MOISTURE_PERCENT",
    "IngredientLine",
    "RecipeAnalysis",
    "ResolvedItem",
    "added_water_percent",
    "analyze",
    "resolve_items",
]

#: Vorbelegung Strompreis; frei änderbar in der Oberfläche.
DEFAULT_ENERGY_PRICE_EUR_PER_KWH: Final = 0.35

#: Eigenfeuchte von Mehl in Prozent (handelsüblich 12-15 %). Steckt Mehl in
#: einer Zutat wie einem Sauerteig, gehört dieses Wasser zum Mehlanteil und
#: nicht zum Schüttwasser. Mit demselben Wert sind die Sauerteige der
#: Startdatenbank berechnet: 100 g Mehl und 100 g Wasser ergeben 113 g Wasser
#: auf 200 g, also die dort hinterlegten 56,5 %.
FLOUR_MOISTURE_PERCENT: Final = 13.0


def added_water_percent(ingredient: Ingredient) -> float:
    """Schüttwasser je 100 g Zutat.

    Das ist das enthaltene Wasser ohne die Eigenfeuchte des Mehlanteils. Es
    kann weder negativ werden (trockener Vorteig) noch größer sein als der Teil
    der Zutat, der kein Mehl ist - bei reinem Mehl also immer 0, gleich wie
    feucht es ist.

    Args:
        ingredient: Zutat mit Wassergehalt und Mehlanteil.

    Returns:
        Schüttwasser in Gramm je 100 g Zutat.
    """
    flour = ingredient.flour_fraction * 100.0
    free_water = ingredient.nutrients.water - flour * FLOUR_MOISTURE_PERCENT / 100.0
    return min(max(0.0, free_water), 100.0 - flour)


@dataclass(frozen=True, slots=True)
class ResolvedItem:
    """Rezeptzeile mit aufgelöster Zutat."""

    ingredient: Ingredient
    amount_g: float


@dataclass(frozen=True, slots=True)
class IngredientLine:
    """Ausgewertete Rezeptzeile."""

    ingredient: Ingredient
    amount_g: float
    """Wirksame Menge nach Teigverlust-Skalierung."""
    share_percent: float
    """Anteil an der Gesamteinwaage."""
    baker_percent: float
    """Anteil an der Mehlmenge; 0, wenn kein Mehl im Rezept ist."""
    cost: float
    """Materialkosten dieser Zeile in Euro."""
    water_g: float
    """Im Zutatenanteil enthaltenes Wasser."""

    @property
    def has_price(self) -> bool:
        return self.ingredient.has_price


@dataclass(frozen=True, slots=True)
class RecipeAnalysis:
    """Vollständiges Ergebnis einer Rezeptauswertung."""

    lines: tuple[IngredientLine, ...] = ()

    # Massen
    weighed_mass_g: float = 0.0
    """Summe der eingewogenen Zutaten."""
    dough_weight_g: float = 0.0
    """Rohteiggewicht (gemessen oder = Einwaage)."""
    baked_weight_g: float = 0.0
    scale_factor: float = 1.0
    """Faktor Rohteig/Einwaage - fängt Teigreste in der Schüssel auf."""
    water_loss_percent: float = 0.0
    """Backverlust vom Rohteig zum fertigen Brot."""

    # Backtechnik
    flour_mass_g: float = 0.0
    water_mass_g: float = 0.0
    dough_yield: float = 0.0
    hydration_percent: float = 0.0

    # Nährwerte
    total: Nutrients = field(default_factory=Nutrients)
    """Absolute Nährwerte des gesamten Teigs."""
    per_100g: Nutrients = field(default_factory=Nutrients)
    """Nährwerte je 100 g fertig gebackenes Brot."""
    ranges_per_100g: dict[str, ValueRange] = field(default_factory=dict)
    """Zulässige Abweichung der Angaben je 100 g gebacken (EU-Toleranzen)."""

    # Kosten
    material_cost: float = 0.0
    energy_cost: float = 0.0
    total_cost: float = 0.0
    cost_per_100g: float = 0.0
    energy_kwh: float = 0.0
    energy_price: float = DEFAULT_ENERGY_PRICE_EUR_PER_KWH

    # Portion
    portion: Portion | None = None
    """Portion für Angaben je Scheibe oder Stück; ``None`` heißt nur je 100 g."""

    @property
    def is_empty(self) -> bool:
        return not self.lines

    @property
    def per_portion(self) -> Nutrients | None:
        """Nährwerte je Portion, aus den ungerundeten Werten je 100 g."""
        portion = self._usable_portion()
        return portion.nutrients(self.per_100g) if portion else None

    @property
    def cost_per_portion(self) -> float | None:
        """Kosten je Portion in Euro."""
        portion = self._usable_portion()
        return portion.cost(self.cost_per_100g) if portion else None

    @property
    def portion_count(self) -> float | None:
        """Wie viele Portionen das Brot ergibt."""
        portion = self._usable_portion()
        return portion.count(self.baked_weight_g) if portion else None

    def _usable_portion(self) -> Portion | None:
        """Die Portion, sofern es Werte je Portion gibt.

        Dafür braucht es Zutaten und das Gewicht des Brots - ohne sie gibt es
        auch keine Werte je 100 g.
        """
        if self.is_empty or self.baked_weight_g <= 0:
            return None
        return self.portion

    @property
    def cost_per_kg(self) -> float:
        return self.cost_per_100g * 10.0

    @property
    def has_complete_prices(self) -> bool:
        """True, wenn für jede Zutat ein Preis hinterlegt ist."""
        return all(line.has_price for line in self.lines)

    @property
    def lines_without_price(self) -> tuple[IngredientLine, ...]:
        return tuple(line for line in self.lines if not line.has_price)

    @property
    def dough_yield_description(self) -> str:
        """Umgangssprachliche Einordnung der Teigausbeute."""
        ta = self.dough_yield
        if ta <= 0:
            return ""
        if ta < 150:
            return "fester Teig (z. B. Brötchen, Baguette)"
        if ta < 170:
            return "mittlerer Teig (z. B. Mischbrot, Roggenbrot)"
        if ta < 200:
            return "weicher Teig (z. B. Ciabatta, Focaccia)"
        return "sehr weicher bis fließender Teig"


def resolve_items(
    items: list[RecipeItem],
    ingredients: dict[str, Ingredient],
) -> tuple[list[ResolvedItem], list[RecipeItem]]:
    """Verknüpft Rezeptzeilen mit den Zutaten der Datenbank.

    Die Auflösung erfolgt zuerst über den Schlüssel, ersatzweise über
    ``name|hersteller`` - so bleiben Rezepte lesbar, die vor der
    Hersteller-Trennung gespeichert wurden.

    Args:
        items: Rezeptzeilen.
        ingredients: Zutatendatenbank, indiziert nach
            :attr:`~brotrechner.core.models.Ingredient.key`.

    Returns:
        Tupel aus aufgelösten Zeilen und den Zeilen, zu denen keine Zutat
        gefunden wurde.
    """
    resolved: list[ResolvedItem] = []
    missing: list[RecipeItem] = []
    for item in items:
        ingredient = ingredients.get(item.ingredient_key)
        if ingredient is None:
            missing.append(item)
            continue
        resolved.append(ResolvedItem(ingredient, item.amount_g))
    return resolved, missing


def analyze(
    items: list[ResolvedItem],
    *,
    baked_weight_g: float,
    dough_weight_g: float = 0.0,
    energy_kwh: float = 0.0,
    energy_price: float = DEFAULT_ENERGY_PRICE_EUR_PER_KWH,
    portion: Portion | None = None,
) -> RecipeAnalysis:
    """Wertet ein Rezept vollständig aus.

    Args:
        items: Zutaten mit Mengen in Gramm.
        baked_weight_g: Gewicht des fertigen Brots. Bezugsgröße für alle
            "je 100 g"-Werte. Bei ``<= 0`` bleiben diese Werte 0.
        dough_weight_g: Gemessenes Rohteiggewicht. Ist es größer oder kleiner
            als die Einwaage, werden alle Mengen entsprechend skaliert; so
            wirkt sich Teig, der in der Schüssel bleibt, korrekt aus.
        energy_kwh: Energieverbrauch des Backvorgangs.
        energy_price: Strompreis in Euro je kWh.
        portion: Portion für die Angaben je Scheibe oder Stück.

    Returns:
        Auswertung; bei leerer Zutatenliste ein leeres :class:`RecipeAnalysis`.

    Raises:
        ValueError: Bei negativen Mengen, Gewichten oder Preisen.
    """
    _validate_inputs(items, baked_weight_g, dough_weight_g, energy_kwh, energy_price)

    if not items:
        return RecipeAnalysis(
            baked_weight_g=max(0.0, baked_weight_g),
            energy_kwh=energy_kwh,
            energy_price=energy_price,
            portion=portion,
        )

    weighed = sum(item.amount_g for item in items)
    effective_dough = dough_weight_g if dough_weight_g > 0 else weighed
    scale = effective_dough / weighed if weighed > 0 else 1.0

    flour_mass = sum(i.amount_g * scale * i.ingredient.flour_fraction for i in items)
    # Schüttwasser: nur das Wasser außerhalb des Mehlanteils. Die Eigenfeuchte
    # des Mehls steckt bereits in der Mehlmenge, mit der die TA definiert ist.
    water_mass = sum(i.amount_g * scale * added_water_percent(i.ingredient) / 100.0 for i in items)

    total = Nutrients()
    material_cost = 0.0
    lines: list[IngredientLine] = []
    for item in items:
        amount = item.amount_g * scale
        total = total + item.ingredient.nutrients.scaled(amount / 100.0)
        cost = item.ingredient.cost_for(amount)
        material_cost += cost
        lines.append(
            IngredientLine(
                ingredient=item.ingredient,
                amount_g=amount,
                share_percent=amount / effective_dough * 100.0 if effective_dough > 0 else 0.0,
                baker_percent=amount / flour_mass * 100.0 if flour_mass > 0 else 0.0,
                cost=cost,
                water_g=amount * item.ingredient.nutrients.water / 100.0,
            )
        )

    per_100g = total.scaled(100.0 / baked_weight_g) if baked_weight_g > 0 else Nutrients()
    # Der Wassergehalt des Brots ergibt sich aus dem Backverlust, nicht aus der
    # Summe der Zutatenwasser - beim Backen verdampft genau die Differenz.
    if baked_weight_g > 0:
        remaining_water = max(0.0, total.water - (effective_dough - baked_weight_g))
        per_100g = per_100g.with_values(water=remaining_water / baked_weight_g * 100.0)

    energy_cost = energy_kwh * energy_price
    total_cost = material_cost + energy_cost

    return RecipeAnalysis(
        lines=tuple(lines),
        weighed_mass_g=weighed,
        dough_weight_g=effective_dough,
        baked_weight_g=baked_weight_g,
        scale_factor=scale,
        water_loss_percent=(
            (1.0 - baked_weight_g / effective_dough) * 100.0 if effective_dough > 0 else 0.0
        ),
        flour_mass_g=flour_mass,
        water_mass_g=water_mass,
        dough_yield=(flour_mass + water_mass) / flour_mass * 100.0 if flour_mass > 0 else 0.0,
        hydration_percent=water_mass / flour_mass * 100.0 if flour_mass > 0 else 0.0,
        total=total,
        per_100g=per_100g,
        ranges_per_100g=_ranges_per_100g(per_100g, baked_weight_g=baked_weight_g),
        material_cost=material_cost,
        energy_cost=energy_cost,
        total_cost=total_cost,
        cost_per_100g=total_cost / baked_weight_g * 100.0 if baked_weight_g > 0 else 0.0,
        energy_kwh=energy_kwh,
        energy_price=energy_price,
        portion=portion,
    )


def _ranges_per_100g(per_100g: Nutrients, *, baked_weight_g: float) -> dict[str, ValueRange]:
    """Zulässige Abweichung der Angaben je 100 g des fertigen Brots.

    Die Toleranzen der EU-Leitlinie gelten für den angegebenen Wert des
    Lebensmittels, das kontrolliert wird - hier also für das Brot, nicht für
    seine Zutaten. Früher stand hier die mengengewichtete Summe der
    Zutatentoleranzen; das ist eine andere Größe, die mit der Kontrolle eines
    Brots nichts zu tun hat.

    Negative oder nicht endliche Werte entstehen nur aus fehlerhaften Zutaten
    (die Datenprüfung meldet sie); sie werden hier wie 0 behandelt, damit die
    Auswertung nicht abbricht.
    """
    if baked_weight_g <= 0:
        return {}
    clean = Nutrients(**{name: as_declarable(getattr(per_100g, name)) for name in NUTRIENT_FIELDS})
    return nutrient_ranges(clean)


def _validate_inputs(
    items: list[ResolvedItem],
    baked_weight_g: float,
    dough_weight_g: float,
    energy_kwh: float,
    energy_price: float,
) -> None:
    """Prüft die Eingaben von :func:`analyze` an der Modulgrenze."""
    for item in items:
        if item.amount_g < 0:
            raise ValueError(
                f"Negative Menge für {item.ingredient.display_name!r}: {item.amount_g}"
            )
    for name, value in (
        ("baked_weight_g", baked_weight_g),
        ("dough_weight_g", dough_weight_g),
        ("energy_kwh", energy_kwh),
        ("energy_price", energy_price),
    ):
        if value < 0:
            raise ValueError(f"{name} darf nicht negativ sein, war {value!r}")


def aggregate_nutrients(items: list[ResolvedItem]) -> Nutrients:
    """Absolute Nährwertsumme einer Zutatenliste (ohne Skalierung).

    Nützlich für Vorschauen, die keine vollständige Auswertung brauchen.
    """
    total = Nutrients()
    for item in items:
        total = total + item.ingredient.nutrients.scaled(item.amount_g / 100.0)
    return total
