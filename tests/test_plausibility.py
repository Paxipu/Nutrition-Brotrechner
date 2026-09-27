"""Plausibilitätsprüfung der Prozessdaten: Gewichte, die nicht stimmen können.

Ein Tippfehler beim Brotgewicht - 75 statt 750 g - ergab bisher ohne jede
Warnung 2273 kcal je 100 g, mehr als reines Fett haben kann, und landete so
auf dem Etikett. Ein Brot, das schwerer als sein Teig ist, fiel ebenso wenig
auf.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from brotrechner.core.analysis import RecipeAnalysis, ResolvedItem, analyze
from brotrechner.core.models import Category, Ingredient
from brotrechner.core.nutrients import Nutrients
from brotrechner.core.plausibility import (
    MAX_BAKE_LOSS_PERCENT,
    MIN_BAKE_LOSS_PERCENT,
    ProcessFinding,
    check_process,
    has_errors,
)
from brotrechner.core.validation import Severity


def flour() -> Ingredient:
    return Ingredient(
        name="Weizenmehl Type 550",
        category=Category.FLOUR,
        nutrients=Nutrients(
            energy_kcal=341, fat=1.0, carbs=70.0, protein=11.0, fiber=4.0, water=13.5
        ),
        flour_percent=100.0,
    )


def water() -> Ingredient:
    return Ingredient(name="Wasser", nutrients=Nutrients(water=100.0))


def salt() -> Ingredient:
    return Ingredient(name="Salz", nutrients=Nutrients(salt=100.0))


def bread(baked: float, dough: float = 0.0) -> list[ProcessFinding]:
    """500 g Mehl, 350 g Wasser, 10 g Salz - 860 g Teig."""
    items = [ResolvedItem(flour(), 500.0), ResolvedItem(water(), 350.0), ResolvedItem(salt(), 10.0)]
    return check_process(analyze(items, baked_weight_g=baked, dough_weight_g=dough))


def codes(findings: list[ProcessFinding]) -> dict[str, Severity]:
    return {f.code: f.severity for f in findings}


class TestNormalBread:
    def test_a_normal_bread_has_no_findings(self) -> None:
        assert bread(750.0) == []

    def test_a_measured_dough_with_some_left_in_the_bowl_is_fine(self) -> None:
        assert bread(740.0, dough=850.0) == []

    def test_an_empty_recipe_has_no_findings(self) -> None:
        assert check_process(analyze([], baked_weight_g=500.0)) == []

    def test_without_a_baked_weight_there_is_nothing_to_judge(self) -> None:
        assert bread(0.0) == []


class TestImpossibleWeights:
    def test_the_typo_from_the_report(self) -> None:
        """75 statt 750 g: Mehr Wasser verdunstet, als im Teig war."""
        found = codes(bread(75.0))
        assert found["below_dry_mass"] is Severity.ERROR

    def test_a_bread_heavier_than_its_dough(self) -> None:
        found = codes(bread(7500.0))
        assert found["baked_heavier"] is Severity.ERROR

    def test_the_messages_name_both_weights(self) -> None:
        finding = next(f for f in bread(75.0) if f.code == "below_dry_mass")
        assert "75 g" in finding.message
        assert "Trockenmasse" in finding.message

    def test_the_energy_is_not_reported_twice(self) -> None:
        """Die zu hohen Nährwerte folgen aus dem Gewicht - eine Meldung genügt."""
        assert "energy_impossible" not in codes(bread(75.0))

    def test_errors_are_recognised(self) -> None:
        assert has_errors(bread(75.0))
        assert not has_errors(bread(750.0))


class TestImpossibleEnergy:
    def test_more_than_pure_fat_is_an_error(self) -> None:
        """Ein Tippfehler in den Zutatendaten, nicht im Gewicht."""
        broken = Ingredient(name="Kaputt", nutrients=Nutrients(energy_kcal=5000.0, water=5.0))
        items = [ResolvedItem(flour(), 500.0), ResolvedItem(broken, 100.0)]
        found = codes(check_process(analyze(items, baked_weight_g=540.0)))
        assert found["energy_impossible"] is Severity.ERROR


class TestUnusualWeights:
    def test_no_loss_at_all_is_unusual(self) -> None:
        found = codes(bread(860.0))
        assert found["bake_loss"] is Severity.WARNING
        assert "baked_heavier" not in found

    def test_a_very_high_loss_is_unusual(self) -> None:
        found = codes(bread(500.0))
        assert found["bake_loss"] is Severity.WARNING
        assert not has_errors(bread(500.0))

    @pytest.mark.parametrize("loss", [MIN_BAKE_LOSS_PERCENT, MAX_BAKE_LOSS_PERCENT])
    def test_the_limits_themselves_are_fine(self, loss: float) -> None:
        assert bread(860.0 * (1 - loss / 100.0)) == []

    def test_a_dough_heavier_than_its_ingredients(self) -> None:
        found = codes(bread(800.0, dough=900.0))
        assert found["dough_heavier"] is Severity.WARNING

    def test_a_dough_much_lighter_than_its_ingredients(self) -> None:
        found = codes(bread(600.0, dough=700.0))
        assert found["dough_loss"] is Severity.WARNING

    def test_a_dough_typo_is_found(self) -> None:
        """8600 statt 860 g Rohteig skaliert alle Mengen auf das Zehnfache."""
        found = codes(bread(750.0, dough=8600.0))
        assert found["dough_heavier"] is Severity.WARNING
        assert found["below_dry_mass"] is Severity.ERROR


class TestProperties:
    @given(
        flour_g=st.floats(min_value=100.0, max_value=5000.0),
        hydration=st.floats(min_value=0.5, max_value=1.0),
        loss=st.floats(min_value=MIN_BAKE_LOSS_PERCENT, max_value=MAX_BAKE_LOSS_PERCENT),
    )
    def test_a_plausible_bread_is_never_flagged(
        self, flour_g: float, hydration: float, loss: float
    ) -> None:
        items = [ResolvedItem(flour(), flour_g), ResolvedItem(water(), flour_g * hydration)]
        dough = flour_g * (1 + hydration)
        result = analyze(items, baked_weight_g=dough * (1 - loss / 100.0))
        assert check_process(result) == []

    @given(baked=st.floats(min_value=0.1, max_value=100_000.0))
    def test_any_baked_weight_gives_a_clear_answer(self, baked: float) -> None:
        """Nie ein Absturz, und nie ein Etikett aus einem unmöglichen Gewicht."""
        findings = bread(baked)
        dry_mass = 860.0 - (350.0 + 500.0 * 0.135)
        if baked < dry_mass - 1e-6 or baked > 860.0 + 1e-6:
            assert has_errors(findings)


def _analysis(baked: float) -> RecipeAnalysis:
    items = [ResolvedItem(flour(), 500.0), ResolvedItem(water(), 350.0), ResolvedItem(salt(), 10.0)]
    return analyze(items, baked_weight_g=baked)


@pytest.mark.gui
class TestCalculatorShowsFindings:
    @pytest.fixture
    def page(self, qapp: object) -> Iterator[object]:
        del qapp
        from brotrechner.gui.pages.calculator import CalculatorPage
        from brotrechner.gui.theme import ThemeMode, resolve_tokens

        widget = CalculatorPage(resolve_tokens(ThemeMode.LIGHT))
        widget.set_ingredients([flour(), water(), salt()])
        widget._items_model.set_items(
            [ResolvedItem(flour(), 500.0), ResolvedItem(water(), 350.0), ResolvedItem(salt(), 10.0)]
        )
        yield widget
        widget.close()

    def test_a_typo_is_shown_at_once(self, page: object) -> None:
        page.spin_baked.setValue(75.0)  # type: ignore[attr-defined]
        page._recalculate()  # type: ignore[attr-defined]
        assert not page.lbl_process.isHidden()  # type: ignore[attr-defined]
        assert "Trockenmasse" in page.lbl_process.text()  # type: ignore[attr-defined]
        assert "unmöglich" in page.stat_weight._hint.text()  # type: ignore[attr-defined]

    def test_a_plausible_weight_shows_nothing(self, page: object) -> None:
        page.spin_baked.setValue(750.0)  # type: ignore[attr-defined]
        page._recalculate()  # type: ignore[attr-defined]
        assert page.lbl_process.isHidden()  # type: ignore[attr-defined]


@pytest.mark.gui
class TestLabelDialogRefuses:
    @pytest.fixture
    def warnings(self, monkeypatch: pytest.MonkeyPatch) -> list[str]:
        from PySide6.QtWidgets import QMessageBox

        shown: list[str] = []
        monkeypatch.setattr(QMessageBox, "warning", lambda _p, title, *_r: shown.append(title))
        monkeypatch.setattr(QMessageBox, "information", lambda *_a: None)
        return shown

    def _dialog(self, baked: float, tmp_path: Path) -> Any:
        from brotrechner.gui.dialogs.label_dialog import LabelDialog

        return LabelDialog(_analysis(baked), recipe_name="Probe", default_dir=tmp_path)

    def test_an_impossible_weight_writes_no_file(
        self, qapp: object, tmp_path: Path, warnings: list[str]
    ) -> None:
        del qapp
        dialog = self._dialog(75.0, tmp_path)
        dialog._on_save()
        assert list(tmp_path.iterdir()) == []
        assert not dialog.label_was_created
        assert warnings == ["Etikett nicht erstellt"]
        dialog.close()

    def test_an_impossible_weight_is_not_printed(
        self, qapp: object, tmp_path: Path, warnings: list[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        del qapp
        from brotrechner.gui.dialogs import label_dialog

        def forbidden(*_args: object) -> None:
            raise AssertionError("Der Druckdialog hätte nicht erscheinen dürfen")

        monkeypatch.setattr(label_dialog, "QPrintDialog", forbidden)
        dialog = self._dialog(75.0, tmp_path)
        dialog._on_print()
        assert not dialog.label_was_created
        assert warnings
        dialog.close()

    def test_the_findings_are_visible_in_the_dialog(self, qapp: object, tmp_path: Path) -> None:
        del qapp
        dialog = self._dialog(75.0, tmp_path)
        assert not dialog.lbl_issues.isHidden()
        assert "Trockenmasse" in dialog.lbl_issues.text()
        dialog.close()

    def test_a_plausible_bread_is_saved(
        self, qapp: object, tmp_path: Path, warnings: list[str]
    ) -> None:
        del qapp
        dialog = self._dialog(750.0, tmp_path)
        assert dialog.lbl_issues.isHidden()
        dialog._on_save()
        assert dialog.label_was_created
        assert len(list(tmp_path.glob("*.png"))) == 1
        assert warnings == []
        dialog.close()
