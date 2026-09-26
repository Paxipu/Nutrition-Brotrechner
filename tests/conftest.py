"""Gemeinsame Testbausteine."""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from hypothesis import HealthCheck, settings

from brotrechner.core.models import Category, Ingredient, Recipe, RecipeItem
from brotrechner.core.nutrients import Nutrients

# Dateisystemzugriffe machen einzelne Hypothesis-Beispiele langsam; die
# Voreinstellung würde deshalb grundlos scheitern.
settings.register_profile(
    "brotrechner",
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("brotrechner")


@pytest.fixture(scope="session")
def qapp() -> Iterator[object]:
    """Eine Qt-Anwendung für die wenigen Tests, die Widgets brauchen.

    Läuft ohne Bildschirm ("offscreen"), damit die Tests auch auf einem
    Bauserver durchlaufen. Qt duldet nur eine Anwendungsinstanz je Prozess,
    deshalb die Sitzungsgültigkeit.
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from brotrechner.gui.app import create_app

    app = create_app([])
    yield app


@pytest.fixture
def flour() -> Ingredient:
    """Roggenvollkornmehl mit geprüften Werten und Preis."""
    return Ingredient(
        name="Roggenvollkornmehl",
        manufacturer="Bauck",
        category=Category.FLOUR,
        nutrients=Nutrients(
            energy_kcal=317,
            fat=1.7,
            saturated_fat=0.3,
            carbs=60.0,
            sugar=1.0,
            protein=8.5,
            salt=0.01,
            fiber=14.0,
            water=13.0,
        ),
        flour_percent=100.0,
        package_price=1.98,
        package_size_g=1000,
    )


@pytest.fixture
def water() -> Ingredient:
    """Wasser: 100 % Wasser, praktisch kostenlos."""
    return Ingredient(
        name="Wasser",
        category=Category.BASICS,
        nutrients=Nutrients(water=100.0),
        package_price=4.50,
        package_size_g=1_000_000,
    )


@pytest.fixture
def salt() -> Ingredient:
    """Speisesalz."""
    return Ingredient(
        name="Salz",
        category=Category.BASICS,
        nutrients=Nutrients(salt=100.0),
        package_price=0.19,
        package_size_g=500,
    )


@pytest.fixture
def milk() -> Ingredient:
    """Milch - Testfall für teilweise wasserhaltige Zutaten."""
    return Ingredient(
        name="Milch",
        category=Category.DAIRY,
        nutrients=Nutrients(
            energy_kcal=64,
            fat=3.5,
            saturated_fat=2.3,
            carbs=4.8,
            sugar=4.8,
            protein=3.3,
            salt=0.1,
            water=87.5,
        ),
        package_price=1.15,
        package_size_g=1030,
    )


@pytest.fixture
def simple_recipe(flour: Ingredient, water: Ingredient, salt: Ingredient) -> Recipe:
    """Reines Roggenbrot aus Mehl, Wasser und Salz."""
    return Recipe(
        name="Testbrot",
        items=[
            RecipeItem(flour.key, flour.name, flour.manufacturer, 1000.0),
            RecipeItem(water.key, water.name, water.manufacturer, 700.0),
            RecipeItem(salt.key, salt.name, salt.manufacturer, 20.0),
        ],
        baked_weight_g=1500.0,
        dough_weight_g=1720.0,
    )


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Isoliertes Datenverzeichnis; berührt niemals echte Nutzerdaten.

    Auch das Benutzerverzeichnis ist ein leerer Ordner des Tests: Sonst legte
    jeder Export auf einem Entwicklerrechner ``~/Documents/Brotrechner`` an.
    """
    target = tmp_path / "daten"
    target.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("BROTRECHNER_DATA_DIR", str(target))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    yield target


#: So lange darf ein modaler Dialog offen stehen, bevor er als vergessen gilt.
#: Beantwortete Dialoge kehren in Millisekunden zurück.
_DIALOG_PATIENCE_MS = 1500


@dataclass
class DialogGuard:
    """Schließt modale Dialoge, die ein Test offen gelassen hat, und merkt sie sich."""

    left_open: list[str] = field(default_factory=list)

    def close_open_dialogs(self) -> list[str]:
        """Schließt alle offenen modalen Dialoge.

        Returns:
            Ihre Fenstertitel - oder die Klassennamen, wo der Titel fehlt.
        """
        from PySide6.QtWidgets import QApplication, QDialog

        closed: list[str] = []
        while (widget := QApplication.activeModalWidget()) is not None:
            closed.append(widget.windowTitle() or type(widget).__name__)
            if isinstance(widget, QDialog):
                widget.reject()
            else:
                widget.close()
            if QApplication.activeModalWidget() is widget:  # ließ sich nicht schließen
                break
        self.left_open += closed
        return closed


@pytest.fixture(autouse=True)
def dialog_guard(request: pytest.FixtureRequest) -> Iterator[DialogGuard]:
    """Lässt einen Oberflächentest scheitern, statt an einem Dialog hängenzubleiben.

    Ein modaler Dialog, den ein Test nicht beantwortet, hielt bisher den ganzen
    Testlauf an - ohne Meldung, bis jemand ihn abbrach. Jetzt schließt ein
    Zeitgeber ihn nach :data:`_DIALOG_PATIENCE_MS`, und der Test scheitert mit
    dem Titel des Dialogs. Beantwortet werden Dialoge mit ``dialogs``.
    """
    guard = DialogGuard()
    if request.node.get_closest_marker("gui") is None:
        yield guard
        return
    request.getfixturevalue("qapp")
    from PySide6.QtCore import QTimer

    timer = QTimer()
    timer.setInterval(_DIALOG_PATIENCE_MS)
    timer.timeout.connect(guard.close_open_dialogs)
    timer.start()
    try:
        yield guard
    finally:
        timer.stop()
    guard.close_open_dialogs()
    if guard.left_open:
        pytest.fail(
            "Unbeantwortete Dialoge: "
            + ", ".join(f"„{title}“" for title in guard.left_open)
            + " - bitte im Test beantworten, etwa mit der Fixture „dialogs“."
        )


@pytest.fixture
def dialogs(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Beantwortet alle modalen Dialoge, damit Tests nicht daran hängenbleiben.

    Die Rückgaben bilden Qt originalgetreu ab: Die angeklickte Schaltfläche
    kommt als *Zahl* zurück, nicht als Enum-Mitglied. Attrappen, die stattdessen
    das Enum lieferten, ließen einen echten Fehler jahrelang durchrutschen -
    siehe ``brotrechner.gui.qt_compat``.

    Das zurückgegebene Wörterbuch steuert die Antworten:
    ``name`` für Texteingaben, ``notes`` für den Notizdialog (``None`` heißt
    "unverändert"), ``button`` für Ja/Nein und ``accept`` für Dialoge mit
    ``exec()``.
    """
    from PySide6.QtWidgets import QDialog, QInputDialog, QMessageBox

    answers: dict[str, object] = {
        "name": "Testbrot",
        "notes": None,
        "button": int(QMessageBox.StandardButton.Yes),
        "accept": True,
    }

    for kind in ("information", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, kind, lambda *_a, **_k: answers["button"])
    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: answers["button"])
    monkeypatch.setattr(QInputDialog, "getText", lambda *_a, **_k: (answers["name"], True))
    monkeypatch.setattr(
        QInputDialog, "getMultiLineText", lambda *_a, **_k: (answers["notes"] or "", True)
    )

    class _NotesStub:
        """Ersetzt den Notizdialog, ohne ein Fenster zu öffnen."""

        DialogCode = QDialog.DialogCode

        def __init__(self, recipe_name: str, notes: str, parent: object = None) -> None:
            del recipe_name, parent
            self._current = notes

        def exec(self) -> int:
            return int(
                QDialog.DialogCode.Accepted if answers["accept"] else QDialog.DialogCode.Rejected
            )

        @property
        def notes(self) -> str:
            wanted = answers["notes"]
            return self._current if wanted is None else str(wanted)

    monkeypatch.setattr("brotrechner.gui.main_window.NotesDialog", _NotesStub)
    return answers
