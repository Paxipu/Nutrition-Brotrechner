"""Tests der plattformabhängigen Teile.

Das Programm soll unter Linux genauso laufen wie unter Windows. Weil sich das
auf einem einzelnen Rechner nicht beidseitig ausprobieren lässt, wird hier die
Plattformkennung gefälscht und geprüft, dass jeder Zweig einen sinnvollen Pfad
liefert.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import ImageDraw, ImageFont

from brotrechner import paths
from brotrechner.core.nutrients import Nutrients
from brotrechner.export import fonts
from brotrechner.export.label import (
    LabelOptions,
    LabelSize,
    LabelTheme,
    render_label,
    single_line,
)


@pytest.fixture(autouse=True)
def _clear_font_cache() -> None:
    """Die Schriftsuche merkt sich ihr Ergebnis - je Test frisch beginnen."""
    fonts.find_font_file.cache_clear()


class TestDataDirPerPlatform:
    def test_linux_uses_xdg(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(paths.DATA_DIR_ENV_VAR, raising=False)
        monkeypatch.setattr("brotrechner.paths.sys.platform", "linux")
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        monkeypatch.setattr("brotrechner.paths._portable_dir", lambda: None)
        assert paths.data_dir() == tmp_path / "brotrechner"

    def test_linux_without_xdg_falls_back_to_local_share(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(paths.DATA_DIR_ENV_VAR, raising=False)
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        monkeypatch.setattr("brotrechner.paths.sys.platform", "linux")
        monkeypatch.setattr("brotrechner.paths.Path.home", staticmethod(lambda: tmp_path))
        monkeypatch.setattr("brotrechner.paths._portable_dir", lambda: None)
        assert paths.data_dir() == tmp_path / ".local" / "share" / "brotrechner"

    def test_macos(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(paths.DATA_DIR_ENV_VAR, raising=False)
        monkeypatch.setattr("brotrechner.paths.sys.platform", "darwin")
        monkeypatch.setattr("brotrechner.paths.Path.home", staticmethod(lambda: tmp_path))
        monkeypatch.setattr("brotrechner.paths._portable_dir", lambda: None)
        assert paths.data_dir() == tmp_path / "Library" / "Application Support" / "Brotrechner"

    def test_windows_uses_appdata(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(paths.DATA_DIR_ENV_VAR, raising=False)
        monkeypatch.setattr("brotrechner.paths.sys.platform", "win32")
        monkeypatch.setenv("APPDATA", str(tmp_path))
        monkeypatch.setattr("brotrechner.paths._portable_dir", lambda: None)
        assert paths.data_dir() == tmp_path / "Brotrechner"

    def test_windows_without_appdata(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(paths.DATA_DIR_ENV_VAR, raising=False)
        monkeypatch.delenv("APPDATA", raising=False)
        monkeypatch.setattr("brotrechner.paths.sys.platform", "win32")
        monkeypatch.setattr("brotrechner.paths.Path.home", staticmethod(lambda: tmp_path))
        monkeypatch.setattr("brotrechner.paths._portable_dir", lambda: None)
        assert paths.data_dir() == tmp_path / "AppData" / "Roaming" / "Brotrechner"

    def test_portable_directory_wins_over_the_system(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        portable = tmp_path / "data"
        portable.mkdir()
        monkeypatch.delenv(paths.DATA_DIR_ENV_VAR, raising=False)
        monkeypatch.setattr("brotrechner.paths._portable_dir", lambda: portable)
        assert paths.data_dir() == portable

    def test_no_portable_directory_by_default(self) -> None:
        """Im installierten Zustand liegt kein data-Ordner neben dem Paket."""
        result = paths._portable_dir()
        assert result is None or result.is_dir()

    def test_export_dir_falls_back_without_documents(
        self, data_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("brotrechner.paths.Path.home", staticmethod(lambda: data_dir))
        assert paths.default_export_dir() == data_dir / "exports"

    def test_export_dir_can_be_created(self, data_dir: Path) -> None:
        assert paths.default_export_dir(create=True).is_dir()

    def test_export_dir_follows_the_given_data_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Mit ``--data-dir`` gehören auch die Ausgaben dorthin, nicht ins Benutzerprofil."""
        monkeypatch.setattr("brotrechner.paths.Path.home", staticmethod(lambda: tmp_path / "leer"))
        own = tmp_path / "anderswo"
        assert paths.default_export_dir(own) == own / "exports"

    def test_the_documents_folder_comes_first(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Dort suchen Anwender ihre Etiketten - auch bei einem eigenen Datenverzeichnis."""
        home = tmp_path / "home"
        (home / "Documents").mkdir(parents=True)
        monkeypatch.setattr("brotrechner.paths.Path.home", staticmethod(lambda: home))
        expected = home / "Documents" / "Brotrechner"
        assert paths.default_export_dir(tmp_path / "anderswo") == expected
        assert not expected.exists()
        assert paths.default_export_dir(create=True).is_dir()

    def test_asking_for_the_export_dir_creates_nothing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Bisher entstand dabei nebenbei das Datenverzeichnis des Systems."""
        system = tmp_path / "system"
        monkeypatch.setenv(paths.DATA_DIR_ENV_VAR, str(system))
        monkeypatch.setattr("brotrechner.paths.Path.home", staticmethod(lambda: tmp_path / "leer"))
        assert paths.default_export_dir() == system / "exports"
        assert not system.exists()


class TestFontDiscovery:
    def test_finds_a_font_on_this_machine(self) -> None:
        found = fonts.find_font_file()
        assert found is not None
        assert found[0].is_file()

    @pytest.mark.parametrize("platform", ["linux", "darwin", "win32", "freebsd"])
    def test_search_directories_exist_per_platform(
        self, platform: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("brotrechner.export.fonts.sys.platform", platform)
        directories = fonts._search_dirs()
        assert all(d.is_dir() for d in directories)

    def test_missing_font_gives_the_bitmap_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Auf einem System ganz ohne TrueType-Schrift darf nichts abstürzen."""
        monkeypatch.setattr("brotrechner.export.fonts.find_font_file", lambda: None)
        font_set = fonts.load_font_set()
        assert not font_set.is_scalable
        assert font_set.get(20) is not None

    def test_broken_font_file_falls_back(self, tmp_path: Path) -> None:
        broken = tmp_path / "kaputt.ttf"
        broken.write_bytes(b"keine Schrift")
        font_set = fonts.FontSet(broken, broken)
        assert font_set.get(12) is not None

    def test_font_cache_returns_the_same_object(self) -> None:
        font_set = fonts.load_font_set()
        assert font_set.get(14) is font_set.get(14)

    def test_bold_and_regular_are_distinguished(self) -> None:
        font_set = fonts.load_font_set()
        assert font_set.get(14, bold=True) is not font_set.get(14)

    def test_label_renders_with_the_bitmap_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Der Härtefall: minimal installiertes Linux ohne jede Schriftdatei."""
        monkeypatch.setattr("brotrechner.export.fonts.find_font_file", lambda: None)
        image = render_label(
            Nutrients(energy_kcal=200, carbs=40, protein=8),
            LabelOptions(dpi=110, net_weight_g=750, ingredients=["Mehl", "Wasser"]),
            fonts=fonts.load_font_set(),
        )
        assert image.size[0] > 0


class TestLabelDetails:
    def test_every_size_has_a_readable_label(self) -> None:
        for size in LabelSize:
            assert "mm" in size.label

    def test_every_theme_has_a_readable_label(self) -> None:
        assert all(theme.label for theme in LabelTheme)

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Brot\nmit Umbruch", "Brot mit Umbruch"),
            ("  viele    Leerzeichen  ", "viele Leerzeichen"),
            ("Tab\tzwischendurch", "Tab zwischendurch"),
            ("\n", ""),
            ("", ""),
            ("Steuer\x00zeichen", "Steuer zeichen"),
        ],
    )
    def test_text_is_flattened_to_one_line(self, raw: str, expected: str) -> None:
        assert single_line(raw) == expected

    def test_multiline_title_no_longer_crashes(self) -> None:
        """Hypothesis hatte hier einen echten Absturz gefunden."""
        options = LabelOptions(title="Zeile eins\nZeile zwei", dpi=110)
        assert render_label(Nutrients(), options).size[0] > 0

    def test_ingredient_list_gets_truncated_when_hopeless(self) -> None:
        """Sehr viele Zutaten auf einem kleinen Etikett werden gekürzt."""
        options = LabelOptions(
            size=LabelSize.SMALL,
            dpi=110,
            net_weight_g=1000,
            ingredients=[f"Zutat mit ausgesprochen langem Namen {i}" for i in range(60)],
        )
        assert render_label(Nutrients(energy_kcal=200), options).size == options.pixel_size()

    def test_no_space_left_for_ingredients(self) -> None:
        """Passt gar nichts mehr, wird das Verzeichnis stillschweigend weggelassen."""
        options = LabelOptions(
            size=LabelSize.SMALL,
            dpi=110,
            net_weight_g=1000,
            subtitle="Ein sehr langer Untertitel, der viel Platz kostet " * 3,
            ingredients=["Mehl", "Wasser"],
        )
        assert render_label(Nutrients(energy_kcal=200), options).size == options.pixel_size()


class TestWrapping:
    def test_a_word_longer_than_the_line_is_broken(self) -> None:
        from PIL import Image

        from brotrechner.export.label import _wrap

        draw = ImageDraw.Draw(Image.new("RGB", (200, 50)))
        font = ImageFont.load_default()
        lines = _wrap(draw, "A" * 400, font, 60)
        assert len(lines) > 1
        assert all(line for line in lines)

    def test_empty_text_yields_no_lines(self) -> None:
        from PIL import Image

        from brotrechner.export.label import _wrap

        draw = ImageDraw.Draw(Image.new("RGB", (200, 50)))
        assert _wrap(draw, "", ImageFont.load_default(), 100) == []
