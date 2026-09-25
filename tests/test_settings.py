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

from brotrechner.settings import THEMES, Settings, load_settings


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
            ("last_label_theme", 1),
            ("last_label_size", None),
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
            _JSON,
            max_size=10,
        )
    )
    def test_reading_never_fails_and_every_value_is_usable(self, data: dict[str, Any]) -> None:
        settings = Settings.from_dict(data)
        assert settings.theme in THEMES
        assert isinstance(settings.energy_price, float)
        assert math.isfinite(settings.energy_price)
        assert 0.0 <= settings.energy_price <= 10.0
        for name in ("export_dir", "window_geometry", "last_label_theme", "last_label_size"):
            assert isinstance(getattr(settings, name), str)
        assert isinstance(settings.show_tolerances, bool)


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
