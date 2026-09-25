"""Unerwartete Fehler werden angezeigt und protokolliert.

Beim Start per Doppelklick gibt es keine Konsole. Bisher verschwand deshalb
jede Ausnahme spurlos: Eine Ausnahme in einem Slot ließ einen Knopf einfach
nicht reagieren, und scheiterte der Aufbau des Hauptfensters, schloss sich das
Programm wortlos.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from collections.abc import Iterator
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from brotrechner.logfile import LOG_FILE, configure_logging, log_path

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def clean_logging() -> Iterator[None]:
    """Stellt die Protokollierung nach dem Test wieder her."""
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield
    for handler in root.handlers[:]:
        if handler not in handlers:
            root.removeHandler(handler)
            handler.close()
    root.setLevel(level)


def _flush() -> None:
    for handler in logging.getLogger().handlers:
        handler.flush()


class TestLogFile:
    def test_messages_land_next_to_the_data(self, tmp_path: Path, clean_logging: None) -> None:
        path = configure_logging(tmp_path)
        logging.getLogger("brotrechner.test").warning("Mehl ist alle")
        _flush()
        assert path == tmp_path / LOG_FILE == log_path(tmp_path)
        assert "Mehl ist alle" in path.read_text(encoding="utf-8")

    def test_configuring_twice_writes_each_message_once(
        self, tmp_path: Path, clean_logging: None
    ) -> None:
        configure_logging(tmp_path)
        path = configure_logging(tmp_path)
        assert path is not None
        logging.getLogger("brotrechner.test").warning("nur einmal")
        _flush()
        assert path.read_text(encoding="utf-8").count("nur einmal") == 1

    def test_without_a_console_only_the_file_remains(
        self, tmp_path: Path, clean_logging: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """So startet Windows ein Programm mit pythonw: ``sys.stderr`` ist ``None``."""
        monkeypatch.setattr(sys, "stderr", None)
        configure_logging(tmp_path)
        ours = [h for h in logging.getLogger().handlers if getattr(h, "_brotrechner_handler", 0)]
        assert [type(h).__name__ for h in ours] == ["RotatingFileHandler"]

    def test_an_unusable_directory_does_not_stop_the_start(
        self, tmp_path: Path, clean_logging: None
    ) -> None:
        blocked = tmp_path / "datei"
        blocked.write_text("x", encoding="utf-8")
        assert configure_logging(blocked) is None

    def test_without_a_data_directory_there_is_no_file(self, clean_logging: None) -> None:
        assert configure_logging(None) is None

    def test_details_only_when_asked(self, tmp_path: Path, clean_logging: None) -> None:
        path = configure_logging(tmp_path)
        assert path is not None
        logging.getLogger("brotrechner.test").debug("leise")
        configure_logging(tmp_path, verbose=True)
        logging.getLogger("brotrechner.test").debug("laut")
        _flush()
        text = path.read_text(encoding="utf-8")
        assert "leise" not in text
        assert "laut" in text


@pytest.fixture
def shown(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, str]]:
    """Fängt jede Meldung ab: (Titel, Text, Einzelheiten)."""
    from PySide6.QtWidgets import QMessageBox

    boxes: list[tuple[str, str, str]] = []

    def record(self: QMessageBox) -> int:
        boxes.append((self.windowTitle(), self.text(), self.detailedText()))
        return 0

    monkeypatch.setattr(QMessageBox, "exec", record)
    # Der Test ersetzt den globalen Hook; monkeypatch setzt ihn danach zurück.
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    return boxes


def _raise(exc: BaseException) -> None:
    """Reicht eine Ausnahme samt Traceback an ``sys.excepthook``, wie Qt es täte."""

    def fail() -> None:
        raise exc

    try:
        fail()
    except BaseException as caught:
        sys.excepthook(type(caught), caught, caught.__traceback__)


@pytest.mark.gui
class TestExceptionHook:
    def test_an_error_is_logged_and_shown(
        self,
        qapp: object,
        tmp_path: Path,
        clean_logging: None,
        shown: list[tuple[str, str, str]],
    ) -> None:
        del qapp
        from brotrechner.gui.errors import install_exception_hook

        log_file = configure_logging(tmp_path)
        install_exception_hook(log_file)
        _raise(ValueError("Teig zu nass"))
        _flush()
        ((title, text, details),) = shown
        assert title == "Unerwarteter Fehler"
        assert "ValueError: Teig zu nass" in text
        assert str(log_file) in text
        assert "Traceback" in details
        assert log_file is not None
        assert "Teig zu nass" in log_file.read_text(encoding="utf-8")

    def test_an_error_in_a_slot_reaches_the_user(
        self, qapp: object, clean_logging: None, shown: list[tuple[str, str, str]]
    ) -> None:
        """Der Alltagsfall: Ein Knopf, dessen Slot scheitert, tat bisher einfach nichts."""
        del qapp
        from PySide6.QtWidgets import QPushButton

        from brotrechner.gui.errors import install_exception_hook

        install_exception_hook(None)
        button = QPushButton()
        button.clicked.connect(lambda: 1 / 0)
        button.click()
        assert len(shown) == 1
        assert "ZeroDivisionError" in shown[0][1]

    def test_ctrl_c_is_passed_on(self, qapp: object, monkeypatch: pytest.MonkeyPatch) -> None:
        del qapp
        from brotrechner.gui.errors import install_exception_hook

        passed: list[type[BaseException]] = []
        monkeypatch.setattr(sys, "excepthook", lambda kind, *_a: passed.append(kind))
        install_exception_hook(None)
        _raise(KeyboardInterrupt())
        assert passed == [KeyboardInterrupt]

    def test_if_the_message_fails_the_old_way_takes_over(
        self, qapp: object, monkeypatch: pytest.MonkeyPatch, clean_logging: None
    ) -> None:
        del qapp
        from PySide6.QtWidgets import QMessageBox

        from brotrechner.gui.errors import install_exception_hook

        passed: list[type[BaseException]] = []
        monkeypatch.setattr(sys, "excepthook", lambda kind, *_a: passed.append(kind))

        def broken(_self: QMessageBox) -> int:
            raise RuntimeError("kein Fenster möglich")

        monkeypatch.setattr(QMessageBox, "exec", broken)
        install_exception_hook(None)
        _raise(ValueError("x"))
        assert passed == [ValueError]

    def test_no_messages_pile_up(
        self,
        qapp: object,
        tmp_path: Path,
        clean_logging: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Scheitert während der Meldung noch etwas, bleibt es beim Protokoll."""
        del qapp
        from PySide6.QtWidgets import QMessageBox

        from brotrechner.gui.errors import install_exception_hook

        monkeypatch.setattr(sys, "excepthook", sys.excepthook)
        texts: list[str] = []

        def show_and_fail_again(self: QMessageBox) -> int:
            texts.append(self.text())
            _raise(RuntimeError("noch einer"))
            return 0

        monkeypatch.setattr(QMessageBox, "exec", show_and_fail_again)
        log_file = configure_logging(tmp_path)
        install_exception_hook(log_file)
        _raise(ValueError("erster"))
        _flush()
        assert len(texts) == 1
        assert log_file is not None
        assert "noch einer" in log_file.read_text(encoding="utf-8")


