"""Tests for logging a manual workout for a future day from this PC."""

from __future__ import annotations

from datetime import date, timedelta
import json
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from screen_locker import _manual_schedule
from screen_locker._day import today_str
from screen_locker._manual_push import PushResult
from screen_locker._manual_schedule import budget_error, schedule_future_workout
from screen_locker._manual_workout import (
    SPORT_OTHER,
    ManualWorkoutDraft,
    build_sync_payload,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


def _plus(days: int) -> str:
    """Return the local ISO date ``days`` from today."""
    return (date.fromisoformat(today_str()) + timedelta(days=days)).isoformat()


def _draft(start: str = "18:00") -> ManualWorkoutDraft:
    """A valid 'other sport' draft."""
    return ManualWorkoutDraft(
        sport=SPORT_OTHER,
        start_time=start,
        end_time="19:30",
        location_name="Padel Club",
        transport_method="bike",
        cost="40 PLN",
        rpe=7,
        went_well="Good rallies and fast footwork",
        to_improve="Second serve needs more spin work",
        overall_feeling="Tired but happy, legs felt strong",
        activity_type_other="padel",
        activity_details="Ninety minutes of padel doubles, baseline and net play",
    )


@pytest.fixture
def stubs(tmp_path: Path) -> Iterator[SimpleNamespace]:
    """Redirect the ledger; stub Firebase pull, the publisher and the identity."""
    ledger = tmp_path / "pending.json"
    pulled: list[tuple[str, dict]] = []
    push = MagicMock(return_value=PushResult(pushed=True, record_count=1, reason="ok"))
    with (
        patch("screen_locker._manual_pending.MANUAL_PENDING_FILE", ledger),
        patch.object(_manual_schedule, "pull_all_manual_records", lambda: list(pulled)),
        patch.object(_manual_schedule, "push_pc_workouts", push),
        patch.object(
            _manual_schedule,
            "device_identity",
            lambda: SimpleNamespace(device_id="pc-test"),
        ),
    ):
        yield SimpleNamespace(
            ledger=ledger, pulled=pulled, push=push, log_file=tmp_path / "log.json"
        )


class TestBudgetError:
    """Budget sees the Firebase pull AND this PC's ledger."""

    def test_open_when_nothing_is_pending(self, stubs: SimpleNamespace) -> None:
        assert budget_error(stubs.log_file, _plus(1)) is None

    def test_phone_pending_entries_hold_a_slot(self, stubs: SimpleNamespace) -> None:
        for offset in (1, 2):
            payload = build_sync_payload(_draft(f"1{offset}:00"), _plus(offset))
            stubs.pulled.append((f"manual:{_plus(offset)}T1{offset}:00", payload))
        assert budget_error(stubs.log_file, _plus(3)) is not None

    def test_excluding_an_id_frees_its_slot(self, stubs: SimpleNamespace) -> None:
        ids = []
        for offset in (1, 2):
            rid = f"manual:{_plus(offset)}T1{offset}:00"
            ids.append(rid)
            stubs.pulled.append((rid, build_sync_payload(_draft(), _plus(offset))))
        assert budget_error(stubs.log_file, _plus(3)) is not None
        assert budget_error(stubs.log_file, _plus(3), exclude_id=ids[0]) is None


class TestScheduleFutureWorkout:
    """Hold a validated draft for a later day and publish it."""

    def test_schedules_stores_and_publishes(self, stubs: SimpleNamespace) -> None:
        day = _plus(1)

        result = schedule_future_workout(stubs.log_file, _draft(), day)

        assert result.scheduled is True
        assert result.record_id == f"manual:{day}T18:00"
        assert "counts automatically" in result.reason
        assert list(json.loads(stubs.ledger.read_text())) == [result.record_id]
        stubs.push.assert_called_once_with(stubs.log_file)
        assert not stubs.log_file.exists()

    def test_an_unpublished_entry_is_still_scheduled_and_says_so(
        self, stubs: SimpleNamespace
    ) -> None:
        stubs.push.return_value = PushResult(
            pushed=False, record_count=1, reason="Firebase down"
        )
        result = schedule_future_workout(stubs.log_file, _draft(), _plus(2))
        assert result.scheduled is True
        assert "not yet published: Firebase down" in result.reason

    def test_today_is_not_a_future_date(self, stubs: SimpleNamespace) -> None:
        result = schedule_future_workout(stubs.log_file, _draft(), _plus(0))
        assert result.scheduled is False
        assert "is today" in result.reason
        stubs.push.assert_not_called()

    @pytest.mark.parametrize("ahead", [-1, 8])
    def test_a_date_outside_the_window_is_refused(
        self, stubs: SimpleNamespace, ahead: int
    ) -> None:
        result = schedule_future_workout(stubs.log_file, _draft(), _plus(ahead))
        assert result.scheduled is False
        assert not stubs.ledger.exists()

    def test_an_exhausted_budget_is_refused(self, stubs: SimpleNamespace) -> None:
        assert schedule_future_workout(
            stubs.log_file, _draft("10:00"), _plus(1)
        ).scheduled
        assert schedule_future_workout(
            stubs.log_file, _draft("11:00"), _plus(2)
        ).scheduled
        refused = schedule_future_workout(stubs.log_file, _draft("12:00"), _plus(3))
        assert refused.scheduled is False
        assert "budget" in refused.reason.lower()
        assert len(json.loads(stubs.ledger.read_text())) == 2

    def test_the_same_entry_twice_is_refused(self, stubs: SimpleNamespace) -> None:
        day = _plus(1)
        assert schedule_future_workout(stubs.log_file, _draft(), day).scheduled
        again = schedule_future_workout(stubs.log_file, _draft(), day)
        assert again.scheduled is False
        assert "already scheduled" in again.reason
        stubs.push.assert_called_once()
