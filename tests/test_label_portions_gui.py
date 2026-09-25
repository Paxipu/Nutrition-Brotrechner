"""Der Etikettdialog bietet die Nährwerte je Portion an, wenn das Rezept eine hat."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from brotrechner.core.analysis import ResolvedItem, analyze
from brotrechner.core.models import Ingredient
from brotrechner.core.portions import Portion
from brotrechner.settings import LabelPreferences

pytestmark = pytest.mark.gui


@pytest.fixture
def make_dialog(
    qapp: object, tmp_path: Path, flour: Ingredient, water: Ingredient, salt: Ingredient
) -> Iterator[Callable[..., Any]]:
    del qapp
    from brotrechner.gui.dialogs.label_dialog import LabelDialog

    created: list[Any] = []

    def build(portion: Portion | None, *, preferences: LabelPreferences | None = None) -> Any:
        analysis = analyze(
            [ResolvedItem(flour, 1000.0), ResolvedItem(water, 700.0), ResolvedItem(salt, 20.0)],
            baked_weight_g=1500.0,
            portion=portion,
        )
        dialog = LabelDialog(
            analysis, recipe_name="Roggenbrot", default_dir=tmp_path, preferences=preferences
        )
        created.append(dialog)
        return dialog

    yield build
    for dialog in created:
        dialog.close()


def test_without_a_portion_there_is_nothing_to_switch(make_dialog: Callable[..., Any]) -> None:
    dialog = make_dialog(None)
    assert not dialog.chk_portion.isEnabled()
    assert "Portion" in dialog.chk_portion.toolTip()
    assert dialog._options(dpi=72).portion is None


def test_a_portion_is_shown_by_default(make_dialog: Callable[..., Any]) -> None:
    dialog = make_dialog(Portion("Scheibe", 50.0))
    assert dialog.chk_portion.isEnabled()
    assert dialog.chk_portion.isChecked()
    assert dialog.chk_portion.text() == "Nährwerte je Scheibe (50 g)"
    assert dialog._options(dpi=72).portion == Portion("Scheibe", 50.0)


def test_it_can_be_switched_off(make_dialog: Callable[..., Any]) -> None:
    dialog = make_dialog(Portion("Scheibe", 50.0))
    dialog.chk_portion.setChecked(False)
    assert dialog._options(dpi=72).portion is None
    assert dialog.preferences().show_portion is False


def test_the_choice_is_remembered(make_dialog: Callable[..., Any]) -> None:
    dialog = make_dialog(Portion("Scheibe", 50.0), preferences=LabelPreferences(show_portion=False))
    assert not dialog.chk_portion.isChecked()
    assert dialog._options(dpi=72).portion is None


def test_a_portion_heavier_than_the_bread_is_not_offered(make_dialog: Callable[..., Any]) -> None:
    """Sonst gäbe es keine sinnvolle Zahl der Portionen - und das Etikett einen Fehler."""
    dialog = make_dialog(Portion("Laib", 2000.0))
    assert not dialog.chk_portion.isEnabled()
    assert "schwerer" in dialog.chk_portion.toolTip()
    assert dialog._options(dpi=72).portion is None
    dialog._render_output()


def test_a_column_that_does_not_fit_is_reported(make_dialog: Callable[..., Any]) -> None:
    from brotrechner.gui.qt_compat import select_data

    dialog = make_dialog(Portion("Kastenweißbrotscheibe", 45.5))
    select_data(dialog.cmb_size, None)
    dialog.spin_width.setValue(30.0)
    dialog.spin_height.setValue(150.0)
    dialog._refresh()
    assert "Spalte je Portion" in dialog.lbl_issues.text()


class TestPreference:
    def test_it_is_on_by_default(self) -> None:
        assert LabelPreferences().show_portion is True

    def test_it_is_read(self) -> None:
        assert LabelPreferences.from_dict({"show_portion": False}).show_portion is False

    def test_a_wrong_type_keeps_the_default(self) -> None:
        assert LabelPreferences.from_dict({"show_portion": "nein"}).show_portion is True
