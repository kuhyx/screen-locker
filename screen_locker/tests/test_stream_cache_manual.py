"""The Firebase stream credits phone-logged manual workouts on arrival.

Until 2026-11-02 the stream only handed StrongLifts sessions to the ingest, so
a manual workout logged on the phone sat in Firebase until the next 15-minute
``workout-sync`` tick -- long enough that it looked lost and was re-logged by
hand on the PC.
"""

from __future__ import annotations

import json
import threading
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from screen_locker import _poke_credit, _stream_cache
from screen_locker._poke_credit import BatchOutcome, PokeLocker
from screen_locker._stream_cache import DeviceLogCache
from screen_locker._workout_credit import WorkoutCreditResult
from screen_locker.tests.test_manual_sync import _OTHER_DRAFT, _manual_record
from screen_locker.tests.test_stream_cache import (
    OWN,
    Credit,
    log_blob,
    patch_event,
    snapshot,
)

if TYPE_CHECKING:
    from pathlib import Path

_DATE = "2026-07-13"
_RID, _PAYLOAD = _manual_record(_OTHER_DRAFT, _DATE)


@pytest.fixture(name="steps")
def steps_fixture(monkeypatch: pytest.MonkeyPatch) -> tuple[Credit, Credit]:
    """Record both batch credit steps instead of building a locker."""
    sessions, manuals = Credit(), Credit()
    monkeypatch.setattr(_stream_cache._poke_credit, "credit_sessions", sessions)
    monkeypatch.setattr(_stream_cache._poke_credit, "credit_manual_workouts", manuals)
    return sessions, manuals


@pytest.fixture(name="cache")
def cache_fixture(steps: tuple[Credit, Credit]) -> DeviceLogCache:
    """A cache whose own device dir is ``pc-own``, sharing one gate."""
    gate = threading.Lock()
    for credit in steps:
        credit.gate = gate
    return DeviceLogCache("sync/devices", frozenset({OWN}), gate)


class TestStreamedManual:
    """Which streamed manual records reach the manual ingest."""

    def test_a_phone_manual_workout_is_credited_on_arrival(
        self, cache: DeviceLogCache, steps: tuple[Credit, Credit]
    ) -> None:
        """A patch carrying a new manual record is handed over under the gate."""
        sessions, manuals = steps
        cache.handle(snapshot({"phone": log_blob("s1")}))
        result = cache.handle(
            patch_event({"phone": log_blob(_RID, wall=2, payload=_PAYLOAD)})
        )
        assert manuals.batches == [[_RID]]
        assert manuals.gate_held == [True]
        assert sessions.batches == [["s1"]]
        assert "1 manual workout(s) checked, 1 newly logged" in result.summary

    def test_already_handed_manual_records_are_a_no_op(
        self, cache: DeviceLogCache, steps: tuple[Credit, Credit]
    ) -> None:
        """Re-streaming the same manual record costs no second ingest."""
        _sessions, manuals = steps
        blob = log_blob(_RID, payload=_PAYLOAD)
        cache.handle(snapshot({"phone": blob}))
        result = cache.handle(snapshot({"phone": blob}))
        assert manuals.batches == [[_RID]]
        assert "no-op, no file I/O" in result.summary

    def test_tombstoned_manual_records_are_not_handed_over(
        self, cache: DeviceLogCache, steps: tuple[Credit, Credit]
    ) -> None:
        """A deleted record must not be credited by the stream either."""
        _sessions, manuals = steps
        cache.handle(
            snapshot({"phone": log_blob(_RID, deleted=True, payload=_PAYLOAD)})
        )
        assert manuals.batches == []

    def test_a_session_only_event_does_not_call_the_manual_ingest(
        self, cache: DeviceLogCache, steps: tuple[Credit, Credit]
    ) -> None:
        """Each kind goes only to its own ingest."""
        sessions, manuals = steps
        cache.handle(snapshot({"phone": log_blob("s1")}))
        assert sessions.batches == [["s1"]]
        assert manuals.batches == []


@pytest.fixture(name="log_file")
def log_file_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fresh PokeLocker on a tmp log; day reset, local ledger and credit stubbed."""
    log = tmp_path / "poke_log.json"

    def headless(locker_cls: type[PokeLocker]) -> PokeLocker:
        """Build a PokeLocker without a display, pointed at the temporary log."""
        locker = object.__new__(locker_cls)
        locker.log_file = log
        locker.workout_data = {}
        return locker

    monkeypatch.setattr(_poke_credit, "_headless_locker", headless)
    monkeypatch.setattr(PokeLocker, "start_the_day", lambda _self: None)
    monkeypatch.setattr(
        PokeLocker,
        "_apply_credit_for_written_entry",
        MagicMock(
            return_value=WorkoutCreditResult(
                shutdown_adjusted=True,
                extra_bonus_delta=0,
                weekly_count=1,
                already_counted_today=False,
            )
        ),
    )
    return log


class TestCreditManualWorkouts:
    """The real manual ingest, run the way the stream runs it."""

    def test_logs_and_credits_a_streamed_manual_workout(self, log_file: Path) -> None:
        """The record lands in log.json under its own id and earns its credit."""
        outcome = _poke_credit.credit_manual_workouts([(_RID, _PAYLOAD)], today=_DATE)
        assert outcome == BatchOutcome(ingested=(_RID,), credited=1)
        logged = json.loads(log_file.read_text())[_DATE]
        assert [e["workout_id"] for e in logged] == [_RID]

    def test_a_second_pass_is_a_duplicate(self, log_file: Path) -> None:
        """Re-crediting the same record logs nothing new."""
        _poke_credit.credit_manual_workouts([(_RID, _PAYLOAD)], today=_DATE)
        outcome = _poke_credit.credit_manual_workouts([(_RID, _PAYLOAD)], today=_DATE)
        assert outcome == BatchOutcome(ingested=(), credited=0)
        assert len(json.loads(log_file.read_text())[_DATE]) == 1
