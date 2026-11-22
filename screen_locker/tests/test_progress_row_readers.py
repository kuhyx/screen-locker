"""Differential: progress rows in the workout ledger change no existing reader."""

from __future__ import annotations

from datetime import date, datetime, time
import json
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import earned_time
import pytest

from screen_locker import _earned, _progress_row
from screen_locker._shutdown_base import base_minutes
from screen_locker._shutdown_target import gather
from screen_locker._workout_ledger import append_rows, credit_row, ledger_path
from screen_locker.tests._earned_fixtures import KEY, signing_key
from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_DAY = date(2026, 10, 10)
_ISO = _DAY.isoformat()
_FLAT = {"leetcode": False, "reading": False, "anki": False, "tutor": False}


@pytest.fixture(autouse=True, name="key")
def key_fixture(tmp_path: Path) -> Iterator[Path]:
    """A signing key so the ledger can be written and read."""
    with signing_key(tmp_path) as path:
        yield path


def _noon() -> float:
    return datetime.combine(_DAY, time(12, 0)).astimezone().timestamp()


def _log(tmp_path: Path) -> Path:
    log = tmp_path / "log.json"
    entry = {
        "workout_data": {"type": "runnerup_verified", "completed_at": _noon()},
        "timestamp": "2026-10-10T20:00:00+00:00",
    }
    log.write_text(json.dumps({_ISO: [entry]}))
    return log


def _readers(tmp_path: Path, log: Path) -> dict[str, Any]:
    """Every existing reader of the workout ledger, side by side."""
    workout = earned_time.WORKOUT
    with patch("screen_locker._shutdown_target.gate_answers", return_value=_FLAT):
        target = gather(_DAY, log)
    return {
        "units": earned_time.credit_units(
            workout, ledger_path(), _earned.HMAC_KEY_FILE, _DAY
        ),
        "first": earned_time.first_credit_at(
            workout, ledger_path(), _earned.HMAC_KEY_FILE, _DAY
        ),
        "first_credit_time": _earned.first_credit_time(workout, _DAY),
        "target_minutes": target.minutes,
        "first_done_at": target.first_done_at,
        "workout_term": target.resolution.term("workout").answer,
        "base": base_minutes(_DAY),
    }


def _credit_result(mock_tk: MagicMock, tmp_path: Path) -> tuple[Any, ...]:
    """The workout credit mixin's outcome over an in-memory shutdown config."""
    locker = create_locker(mock_tk, tmp_path)
    locker.workout_data = {"type": "runnerup_verified"}
    config = {"value": (1200, 1200, 300)}

    def write(mw: int, ts: int, morning: int, *, restore: bool) -> bool:
        assert restore
        config["value"] = (mw, ts, morning)
        return True

    object.__setattr__(
        locker, "_read_shutdown_config", MagicMock(side_effect=lambda: config["value"])
    )
    object.__setattr__(locker, "_write_shutdown_config", MagicMock(side_effect=write))
    with (
        patch("screen_locker._shutdown.plan_absorb", side_effect=lambda m: (m, 0)),
        patch("screen_locker._shutdown.save_lift"),
        patch("screen_locker._workout_credit.is_rest_day", return_value=False),
        patch("screen_locker._workout_credit.count_weekly_workouts", return_value=3),
        patch("screen_locker._workout_credit._credit_notify.notify_workout_credit"),
    ):
        result = locker._apply_credit_for_written_entry([])
    return (result, config["value"])


@pytest.mark.usefixtures("pre_ladder")
def test_progress_rows_change_no_existing_reader(
    tmp_path: Path, mock_tk: MagicMock, mock_sys_exit: MagicMock
) -> None:
    """Credit units, first credit, shutdown target/base and the credit mixin agree."""
    del mock_sys_exit
    log = _log(tmp_path)
    entries = json.loads(log.read_text())[_ISO]
    credit = credit_row(_ISO, entries, 0)
    assert credit is not None
    assert append_rows([credit]) == 1
    without = _readers(tmp_path, log)
    credited_without = _credit_result(mock_tk, tmp_path)
    assert without["units"] == 1

    for done in (600.0, 1200.0):
        _progress_row.record_progress(_ISO, done / 2 * 3.5, done)
    stored = json.loads(ledger_path().read_text())["entries"]
    assert [r["kind"] for r in stored] == ["credit", "progress", "progress"]

    assert _readers(tmp_path, log) == without
    assert _credit_result(mock_tk, tmp_path) == credited_without


def test_progress_rows_alone_earn_no_credit(tmp_path: Path) -> None:
    """A ledger holding only progress rows has zero credit units and no first credit."""
    del tmp_path
    _progress_row.record_progress(_ISO, 1750.0, 300.0)
    assert earned_time.verified(
        json.loads(ledger_path().read_text())["entries"][0], KEY
    )
    workout = earned_time.WORKOUT
    units = earned_time.credit_units(
        workout, ledger_path(), _earned.HMAC_KEY_FILE, _DAY
    )
    assert units is not None
    assert not units
    assert (
        earned_time.first_credit_at(workout, ledger_path(), _earned.HMAC_KEY_FILE, _DAY)
        is None
    )
