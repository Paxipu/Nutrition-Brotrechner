"""Einstellungen: robust einlesen.

Die Datei ``settings.json`` lässt sich von Hand bearbeiten. Bisher übernahm das
Programm jeden Wert ungeprüft: ``"theme": "blau"`` ließ den Start mit
``ValueError`` scheitern, ein Strompreis ``"abc"`` scheiterte erst später beim
Rechnen, eine Fenstergeometrie als Zahl beim Wiederherstellen.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from brotrechner.settings import THEMES, LabelPreferences, Settings, load_settings, save_settings


class TestInvalidValues:
    @pytest.mark.parametrize(
        ("key", "value"),
        [
            ("theme", "blau"),
            ("theme", 3),
            ("energy_price", "abc"),
            ("energy_price", True),
            ("energy_price", -0.1),
            ("energy_price", 10.5),
            ("energy_price", None),
            ("export_dir", ["x"]),
            ("window_geometry", 5),
            ("show_tolerances", "ja"),
            ("label", "Etikett"),
            ("label", None),
        ],
    )
    def test_fall_back_to_the_default(self, key: str, value: object) -> None:
        settings = Settings.from_dict({key: value})
        assert getattr(settings, key) == getattr(Settings(), key)

    def test_valid_values_are_kept(self) -> None:
        settings = Settings.from_dict(
            {
                "theme": "dark",
                "energy_price": 1,
                "export_dir": "/tmp/etiketten",
                "window_geometry": "AAAA",
                "show_tolerances": False,
            }
        )
        assert settings.theme == "dark"
        assert settings.energy_price == 1.0
        assert isinstance(settings.energy_price, float)
        assert settings.export_dir == "/tmp/etiketten"
        assert settings.window_geometry == "AAAA"
        assert settings.show_tolerances is False

    def test_one_bad_value_keeps_the_others(self, tmp_path: Path) -> None:
        target = tmp_path / "settings.json"
        target.write_text(json.dumps({"theme": "blau", "energy_price": 0.42}), encoding="utf-8")
        settings = load_settings(target)
        assert settings.theme == "system"
        assert settings.energy_price == pytest.approx(0.42)

    def test_the_themes_match_the_interface(self) -> None:
        from brotrechner.gui.theme import ThemeMode

        assert set(THEMES) == {mode.value for mode in ThemeMode}


_JSON = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats() | st.text(max_size=20),
    lambda children: (
        st.lists(children, max_size=3) | st.dictionaries(st.text(max_size=5), children, max_size=3)
    ),
    max_leaves=10,
)


class TestAnyFile:
    @given(
        data=st.dictionaries(
            st.sampled_from([*Settings.__slots__, "unbekannt"]) | st.text(max_size=8),
            _JSON
            | st.dictionaries(
                st.sampled_from([*LabelPreferences.__slots__, "unbekannt"]), _JSON, max_size=8
            ),
            max_size=10,
        )
    )
    def test_reading_never_fails_and_every_value_is_usable(self, data: dict[str, Any]) -> None:
        settings = Settings.from_dict(data)
        assert settings.theme in THEMES
        assert isinstance(settings.energy_price, float)
        assert math.isfinite(settings.energy_price)
        assert 0.0 <= settings.energy_price <= 10.0
        for name in ("export_dir", "window_geometry"):
            assert isinstance(getattr(settings, name), str)
        assert isinstance(settings.show_tolerances, bool)
        defaults = LabelPreferences()
        for name in LabelPreferences.__slots__:
            assert type(getattr(settings.label, name)) is type(getattr(defaults, name))


@pytest.mark.gui
class TestStart:
    def test_an_unknown_theme_does_not_stop_the_program(
        self, qapp: object, data_dir: Path, dialogs: dict[str, object]
    ) -> None:
        """Früher: ValueError: 'blau' is not a valid ThemeMode - und kein Fenster."""
        del qapp, dialogs
        from brotrechner.gui.main_window import MainWindow

        (data_dir / "settings.json").write_text('{"theme": "blau"}', encoding="utf-8")
        window = MainWindow(data_dir=data_dir)
        window.close()


class TestLabelPreferences:
    def test_they_survive_a_restart(self, tmp_path: Path) -> None:
        target = tmp_path / "settings.json"
        chosen = LabelPreferences(
            size="custom",
            custom_width_mm=105.0,
            custom_height_mm=74.0,
            for_sale=True,
            producer="Backstube Muster\nHauptstraße 1",
            print_mode="sheet",
            sheet_columns=2,
            sheet_next_free=7,
        )
        save_settings(target, Settings(label=chosen))
        assert load_settings(target).label == chosen

    @pytest.mark.parametrize(
        ("key", "value"),
        [
            ("dpi", "300"),
            ("dpi", 300.5),
            ("dpi", True),
            ("dpi", 10**12),
            ("custom_width_mm", float("inf")),
            ("custom_width_mm", -5),
            ("custom_width_mm", "70"),
            ("for_sale", 1),
            ("producer", 42),
            ("sheet_columns", -1),
        ],
    )
    def test_a_bad_value_falls_back_alone(self, key: str, value: object) -> None:
        prefs = LabelPreferences.from_dict({key: value, "footer": "Eigene Fußzeile"})
        assert getattr(prefs, key) == getattr(LabelPreferences(), key)
        assert prefs.footer == "Eigene Fußzeile"

    def test_unknown_keys_are_ignored(self) -> None:
        prefs = LabelPreferences.from_dict({"aus_der_zukunft": 1, "footer": "Eigene"})
        assert prefs == LabelPreferences(footer="Eigene")

    def test_whole_numbers_are_fine_for_millimeters(self) -> None:
        prefs = LabelPreferences.from_dict({"custom_width_mm": 105})
        assert prefs.custom_width_mm == 105.0
        assert isinstance(prefs.custom_width_mm, float)


def _analysis():  # type: ignore[no-untyped-def]
    from brotrechner.core.analysis import ResolvedItem, analyze
    from brotrechner.core.models import Category, Ingredient
    from brotrechner.core.nutrients import Nutrients

    flour = Ingredient(
        name="Weizenmehl Type 550",
        category=Category.FLOUR,
        nutrients=Nutrients(energy_kcal=341, carbs=70.0, protein=11.0, fiber=4.0, water=13.5),
        flour_percent=100.0,
        allergens=frozenset(),
    )
    water = Ingredient(name="Wasser", nutrients=Nutrients(water=100.0), allergens=frozenset())
    return analyze([ResolvedItem(flour, 500), ResolvedItem(water, 350)], baked_weight_g=750)


def _dialog(tmp_path: Path, **kwargs: Any):  # type: ignore[no-untyped-def]
    from brotrechner.gui.dialogs.label_dialog import LabelDialog

    return LabelDialog(_analysis(), recipe_name="Weizenbrot", default_dir=tmp_path, **kwargs)


REMEMBERED = LabelPreferences(
    size="custom",
    custom_width_mm=105.0,
    custom_height_mm=74.0,
    theme="mono",
    dpi=600,
    footer="Backstube Muster",
    show_date=False,
    show_fiber=False,
    show_reference_hint=False,
    for_sale=True,
    producer="Backstube Muster\nHauptstraße 1\n12345 Musterstadt",
    storage_hint="Trocken lagern.",
    print_mode="sheet",
    rotate=False,
    sheet_columns=2,
    sheet_rows=4,
    sheet_margin_left_mm=0.0,
    sheet_margin_top_mm=0.5,
    sheet_gap_x_mm=0.0,
    sheet_gap_y_mm=0.0,
    sheet_next_free=5,
)


@pytest.mark.gui
class TestTheLabelDialogRemembers:
    def test_everything_comes_back(self, qapp: object, tmp_path: Path) -> None:
        del qapp
        from brotrechner.export.label import LabelTheme
        from brotrechner.export.printing import PrintMode

        dialog = _dialog(tmp_path, preferences=REMEMBERED)
        assert dialog.cmb_size.currentData() is None
        assert dialog.cmb_theme.currentData() == LabelTheme.MONO
        assert dialog.cmb_dpi.currentData() == 600
        assert dialog.txt_producer.toPlainText() == REMEMBERED.producer
        assert dialog.print_card.mode() == PrintMode.SHEET
        assert dialog.print_card.spin_first.value() == 5
        assert dialog.preferences() == REMEMBERED
        dialog.close()

    def test_unknown_values_leave_the_defaults(self, qapp: object, tmp_path: Path) -> None:
        del qapp
        from brotrechner.export.label import LabelSize, LabelTheme
        from brotrechner.export.printing import PrintMode

        odd = LabelPreferences(size="riesig", theme="lila", dpi=1234, print_mode="fax")
        dialog = _dialog(tmp_path, preferences=odd)
        assert dialog.cmb_size.currentData() == LabelSize.MEDIUM
        assert dialog.cmb_theme.currentData() == LabelTheme.NATURAL
        assert dialog.cmb_dpi.currentData() == 300
        assert dialog.print_card.mode() == PrintMode.SINGLE
        dialog.close()

    def test_the_shelf_life_comes_from_the_recipe(self, qapp: object, tmp_path: Path) -> None:
        """21 Tage beim letzten Mal - dann auch diesmal, nicht wieder sieben."""
        del qapp
        from datetime import date, timedelta

        dialog = _dialog(
            tmp_path, last_baked_on=date(2026, 9, 1), last_best_before=date(2026, 9, 22)
        )
        assert dialog.chk_best_before.isChecked()
        assert dialog.best_before == date.today() + timedelta(days=21)
        dialog.close()

    def test_an_impossible_shelf_life_is_ignored(self, qapp: object, tmp_path: Path) -> None:
        del qapp
        from datetime import date

        dialog = _dialog(
            tmp_path, last_baked_on=date(2026, 9, 22), last_best_before=date(2026, 9, 1)
        )
        assert not dialog.chk_best_before.isChecked()
        dialog.close()

    def test_the_next_free_label_moves_on_after_printing(
        self, qapp: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Drei Etiketten ab Feld 7 eines Bogens mit acht: Weiter geht es bei Feld 2."""
        del qapp
        from PySide6.QtWidgets import QDialog

        from brotrechner.gui.dialogs import label_dialog

        class _Accepting:
            def __init__(self, *_args: object) -> None:
                pass

            def setWindowTitle(self, _title: str) -> None:  # noqa: N802 - Qt-Vertrag
                pass

            def exec(self) -> QDialog.DialogCode:
                return QDialog.DialogCode.Accepted

        monkeypatch.setattr(label_dialog, "QPrintDialog", _Accepting)
        # 2 × 4 Etiketten von 105 × 74 mm füllen ein A4-Blatt genau.
        prefs = LabelPreferences(
            size="custom",
            custom_width_mm=105.0,
            custom_height_mm=74.0,
            print_mode="sheet",
            sheet_next_free=7,
        )
        dialog = _dialog(tmp_path, preferences=prefs)
        monkeypatch.setattr(dialog, "_paint_to_printer", lambda _printer: None)
        dialog.print_card.spin_count.setValue(3)
        dialog._on_print()
        assert dialog.preferences().sheet_next_free == 2
        dialog.close()


