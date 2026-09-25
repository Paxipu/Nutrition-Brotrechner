"""Sicherungen nur bei echten Änderungen.

Früher legte jedes Speichern eine Sicherung an, auch das beim Beenden. Nach
zehnmal Schließen ohne Änderung waren die zehn aufbewahrten Sicherungen zehn
gleiche Kopien des jetzigen Stands - jeder ältere war verloren. Außerdem trugen
die Namen nur Sekunden: Zwei Speichervorgänge in derselben Sekunde schrieben
dieselbe Sicherung, und der ältere Stand ging verloren.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from brotrechner.core.models import Ingredient
from brotrechner.core.nutrients import Nutrients
from brotrechner.data import repository
from brotrechner.data.repository import (
    MAX_BACKUPS,
    IngredientStore,
    make_backup,
    save_ingredients,
    write_json_atomic,
)


def backups(folder: Path, stem: str = "daten") -> list[Any]:
    """Inhalte der Sicherungen, die älteste zuerst."""
    files = sorted((folder / "backups").glob(f"{stem}_*.json"))
    return [json.loads(f.read_text(encoding="utf-8")) for f in files]


class _FrozenClock(datetime):
    """Eine Uhr, die immer denselben Augenblick zeigt."""

    @classmethod
    def now(cls, tz: Any = None) -> _FrozenClock:  # type: ignore[override]
        del tz
        return cls(2026, 9, 25, 10, 0, 0, 0)


class TestOnlyRealChanges:
    def test_the_same_content_is_not_written_again(self, tmp_path: Path) -> None:
        target = tmp_path / "daten.json"
        assert write_json_atomic(target, {"a": 1})
        written = target.stat().st_mtime_ns
        assert not write_json_atomic(target, {"a": 1})
        assert target.stat().st_mtime_ns == written
        assert backups(tmp_path) == []

    def test_a_new_timestamp_alone_is_no_change(self, tmp_path: Path) -> None:
        target = tmp_path / "daten.json"
        write_json_atomic(target, {"updated_at": "eins", "a": 1}, volatile=("updated_at",))
        assert not write_json_atomic(
            target, {"updated_at": "zwei", "a": 1}, volatile=("updated_at",)
        )
        assert json.loads(target.read_text(encoding="utf-8"))["updated_at"] == "eins"

    def test_a_real_change_backs_up_the_previous_state(self, tmp_path: Path) -> None:
        target = tmp_path / "daten.json"
        write_json_atomic(target, {"stand": 1})
        assert write_json_atomic(target, {"stand": 2})
        assert backups(tmp_path) == [{"stand": 1}]

    def test_tuples_count_as_the_lists_they_become(self, tmp_path: Path) -> None:
        target = tmp_path / "daten.json"
        write_json_atomic(target, {"werte": (1, 2)})
        assert not write_json_atomic(target, {"werte": [1, 2]})

    def test_a_list_is_compared_as_a_whole(self, tmp_path: Path) -> None:
        target = tmp_path / "daten.json"
        write_json_atomic(target, [1, 2], volatile=("updated_at",))
        assert not write_json_atomic(target, [1, 2], volatile=("updated_at",))
        assert write_json_atomic(target, [2, 1], volatile=("updated_at",))

    def test_a_broken_file_is_backed_up_and_replaced(self, tmp_path: Path) -> None:
        target = tmp_path / "daten.json"
        target.write_text("{kaputt", encoding="utf-8")
        assert write_json_atomic(target, {"a": 1})
        (backup,) = (tmp_path / "backups").glob("daten_*.json")
        assert backup.read_text(encoding="utf-8") == "{kaputt"

    def test_closing_again_and_again_keeps_the_history(self, tmp_path: Path) -> None:
        """Der eigentliche Fehler: Jedes Beenden speichert - ohne Änderung."""
        path = tmp_path / "ingredients.json"
        salt = Ingredient(name="Salz", nutrients=Nutrients(salt=100.0))
        store = IngredientStore([salt])
        save_ingredients(path, store)
        store.add(Ingredient(name="Wasser", nutrients=Nutrients(water=100.0)))
        save_ingredients(path, store)
        for _ in range(MAX_BACKUPS + 2):
            assert not save_ingredients(path, store)
        (older,) = backups(tmp_path, "ingredients")
        assert [i["name"] for i in older["ingredients"]] == ["Salz"]


class TestBackupNames:
    def test_two_changes_in_the_same_instant_keep_both_states(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(repository, "datetime", _FrozenClock)
        target = tmp_path / "daten.json"
        for stand in (1, 2, 3):
            write_json_atomic(target, {"stand": stand})
        assert backups(tmp_path) == [{"stand": 1}, {"stand": 2}]

    def test_old_names_without_microseconds_sort_before_new_ones(self, tmp_path: Path) -> None:
        """Sicherungen aus der Vorversion bleiben in der richtigen Reihenfolge."""
        folder = tmp_path / "backups"
        folder.mkdir()
        (folder / "daten_20200101_120000.json").write_text('{"stand": 0}', encoding="utf-8")
        target = tmp_path / "daten.json"
        write_json_atomic(target, {"stand": 1})
        write_json_atomic(target, {"stand": 2})
        assert backups(tmp_path) == [{"stand": 0}, {"stand": 1}]

    def test_only_the_most_recent_are_kept(self, tmp_path: Path) -> None:
        target = tmp_path / "daten.json"
        for stand in range(MAX_BACKUPS + 5):
            write_json_atomic(target, {"stand": stand})
        assert backups(tmp_path) == [{"stand": s} for s in range(4, MAX_BACKUPS + 4)]


class TestMakeBackup:
    def test_the_current_state_is_secured(self, tmp_path: Path) -> None:
        target = tmp_path / "daten.json"
        write_json_atomic(target, {"stand": 1})
        backup = make_backup(target)
        assert backup is not None
        assert json.loads(backup.read_text(encoding="utf-8")) == {"stand": 1}

    def test_twice_makes_no_duplicate(self, tmp_path: Path) -> None:
        target = tmp_path / "daten.json"
        write_json_atomic(target, {"stand": 1})
        first = make_backup(target)
        assert make_backup(target) == first
        assert backups(tmp_path) == [{"stand": 1}]

    def test_a_change_after_a_backup_makes_no_duplicate(self, tmp_path: Path) -> None:
        target = tmp_path / "daten.json"
        write_json_atomic(target, {"stand": 1})
        make_backup(target)
        write_json_atomic(target, {"stand": 2})
        assert backups(tmp_path) == [{"stand": 1}]

    def test_nothing_to_secure(self, tmp_path: Path) -> None:
        assert make_backup(tmp_path / "fehlt.json") is None

    def test_a_failed_backup_is_reported(self, tmp_path: Path) -> None:
        target = tmp_path / "daten.json"
        write_json_atomic(target, {"stand": 1})
        (tmp_path / "backups").write_text("Datei statt Ordner", encoding="utf-8")
        assert make_backup(target) is None


class TestHistory:
    @given(states=st.lists(st.integers(min_value=0, max_value=3), min_size=1, max_size=30))
    def test_every_real_change_leaves_exactly_one_backup(self, states: list[int]) -> None:
        """Gleich oft gespeichert oder nicht: Gesichert wird jeder frühere Stand genau einmal."""
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "daten.json"
            expected: list[dict[str, int]] = []
            previous: int | None = None
            for state in states:
                written = write_json_atomic(target, {"stand": state})
                assert written == (state != previous)
                if previous is not None and state != previous:
                    expected.append({"stand": previous})
                previous = state
            assert backups(Path(folder)) == expected[-MAX_BACKUPS:]
