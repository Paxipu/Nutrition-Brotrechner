"""Das Prüfskript selbst: Es muss überall laufen, wo die CI läuft.

Die Prüfschritte werden hier durch einen einzigen kleinen Befehl ersetzt;
geprüft wird nur, was ``main`` daraus macht.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: Startet ``main`` mit einem Prüfschritt, der den übergebenen Befehl ausführt.
_RUN_ONE_STEP = """
import sys
sys.path.insert(0, "tools")
import quality_gate

step = quality_gate.Step("Übung", [sys.executable, "-c", sys.argv[1]], "So geht es weiter.")
quality_gate.build_steps = lambda **_: [step]
sys.argv = ["quality_gate.py"]
raise SystemExit(quality_gate.main())
"""


def _run(step_code: str, **env: str) -> subprocess.CompletedProcess[bytes]:
    # Mit PYTHONUNBUFFERED puffert Python nie; in der CI ist es nicht gesetzt.
    inherited = {key: value for key, value in os.environ.items() if key != "PYTHONUNBUFFERED"}
    return subprocess.run(
        [sys.executable, "-c", _RUN_ONE_STEP, step_code],
        capture_output=True,
        cwd=ROOT,
        env={**inherited, **env},
        check=False,
        timeout=60,
    )


def test_the_output_survives_a_windows_code_page() -> None:
    """Unter Windows schreibt Python in eine Pipe in cp1252 - dort gibt es kein „─“.

    Die CI brach deshalb schon an der ersten Überschrift ab. Die Prüfschritte
    schreiben in dieselbe Ausgabe und müssen dieselbe Kodierung verwenden.
    """
    result = _run("print('Schritt ─ fertig')", PYTHONIOENCODING="cp1252")
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    output = result.stdout.decode("utf-8")
    assert "── Übung ─" in output
    assert "Schritt ─ fertig" in output
    assert "ERGEBNIS: alles grün." in output


def test_each_heading_comes_before_its_step() -> None:
    """In eine Pipe puffert Python - ohne Leeren stand die Überschrift erst am Ende."""
    result = _run("print('Ausgabe des Schritts')")
    output = result.stdout.decode("utf-8")
    assert output.index("── Übung") < output.index("Ausgabe des Schritts")


def test_a_failing_step_fails_the_run() -> None:
    result = _run("raise SystemExit(3)")
    assert result.returncode == 1
    output = result.stdout.decode("utf-8")
    assert "ERGEBNIS: 1 Schritt(e) fehlgeschlagen: Übung" in output
    assert "So geht es weiter." in output


def test_the_audit_covers_the_build_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """PyInstaller steckt mit seinem Startprogramm in jedem ausgelieferten Windows-Paket."""
    script = ROOT / "tools" / "quality_gate.py"
    spec = importlib.util.spec_from_file_location("quality_gate", script)
    assert spec is not None
    assert spec.loader is not None
    gate = importlib.util.module_from_spec(spec)
    # Der dataclass-Dekorator schlägt das Modul in sys.modules nach.
    monkeypatch.setitem(sys.modules, spec.name, gate)
    spec.loader.exec_module(gate)
    steps = gate.build_steps(fast=True, audit=True)
    (audit,) = [step for step in steps if "pip_audit" in step.command]
    assert str(ROOT / "packaging" / "requirements.txt") in audit.command