@pytest.mark.gui
class TestTheMainWindowRemembers:
    def test_the_energy_price_survives_a_restart(
        self, qapp: object, data_dir: Path, dialogs: dict[str, object]
    ) -> None:
        """Bisher begann der Rechner bei jedem Start wieder mit der Vorgabe."""
        del qapp, dialogs
        from brotrechner.gui.main_window import MainWindow

        first = MainWindow(data_dir=data_dir)
        first.page_calculator.spin_price.setValue(0.55)
        first.close()
        second = MainWindow(data_dir=data_dir)
        assert second.page_calculator.spin_price.value() == pytest.approx(0.55)
        second.close()

    def test_the_output_folder_can_be_chosen(
        self,
        qapp: object,
        data_dir: Path,
        dialogs: dict[str, object],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        del qapp, dialogs
        from PySide6.QtWidgets import QFileDialog

        from brotrechner.gui.main_window import MainWindow

        target = tmp_path / "Etiketten"
        target.mkdir()
        monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *_a: str(target))
        window = MainWindow(data_dir=data_dir)
        window._on_choose_export_dir()
        assert window._export_dir() == target
        assert load_settings(data_dir / "settings.json").export_dir == str(target)
        window.close()

    def test_cancelling_keeps_the_folder(
        self,
        qapp: object,
        data_dir: Path,
        dialogs: dict[str, object],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        del qapp, dialogs
        from PySide6.QtWidgets import QFileDialog

        from brotrechner.gui.main_window import MainWindow

        monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *_a: "")
        window = MainWindow(data_dir=data_dir)
        window._on_choose_export_dir()
        assert window._settings.export_dir == ""
        window.close()

    def test_the_label_settings_are_passed_on_and_kept(
        self,
        qapp: object,
        data_dir: Path,
        dialogs: dict[str, object],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        del qapp, dialogs
        from brotrechner.gui.main_window import MainWindow

        seen: list[dict[str, object]] = []

        class _Stub:
            def __init__(self, _analysis: object, **kwargs: object) -> None:
                seen.append(kwargs)

            def exec(self) -> int:
                return 0

            def preferences(self) -> LabelPreferences:
                return REMEMBERED

            label_was_created = False

        monkeypatch.setattr("brotrechner.gui.main_window.LabelDialog", _Stub)
        window = MainWindow(data_dir=data_dir)
        flour = next(i for i in window._ingredients if i.is_flour)
        page = window.page_calculator
        page._items_model.add_item(flour, 1000.0)
        page.spin_baked.setValue(800.0)
        page._recalculate()
        window._on_label()
        window._on_label()
        assert seen[0]["preferences"] == LabelPreferences()
        assert seen[1]["preferences"] == REMEMBERED
        assert load_settings(data_dir / "settings.json").label == REMEMBERED
        window.close()
