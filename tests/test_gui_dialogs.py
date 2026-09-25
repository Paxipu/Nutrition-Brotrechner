"""Verhalten der Dialoge: Datumskopplung im Etikett, Notizen am Rezept.

Diese Tests brauchen eine Qt-Anwendung. Sie prüfen keine Optik, sondern die
Regeln, nach denen sich die Bedienelemente gegenseitig beeinflussen - genau
das, was sich beim Ausprobieren von Hand nur mühsam nachvollziehen lässt.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from brotrechner.core.analysis import ResolvedItem, analyze
from brotrechner.core.models import Ingredient, Recipe

pytestmark = pytest.mark.gui


@pytest.fixture
def analysis(flour: Ingredient, water: Ingredient):
    """Eine Auswertung, wie sie der Rechner an den Etikettdialog reicht."""
    return analyze(
        [ResolvedItem(flour, 1000.0), ResolvedItem(water, 700.0)],
        baked_weight_g=1500.0,
    )


@pytest.fixture
def label(qapp: object, analysis, tmp_path: Path):
    """Etikettdialog ohne Bildschirm."""
    del qapp
    from brotrechner.gui.dialogs.label_dialog import LabelDialog

    dialog = LabelDialog(analysis, recipe_name="Probebrot", default_dir=tmp_path)
    yield dialog
    dialog.close()


def _qdate(widget) -> date:
    """Datum eines ``QDateEdit`` als Python-Datum."""
    value = widget.date()
    return date(value.year(), value.month(), value.day())


def _set(widget, value: date) -> None:
    from PySide6.QtCore import QDate

    widget.setDate(QDate(value.year, value.month, value.day))


class TestBakingDateCoupling:
    """Backdatum und Mindesthaltbarkeit hängen in genau einer Richtung zusammen.

    Das Backdatum zieht die Mindesthaltbarkeit mit sich - ändert man das
    Backdatum, verschiebt sich die Haltbarkeit um dieselbe Spanne. Umgekehrt
    gilt das ausdrücklich *nicht*: Wer die Haltbarkeit von Hand setzt, will
    genau dieses Datum und nicht plötzlich ein anderes Backdatum.
    """

    def test_baking_date_starts_today(self, label: object) -> None:
        assert _qdate(label.date_baked) == date.today()

    def test_moving_the_baking_date_moves_the_best_before(self, label: object) -> None:
        vorher = _qdate(label.date_best_before)
        _set(label.date_baked, date.today() - timedelta(days=3))
        assert _qdate(label.date_best_before) == vorher - timedelta(days=3)

    def test_the_gap_between_both_dates_stays(self, label: object) -> None:
        _set(label.date_baked, date(2026, 3, 1))
        assert _qdate(label.date_best_before) == date(2026, 3, 8), "Voreinstellung 7 Tage"

    def test_setting_the_best_before_leaves_the_baking_date_alone(self, label: object) -> None:
        """Der ausdrückliche Wunsch: kein Automatismus in diese Richtung."""
        gebacken = _qdate(label.date_baked)
        _set(label.date_best_before, gebacken + timedelta(days=21))
        assert _qdate(label.date_baked) == gebacken

    def test_a_hand_set_best_before_survives(self, label: object) -> None:
        gebacken = _qdate(label.date_baked)
        _set(label.date_best_before, gebacken + timedelta(days=21))
        assert _qdate(label.date_best_before) == gebacken + timedelta(days=21)

    def test_the_hand_set_span_is_reused_for_the_next_baking_date(self, label: object) -> None:
        """Wer 21 Tage wählt, meint 21 Tage - auch nach dem nächsten Backtag."""
        _set(label.date_best_before, _qdate(label.date_baked) + timedelta(days=21))
        _set(label.date_baked, date(2026, 3, 1))
        assert _qdate(label.date_best_before) == date(2026, 3, 22)

    def test_the_best_before_cannot_precede_the_baking_date(self, label: object) -> None:
        _set(label.date_baked, date(2026, 3, 10))
        _set(label.date_best_before, date(2026, 1, 1))
        assert _qdate(label.date_best_before) >= date(2026, 3, 10)


class TestLabelUsesTheChosenDates:
    """Was im Dialog steht, muss auch auf dem Etikett landen."""

    def test_options_carry_the_chosen_baking_date(self, label: object) -> None:
        _set(label.date_baked, date(2026, 3, 1))
        assert label._options(dpi=110).baked_on == date(2026, 3, 1)

    def test_the_printed_line_shows_the_chosen_date(self, label: object) -> None:
        from brotrechner.export.label import date_lines

        _set(label.date_baked, date(2026, 3, 1))
        assert any("01.03.2026" in line for line in date_lines(label._options(dpi=110)))

    def test_best_before_is_only_included_when_ticked(self, label: object) -> None:
        assert label._options(dpi=110).best_before is None
        label.chk_best_before.setChecked(True)
        assert label._options(dpi=110).best_before is not None


class TestOldRecipesStartAtToday:
    """Ein lange zurückliegender Backtag darf den Kalender nicht verschleppen.

    Sonst müsste man sich beim Nachbacken monateweise nach vorn klicken. Das
    zuletzt verwendete Datum wird deshalb angezeigt, aber nicht eingesetzt.
    """

    def test_the_field_still_starts_today(self, qapp: object, analysis, tmp_path: Path) -> None:
        del qapp
        from brotrechner.gui.dialogs.label_dialog import LabelDialog

        dialog = LabelDialog(
            analysis,
            recipe_name="Altbrot",
            default_dir=tmp_path,
            last_baked_on=date(2025, 12, 23),
        )
        assert _qdate(dialog.date_baked) == date.today()
        dialog.close()

    def test_the_last_baking_day_is_shown_as_a_hint(
        self, qapp: object, analysis, tmp_path: Path
    ) -> None:
        del qapp
        from brotrechner.gui.dialogs.label_dialog import LabelDialog

        dialog = LabelDialog(
            analysis,
            recipe_name="Altbrot",
            default_dir=tmp_path,
            last_baked_on=date(2025, 12, 23),
        )
        assert "23.12.2025" in dialog.lbl_last_baked.text()
        dialog.close()

    def test_without_a_previous_bake_there_is_no_hint(self, label: object) -> None:
        assert not label.lbl_last_baked.text()

    def test_an_empty_hint_takes_no_space(self, label: object) -> None:
        """Eine leere Beschriftung belegt sonst Zeilenhöhe, die hier fehlt."""
        assert label.lbl_last_baked.isHidden()


class TestTheSidebarFits:
    """Die beiden Datumsfelder dürfen die Schaltflächen nicht hinausdrängen.

    Die Seitenspalte hat feste Breite und keinen Rollbalken: Was nicht in die
    Mindesthöhe des Dialogs passt, wird gestaucht - zuerst die Schaltflächen
    ganz unten.
    """

    @pytest.mark.parametrize("zuletzt", [None, date(2025, 12, 23)])
    def test_it_fits_into_the_minimum_height(
        self, qapp: object, analysis, tmp_path: Path, zuletzt: date | None
    ) -> None:
        del qapp
        from brotrechner.gui.dialogs.label_dialog import LabelDialog

        dialog = LabelDialog(
            analysis, recipe_name="Probe", default_dir=tmp_path, last_baked_on=zuletzt
        )
        dialog.resize(dialog.minimumSize())
        dialog.show()
        holder = dialog.date_baked.parentWidget()
        while holder is not None and holder.width() != 320:
            holder = holder.parentWidget()
        assert holder is not None, "Seitenspalte nicht gefunden"
        needed = holder.sizeHint().height()
        assert needed <= dialog.height(), f"Seitenspalte braucht {needed} px von {dialog.height()}"
        dialog.close()


class TestNotesDialog:
    """Erfahrungen zum Rezept nachträglich festhalten."""

    def test_it_starts_with_the_existing_notes(self, qapp: object) -> None:
        del qapp
        from brotrechner.gui.dialogs.simple_dialogs import NotesDialog

        dialog = NotesDialog("Probebrot", "Ofen 10 Minuten länger.")
        assert dialog.notes == "Ofen 10 Minuten länger."
        dialog.close()

    def test_it_returns_the_edited_text(self, qapp: object) -> None:
        del qapp
        from brotrechner.gui.dialogs.simple_dialogs import NotesDialog

        dialog = NotesDialog("Probebrot", "alt")
        dialog.txt_notes.setPlainText("Teig war zu weich, 30 g Wasser weniger.")
        assert dialog.notes == "Teig war zu weich, 30 g Wasser weniger."
        dialog.close()

    def test_an_empty_note_is_allowed(self, qapp: object) -> None:
        """Eine Notiz zu löschen muss genauso möglich sein wie sie anzulegen."""
        del qapp
        from brotrechner.gui.dialogs.simple_dialogs import NotesDialog

        dialog = NotesDialog("Probebrot", "alt")
        dialog.txt_notes.setPlainText("")
        assert dialog.notes == ""
        dialog.close()


class TestRecipePreviewShowsTheDates:
    """Die Vorschau ist die Stelle, an der man ein Rezept ansieht."""

    @pytest.fixture
    def page(self, qapp: object, flour: Ingredient, water: Ingredient):
        del qapp
        from brotrechner.gui.pages.recipes import RecipesPage
        from brotrechner.gui.theme import ThemeMode, resolve_tokens

        widget = RecipesPage(resolve_tokens(ThemeMode.LIGHT))
        widget._ingredients = {flour.key: flour, water.key: water}
        yield widget
        widget.close()

    def test_the_last_baking_day_appears(self, page: object, simple_recipe: Recipe) -> None:
        simple_recipe.last_baked_on = date(2025, 12, 23)
        assert "23.12.2025" in page._preview_html(simple_recipe)

    def test_the_best_before_appears(self, page: object, simple_recipe: Recipe) -> None:
        simple_recipe.last_baked_on = date(2025, 12, 23)
        simple_recipe.last_best_before = date(2025, 12, 30)
        assert "30.12.2025" in page._preview_html(simple_recipe)

    def test_a_recipe_never_baked_says_nothing_about_it(
        self, page: object, simple_recipe: Recipe
    ) -> None:
        assert "gebacken am" not in page._preview_html(simple_recipe)


class TestPersistence:
    """Was der Anwender einträgt, muss den Programmstart überleben."""

    @pytest.fixture
    def window(self, qapp: object, data_dir, dialogs: dict[str, object]):
        del qapp, dialogs
        from brotrechner.gui.main_window import MainWindow

        widget = MainWindow(data_dir=data_dir)
        yield widget
        widget.close()

    @staticmethod
    def _reload(data_dir) -> dict[str, Recipe]:
        from brotrechner.data.repository import load_ingredients, load_recipes

        ingredients, _ = load_ingredients(data_dir / "ingredients.json")
        recipes, _ = load_recipes(data_dir / "recipes.json", ingredients)
        return {r.name: r for r in recipes}

    @staticmethod
    def _store(window: object, recipe: Recipe) -> None:
        window._recipes.add(recipe, replace_existing=True)  # type: ignore[attr-defined]
        window._save_recipes()  # type: ignore[attr-defined]
        window._refresh_all()  # type: ignore[attr-defined]

    def test_the_backup_action_secures_the_current_state(
        self, window: object, data_dir, dialogs: dict[str, object]
    ) -> None:
        """Bisher sicherte "Sicherung anlegen" nur den vorherigen Stand."""
        del dialogs
        window._on_backup()  # type: ignore[attr-defined]
        for name in ("ingredients", "recipes"):
            newest = sorted((data_dir / "backups").glob(f"{name}_*.json"))[-1]
            assert newest.read_bytes() == (data_dir / f"{name}.json").read_bytes()

    def test_closing_without_changes_leaves_no_backups(
        self, qapp: object, data_dir, dialogs: dict[str, object]
    ) -> None:
        """Jedes Beenden speicherte - und verdrängte so die echten Sicherungen."""
        del qapp, dialogs
        from brotrechner.gui.main_window import MainWindow

        for _ in range(3):
            MainWindow(data_dir=data_dir).close()
        assert list((data_dir / "backups").glob("*.json")) == []

    def test_notes_added_later_are_written_to_disk(
        self, window: object, data_dir, dialogs: dict[str, object]
    ) -> None:
        self._store(window, Recipe(name="Testbrot"))
        dialogs["notes"] = "Teig war zu weich, 30 g Wasser weniger."
        window._on_recipe_notes("Testbrot")  # type: ignore[attr-defined]

        wieder = self._reload(data_dir)["Testbrot"]
        assert wieder.notes == "Teig war zu weich, 30 g Wasser weniger."

    def test_cancelling_the_notes_dialog_changes_nothing(
        self, window: object, data_dir, dialogs: dict[str, object]
    ) -> None:
        self._store(window, Recipe(name="Testbrot", notes="unverändert"))
        dialogs["notes"] = "verworfen"
        dialogs["accept"] = False
        window._on_recipe_notes("Testbrot")  # type: ignore[attr-defined]

        assert self._reload(data_dir)["Testbrot"].notes == "unverändert"

    def test_overwriting_keeps_notes_and_baking_dates(
        self, window: object, data_dir, dialogs: dict[str, object]
    ) -> None:
        """Beim Überschreiben darf die Rezepthistorie nicht verlorengehen."""
        flour = next(i for i in window._ingredients if i.is_flour)  # type: ignore[attr-defined]
        self._store(
            window,
            Recipe(
                name="Testbrot",
                notes="Erfahrung aus dem letzten Mal.",
                last_baked_on=date(2025, 12, 23),
                last_best_before=date(2025, 12, 30),
            ),
        )

        page = window.page_calculator  # type: ignore[attr-defined]
        page.clear()
        page._items_model.add_item(flour, 1000.0)
        page.spin_baked.setValue(800.0)
        page.txt_name.setText("Testbrot")
        page._recalculate()
        dialogs["name"] = "Testbrot"
        window.btn_save_recipe.click()  # type: ignore[attr-defined]

        wieder = self._reload(data_dir)["Testbrot"]
        assert wieder.notes == "Erfahrung aus dem letzten Mal."
        assert wieder.last_baked_on == date(2025, 12, 23)
        assert wieder.last_best_before == date(2025, 12, 30)
        assert wieder.total_amount_g == pytest.approx(1000.0), "Mengen müssen neu sein"

    @staticmethod
    def _stub_label(monkeypatch: pytest.MonkeyPatch, *, created: bool, baked: date):
        """Ersetzt den Etikettdialog und meldet, womit er aufgerufen wurde."""
        gesehen: dict[str, object] = {}

        class _LabelStub:
            def __init__(self, _analysis: object, **kwargs: object) -> None:
                gesehen.update(kwargs)

            def exec(self) -> int:
                return 1

            label_was_created = created
            baked_on = baked
            best_before = baked + timedelta(days=7)

        monkeypatch.setattr("brotrechner.gui.main_window.LabelDialog", _LabelStub)
        return gesehen

    def _prepare_calculator(self, window: object, name: str) -> None:
        flour = next(i for i in window._ingredients if i.is_flour)  # type: ignore[attr-defined]
        page = window.page_calculator  # type: ignore[attr-defined]
        page.clear()
        page._items_model.add_item(flour, 1000.0)
        page.spin_baked.setValue(800.0)
        page.txt_name.setText(name)
        page._recalculate()

    def test_a_created_label_writes_the_baking_day_to_the_recipe(
        self, window: object, data_dir, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._store(window, Recipe(name="Testbrot", baked_weight_g=800.0))
        self._prepare_calculator(window, "Testbrot")
        self._stub_label(monkeypatch, created=True, baked=date(2026, 3, 1))

        window._on_label()  # type: ignore[attr-defined]

        wieder = self._reload(data_dir)["Testbrot"]
        assert wieder.last_baked_on == date(2026, 3, 1)
        assert wieder.last_best_before == date(2026, 3, 8)

    def test_merely_looking_at_the_dialog_changes_no_date(
        self, window: object, data_dir, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Den Dialog zu öffnen und wieder zu schließen ist kein Backvorgang."""
        self._store(window, Recipe(name="Testbrot", baked_weight_g=800.0))
        self._prepare_calculator(window, "Testbrot")
        self._stub_label(monkeypatch, created=False, baked=date(2026, 3, 1))

        window._on_label()  # type: ignore[attr-defined]

        assert self._reload(data_dir)["Testbrot"].last_baked_on is None

    def test_the_dialog_learns_the_previous_baking_day(
        self, window: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._store(window, Recipe(name="Testbrot", last_baked_on=date(2025, 12, 23)))
        self._prepare_calculator(window, "Testbrot")
        gesehen = self._stub_label(monkeypatch, created=False, baked=date(2026, 3, 1))

        window._on_label()  # type: ignore[attr-defined]

        assert gesehen["last_baked_on"] == date(2025, 12, 23)

    def test_an_unsaved_recipe_is_not_invented(
        self, window: object, data_dir, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Ohne gespeichertes Rezept gibt es nichts fortzuschreiben."""
        self._prepare_calculator(window, "Noch nie gespeichert")
        self._stub_label(monkeypatch, created=True, baked=date(2026, 3, 1))

        window._on_label()  # type: ignore[attr-defined]

        assert "Noch nie gespeichert" not in self._reload(data_dir)
