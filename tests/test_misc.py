"""Tests der kleineren Bausteine: Formatierung, Referenzmengen, Pfade, Einstellungen."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from brotrechner import paths
from brotrechner.core.reference import (
    DGE_FIBER_REFERENCE_G,
    REFERENCE_INTAKES,
    TRAFFIC_LIGHT_THRESHOLDS,
    AmpelLevel,
    reference_intake_percent,
    traffic_light,
)
from brotrechner.i18n import (
    NUTRIENT_LABELS,
    NUTRIENT_ORDER,
    NUTRIENT_UNITS,
    decimals_for,
    format_currency,
    format_number,
    parse_number,
)
from brotrechner.settings import Settings, load_settings, save_settings


class TestNumberFormatting:
    @pytest.mark.parametrize(
        ("value", "decimals", "expected"),
        [
            (1234.5, 1, "1234,5"),
            (0.005, 2, "0,01"),
            (0.0, 1, "0,0"),
            (-2.5, 1, "-2,5"),
            (317.0, 0, "317"),
        ],
    )
    def test_german_decimal_comma(self, value: float, decimals: int, expected: str) -> None:
        assert format_number(value, decimals) == expected

    def test_currency(self) -> None:
        assert format_currency(1.5) == "1,50 €"

    @pytest.mark.parametrize(
        ("text", "expected"),
        [("1,5", 1.5), ("1.5", 1.5), ("  2 ", 2.0), ("", 0.0), ("-3,25", -3.25), ("1 000", 1000.0)],
    )
    def test_parse_accepts_both_separators(self, text: str, expected: float) -> None:
        assert parse_number(text) == pytest.approx(expected)

    @pytest.mark.parametrize("text", ["viel", "1,2,3", "€"])
    def test_parse_rejects_nonsense(self, text: str) -> None:
        with pytest.raises(ValueError):
            parse_number(text)

    def test_decimals_per_field(self) -> None:
        assert decimals_for("energy_kcal") == 0
        assert decimals_for("salt") == 2
        assert decimals_for("fat") == 1

    def test_every_ordered_field_has_a_label_and_unit(self) -> None:
        for field in NUTRIENT_ORDER:
            assert NUTRIENT_LABELS[field]
            assert NUTRIENT_UNITS[field]

    def test_order_matches_the_regulation(self) -> None:
        """Anhang XV VO (EU) Nr. 1169/2011 gibt die Reihenfolge vor."""
        assert NUTRIENT_ORDER[:5] == (
            "energy_kcal",
            "fat",
            "saturated_fat",
            "carbs",
            "sugar",
        )
        assert NUTRIENT_ORDER[-1] == "salt"


class TestTrafficLight:
    @pytest.mark.parametrize(
        ("field", "value", "level"),
        [
            ("fat", 3.0, AmpelLevel.LOW),
            ("fat", 3.01, AmpelLevel.MEDIUM),
            ("fat", 17.5, AmpelLevel.MEDIUM),
            ("fat", 17.6, AmpelLevel.HIGH),
            ("saturated_fat", 1.5, AmpelLevel.LOW),
            ("saturated_fat", 6.0, AmpelLevel.HIGH),
            ("sugar", 5.0, AmpelLevel.LOW),
            ("sugar", 23.0, AmpelLevel.HIGH),
            ("salt", 0.3, AmpelLevel.LOW),
            ("salt", 1.0, AmpelLevel.MEDIUM),
            ("salt", 2.21, AmpelLevel.HIGH),
        ],
    )
    def test_thresholds(self, field: str, value: float, level: AmpelLevel) -> None:
        assert traffic_light(field, value) is level

    def test_fields_without_a_light(self) -> None:
        assert traffic_light("protein", 50.0) is AmpelLevel.NONE
        assert traffic_light("fiber", 10.0) is AmpelLevel.NONE

    def test_levels_carry_a_label(self) -> None:
        assert AmpelLevel.HIGH.label == "hoch"
        assert AmpelLevel.NONE.label == ""

    def test_all_threshold_fields_are_nutrients(self) -> None:
        assert set(TRAFFIC_LIGHT_THRESHOLDS) <= set(NUTRIENT_LABELS)


class TestReferenceIntake:
    def test_energy(self) -> None:
        assert reference_intake_percent("energy_kcal", 200.0) == pytest.approx(10.0)

    def test_salt(self) -> None:
        assert reference_intake_percent("salt", 3.0) == pytest.approx(50.0)

    def test_fiber_uses_the_dge_value(self) -> None:
        """Ballaststoffe haben keine EU-Referenzmenge."""
        assert "fiber" not in REFERENCE_INTAKES
        assert reference_intake_percent("fiber", DGE_FIBER_REFERENCE_G) == pytest.approx(100.0)

    def test_unknown_field_returns_none(self) -> None:
        assert reference_intake_percent("water", 50.0) is None

    def test_reference_values_match_annex_xiii(self) -> None:
        assert REFERENCE_INTAKES == {
            "energy_kcal": 2000.0,
            "fat": 70.0,
            "saturated_fat": 20.0,
            "carbs": 260.0,
            "sugar": 90.0,
            "protein": 50.0,
            "salt": 6.0,
        }


class TestPaths:
    def test_environment_variable_wins(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "eigenes"
        monkeypatch.setenv(paths.DATA_DIR_ENV_VAR, str(target))
        assert paths.data_dir() == target
        assert target.is_dir()

    def test_derived_paths(self, data_dir: Path) -> None:
        assert paths.ingredients_path() == data_dir / paths.INGREDIENTS_FILE
        assert paths.recipes_path() == data_dir / paths.RECIPES_FILE
        assert paths.settings_path() == data_dir / paths.SETTINGS_FILE

    def test_backup_dir_is_created(self, data_dir: Path) -> None:
        assert paths.backup_dir().is_dir()

    def test_backup_dir_follows_an_explicit_base(self, tmp_path: Path) -> None:
        """Mit --data-dir müssen die Sicherungen dort landen, nicht im Standardort."""
        assert paths.backup_dir(tmp_path) == tmp_path / "backups"

    def test_backup_dir_can_be_probed_without_creating(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(paths.DATA_DIR_ENV_VAR, str(tmp_path / "neu"))
        assert not paths.backup_dir(create=False).exists()

    def test_export_dir_is_a_path(self, data_dir: Path) -> None:
        assert isinstance(paths.default_export_dir(), Path)

    def test_data_dir_without_creating(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "nichtangelegt"
        monkeypatch.setenv(paths.DATA_DIR_ENV_VAR, str(target))
        assert paths.data_dir(create=False) == target
        assert not target.exists()


class TestSettings:
    def test_defaults(self) -> None:
        settings = Settings()
        assert settings.theme == "system"
        assert settings.show_tolerances

    def test_roundtrip(self, tmp_path: Path) -> None:
        target = tmp_path / "settings.json"
        save_settings(target, Settings(theme="dark", energy_price=0.42))
        loaded = load_settings(target)
        assert loaded.theme == "dark"
        assert loaded.energy_price == pytest.approx(0.42)

    def test_missing_file_yields_defaults(self, tmp_path: Path) -> None:
        assert load_settings(tmp_path / "weg.json").theme == "system"

    def test_broken_file_yields_defaults(self, tmp_path: Path) -> None:
        """Kaputte Einstellungen dürfen den Programmstart nicht verhindern."""
        target = tmp_path / "settings.json"
        target.write_text("{kaputt", encoding="utf-8")
        assert load_settings(target).theme == "system"

    def test_unknown_keys_are_ignored(self, tmp_path: Path) -> None:
        target = tmp_path / "settings.json"
        target.write_text(json.dumps({"theme": "light", "aus_der_zukunft": 1}), encoding="utf-8")
        assert load_settings(target).theme == "light"

    def test_non_object_file_yields_defaults(self, tmp_path: Path) -> None:
        target = tmp_path / "settings.json"
        target.write_text("[]", encoding="utf-8")
        assert load_settings(target).theme == "system"

    def test_saving_creates_the_directory(self, tmp_path: Path) -> None:
        target = tmp_path / "tief" / "settings.json"
        save_settings(target, Settings())
        assert target.exists()


class TestProperties:
    @given(st.floats(min_value=-1e6, max_value=1e6, allow_nan=False), st.integers(0, 4))
    def test_format_and_parse_roundtrip(self, value: float, decimals: int) -> None:
        text = format_number(value, decimals)
        assert parse_number(text) == pytest.approx(value, abs=10**-decimals)

    @given(
        st.sampled_from(sorted(TRAFFIC_LIGHT_THRESHOLDS)),
        st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
    )
    def test_traffic_light_is_monotonic(self, field: str, value: float) -> None:
        """Mehr vom Nährstoff darf die Bewertung nie verbessern."""
        order = {AmpelLevel.LOW: 0, AmpelLevel.MEDIUM: 1, AmpelLevel.HIGH: 2}
        assert order[traffic_light(field, value)] <= order[traffic_light(field, value + 1.0)]