@pytest.mark.gui
class TestStart:
    def test_a_failing_start_is_shown_and_ends_with_1(
        self,
        qapp: object,
        tmp_path: Path,
        clean_logging: None,
        shown: list[tuple[str, str, str]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Früher schloss sich das Programm dann wortlos."""
        del qapp
        from brotrechner.gui import app, main_window

        def broken(**_kwargs: Any) -> None:
            raise ValueError("'blau' is not a valid ThemeMode")

        monkeypatch.setattr(main_window, "MainWindow", broken)
        assert app.run([], data_dir=tmp_path) == 1
        _flush()
        assert shown[0][0] == "Der Brotrechner konnte nicht starten"
        assert "blau" in shown[0][1]
        assert "blau" in (tmp_path / LOG_FILE).read_text(encoding="utf-8")


def _launcher() -> ModuleType:
    """Lädt den Doppelklick-Starter als Modul."""
    path = ROOT / "Brotrechner starten.pyw"
    loader = SourceFileLoader("brotrechner_starter", str(path))
    spec = importlib.util.spec_from_loader("brotrechner_starter", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class TestLauncher:
    def test_a_crash_is_reported_instead_of_vanishing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from brotrechner.gui import app

        launcher = _launcher()
        reports: list[tuple[str, str]] = []
        monkeypatch.setattr(launcher, "_report", lambda title, text: reports.append((title, text)))

        def crash(*_args: Any, **_kwargs: Any) -> int:
            raise RuntimeError("Qt ließ sich nicht starten")

        monkeypatch.setattr(app, "run", crash)
        assert launcher.main() == 1
        ((title, text),) = reports
        assert title == "Der Brotrechner wurde unerwartet beendet"
        assert "Qt ließ sich nicht starten" in text
        assert LOG_FILE in text


class TestWhereTheLogIs:
    def test_the_command_line_passes_verbose_to_the_interface(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from brotrechner import cli
        from brotrechner.gui import app

        calls: list[dict[str, Any]] = []

        def fake_run(**kwargs: Any) -> int:
            calls.append(kwargs)
            return 7

        monkeypatch.setattr(app, "run", fake_run)
        assert cli.main(["--data-dir", str(tmp_path), "-v"]) == 7
        assert calls == [{"data_dir": tmp_path.resolve(), "verbose": True}]

    @pytest.mark.gui
    def test_the_about_dialog_names_the_log_file(self, qapp: object, tmp_path: Path) -> None:
        del qapp
        from PySide6.QtWidgets import QLabel

        from brotrechner.gui.dialogs.simple_dialogs import AboutDialog

        dialog = AboutDialog(data_dir=str(tmp_path), ingredient_count=1, recipe_count=2)
        texts = " ".join(label.text() for label in dialog.findChildren(QLabel))
        assert str(tmp_path / LOG_FILE) in texts
        dialog.close()
