"""Headless manual-workout logging with ``--date``: future days are held, not logged."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import json
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from screen_locker._manual_cli import run_manual_log
from screen_locker._manual_push import PushResult
from screen_locker.tests.test_manual_cli import _TODAY, _args, _entries

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


def _days_from_today(days: int) -> str:
    """Return the local ISO date ``days`` from today (negative = past)."""
    return (date.fromisoformat(_TODAY) + timedelta(days=days)).isoformat()


@dataclass
class Held:
    """The redirected pending ledger and the stubbed publisher."""

    ledger: Path
    push: MagicMock


@pytest.fixture
def held(tmp_path: Path) -> Iterator[Held]:
    """Redirect the pending ledger and stub the publisher: nothing leaves the box."""
    ledger = tmp_path / "manual_pending.json"
    with (
        patch("screen_locker._constants.MANUAL_PENDING_FILE", ledger),
        patch("screen_locker._manual_pending.MANUAL_PENDING_FILE", ledger),
        patch(
            "screen_locker._manual_schedule.push_pc_workouts",
            return_value=PushResult(pushed=True, record_count=1, reason="pushed"),
        ) as push,
        patch(
            "screen_locker._manual_schedule.device_identity",
            return_value=SimpleNamespace(device_id="pc-test"),
        ),
    ):
        yield Held(ledger=ledger, push=push)


@pytest.mark.parametrize("ahead", [1, 7])
def test_a_future_date_is_held_not_logged(
    tmp_path: Path, held: Held, ahead: int
) -> None:
    """Today+1 .. today+7 is scheduled: ledger + publish, never log.json."""
    log_file = tmp_path / "log.json"
    day = _days_from_today(ahead)

    assert run_manual_log(log_file, _args(date=day)) == 0

    assert _entries(log_file) == []
    assert list(json.loads(held.ledger.read_text())) == [f"manual:{day}T17:30"]
    held.push.assert_called_once()


@pytest.mark.parametrize("ahead", [8, -1])
def test_a_date_outside_today_to_plus_seven_is_refused(
    tmp_path: Path, held: Held, ahead: int
) -> None:
    """+8 days and yesterday are refused, nothing written or published."""
    log_file = tmp_path / "log.json"

    assert run_manual_log(log_file, _args(date=_days_from_today(ahead))) == 1

    assert _entries(log_file) == []
    assert not held.ledger.exists()
    held.push.assert_not_called()


def test_a_garbled_date_is_refused(tmp_path: Path, held: Held) -> None:
    """A date that is not YYYY-MM-DD is refused before anything is written."""
    assert run_manual_log(tmp_path / "log.json", _args(date="tomorrow")) == 1
    assert not held.ledger.exists()


def test_a_future_entry_that_breaks_the_budget_is_refused(
    tmp_path: Path, held: Held
) -> None:
    """Scheduling counts the logged credits: a full week cannot take a 3rd."""
    log_file = tmp_path / "log.json"
    day = _days_from_today(1)
    assert run_manual_log(log_file, _args(start="07:00", end="08:30")) == 0
    assert run_manual_log(log_file, _args(start="10:00", end="11:30")) == 0

    # Today holds 2; tomorrow's 7-day window contains today, so it is full too.
    assert run_manual_log(log_file, _args(date=day)) == 1
    assert not held.ledger.exists()


def test_scheduling_the_same_entry_twice_is_refused(tmp_path: Path, held: Held) -> None:
    """The record id (date + start) is the dedup key for pending entries."""
    day = _days_from_today(2)
    log_file = tmp_path / "log.json"

    assert run_manual_log(log_file, _args(date=day)) == 0
    assert run_manual_log(log_file, _args(date=day)) == 1
    assert len(json.loads(held.ledger.read_text())) == 1


def test_a_pending_future_entry_counts_against_today(
    tmp_path: Path, held: Held
) -> None:
    """Today's entry sees pending future ones: they share a 7-day window."""
    log_file = tmp_path / "log.json"
    assert run_manual_log(log_file, _args(date=_days_from_today(1))) == 0
    assert run_manual_log(log_file, _args(date=_days_from_today(2), start="08:00")) == 0

    assert run_manual_log(log_file, _args()) == 1
    assert _entries(log_file) == []
