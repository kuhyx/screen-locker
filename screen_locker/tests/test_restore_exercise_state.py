"""Restore of the pre-gap-deload export (scripts/restore_exercise_state.py)."""

from __future__ import annotations

import datetime as dt

import pytest

from scripts import restore_exercise_state as res

_NOW = dt.datetime(2026, 11, 21, 12, 0, tzinfo=dt.UTC)


def test_every_row_gets_a_newer_stamp_and_a_deload_stamp() -> None:
    """Each row wins the import and is shielded from a second auto cut."""
    export = {
        "format": "workout_app-export",
        "version": 3,
        "exercise_state": [
            {"name": "Dumbbell Lunge", "weight": 20.0, "updated_at": 5},
            {"name": "Situp", "weight": 10.0, "updated_at": 0},
        ],
    }
    doc = res.prepare_restore(export, _NOW)
    stamp = int(_NOW.timestamp() * 1000)
    assert [r["updated_at"] for r in doc["exercise_state"]] == [stamp, stamp]
    assert all(r["last_deloaded_at"].startswith("2026-11-21T12:00") for r in doc["exercise_state"])
    assert doc["exercise_state"][0]["weight"] == 20.0
    assert doc["version"] == 3


def test_an_empty_export_is_refused() -> None:
    """An export with no rows is refused instead of restoring nothing."""
    with pytest.raises(ValueError, match="nothing to restore"):
        res.prepare_restore({"exercise_state": []}, _NOW)
