"""Das Windows-Programmpaket: Datenordner, Startdateien und Selbsttest.

Im Paket liegt das Programm nicht mehr im Quelltextordner. Der „portable“
Datenordner ``data`` gehört dann neben ``Brotrechner.exe`` - und ob Schriften,
PDF-Bibliothek und Startdatenbank mit eingepackt wurden, muss sich am fertigen
Paket prüfen lassen, ohne die Oberfläche zu bedienen.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from brotrechner import __version__, cli, paths
from brotrechner.export import report

ROOT = Path(__file__).resolve().parents[1]


class TestDataFolderOfThePackage:
    @pytest.fixture
    def program(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        """Ein ausgepacktes Programm: ``Brotrechner/Brotrechner.exe``."""
        folder = tmp_path / "Brotrechner"
        folder.mkdir()
        monkeypatch.delenv(paths.DATA_DIR_ENV_VAR, raising=False)
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
        monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "executable", str(folder / "Brotrechner.exe"))
        return folder

    def test_a_data_folder_next_to_the_program_is_used(self, program: Path) -> None:
        (program / "data").mkdir()
        assert paths.data_dir(create=False) == (program / "data").resolve()

    def test_without_it_the_user_folder_is_used(self, program: Path) -> None:
        assert not paths.data_dir(create=False).is_relative_to(program)


class TestSelftest:
    def test_label_and_report_are_written(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        out = tmp_path / "selbsttest"
        assert (
            cli.main(["--data-dir", str(tmp_path / "daten"), "selftest", "--output", str(out)]) == 0
        )
        with Image.open(out / "etikett.png") as image:
            assert image.size[0] > 100
        printed = capsys.readouterr().out
        assert str(out / "etikett.png") in printed
        if report.is_available():
            assert (out / "bericht.pdf").read_bytes().startswith(b"%PDF")
            assert str(out / "bericht.pdf") in printed

    def test_without_a_folder_a_temporary_one_is_used(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import tempfile

        monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
        assert cli.main(["--data-dir", str(tmp_path / "daten"), "selftest"]) == 0
        written = list(tmp_path.glob("brotrechner-selbsttest-*/etikett.png"))
        assert len(written) == 1
        assert str(written[0]) in capsys.readouterr().out

    def test_a_failure_is_reported(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def broken(*_args: object, **_kwargs: object) -> None:
            raise OSError("Schrift fehlt")

        monkeypatch.setattr("brotrechner.cli.render_label", broken)
        code = cli.main(
            ["--data-dir", str(tmp_path / "daten"), "selftest", "--output", str(tmp_path)]
        )
        assert code == 1
        assert "Selbsttest fehlgeschlagen: OSError: Schrift fehlt" in capsys.readouterr().err

    def test_without_reportlab_the_report_is_skipped(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(report, "is_available", lambda: False)
        assert (
            cli.main(["--data-dir", str(tmp_path / "daten"), "selftest", "--output", str(tmp_path)])
            == 0
        )
        assert not (tmp_path / "bericht.pdf").exists()
        assert "übersprungen (reportlab fehlt)" in capsys.readouterr().out


class TestStartFiles:
    """Die Startdateien, aus denen PyInstaller die beiden Programme baut."""

    def test_the_command_line_program_starts(self, tmp_path: Path) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "packaging" / "brotrechner_cli.py"), "--version"],
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
            cwd=tmp_path,
            timeout=60,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == f"brotrechner {__version__}"

    def test_the_window_program_calls_the_interface(self) -> None:
        text = (ROOT / "packaging" / "brotrechner_gui.py").read_text(encoding="utf-8")
        assert "main_gui" in text

    def test_the_interface_gets_the_data_folder(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """So startet ``Brotrechner.exe``: ohne Argumente, mit dem Datenordner des Systems."""
        from brotrechner.gui import app

        calls: list[dict[str, object]] = []

        def fake_run(**kwargs: object) -> int:
            calls.append(kwargs)
            return 3

        monkeypatch.setattr(app, "run", fake_run)
        monkeypatch.setenv(paths.DATA_DIR_ENV_VAR, str(tmp_path))
        assert cli.main_gui() == 3
        assert calls == [{"data_dir": tmp_path}]

    def test_the_spec_builds_both(self) -> None:
        spec = (ROOT / "packaging" / "brotrechner.spec").read_text(encoding="utf-8")
        for expected in (
            "brotrechner_gui.py",
            "brotrechner_cli.py",
            'collect_data_files("brotrechner")',
        ):
            assert expected in spec
