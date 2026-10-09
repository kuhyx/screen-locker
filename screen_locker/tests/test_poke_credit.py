"""Crediting poked sessions: precheck, ingest, slot outcomes and the day reset."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest

from screen_locker import _poke_credit
from screen_locker._poke_credit import (
    BatchOutcome,
    PokeLocker,
    PokeOutcome,
    credit_session,
    credit_sessions,
)
from screen_locker._workout_credit import WorkoutCreditResult

if TYPE_CHECKING:
    from pathlib import Path

_DAY = "2026-10-09"


def _session(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "workout_type": "B",
        "date": _DAY,
        "start_time": f"{_DAY}T15:10:40.953",
        "duration_seconds": 7020,
        "succeeded": True,
        "exercises": [{"name": "Row", "succeeded": True}],
    }
    payload.update(overrides)
    return payload


def _result(*, counted: bool = False) -> WorkoutCreditResult:
    return WorkoutCreditResult(
        shutdown_adjusted=not counted,
        new_debt=None,
        extra_bonus_delta=0,
        weekly_count=1,
        already_counted_today=counted,
    )


@pytest.fixture
def log_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fresh PokeLocker on a tmp log; the day reset and the credit stubbed."""
    log = tmp_path / "poke_log.json"

    def headless(locker_cls: type[PokeLocker]) -> PokeLocker:
        locker = object.__new__(locker_cls)
        locker.log_file = log
        locker.workout_data = {}
        return locker

    monkeypatch.setattr(_poke_credit, "_headless_locker", headless)
    monkeypatch.setattr(_poke_credit, "process_week_transition", lambda *_: [])
    monkeypatch.setattr(_poke_credit, "reset_to_base_if_new_day", lambda *_a, **_k: 0)
    return log


@pytest.fixture
def credit(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace the shared credit step; the ingest itself stays real."""
    stub = MagicMock(return_value=_result())
    monkeypatch.setattr(PokeLocker, "_apply_credit_for_written_entry", stub)
    return stub


def _logged_ids(log: Path) -> list[str]:
    data = json.loads(log.read_text())
    return [e["workout_data"]["sync_record_id"] for es in data.values() for e in es]


class TestCreditSession:
    def test_happy_path_logs_and_credits_once(
        self, log_file: Path, credit: MagicMock
    ) -> None:
        outcome = credit_session("r1", _session())
        assert outcome == PokeOutcome(
            ok=True, credited=True, duplicate=False, reason="workout credited"
        )
        assert _logged_ids(log_file) == [f"{_DAY}T15:10:40.953"]
        credit.assert_called_once()

    def test_second_poke_of_the_same_session_is_a_duplicate(
        self, log_file: Path, credit: MagicMock
    ) -> None:
        credit_session("r1", _session())
        outcome = credit_session("r1", _session())
        assert (outcome.ok, outcome.credited, outcome.duplicate) == (True, False, True)
        assert "already in the PC's log" in outcome.reason
        assert credit.call_count == 1
        assert len(_logged_ids(log_file)) == 1

    def test_slot_already_paid_logs_but_credits_nothing(
        self,
        log_file: Path,
        credit: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        credit.return_value = _result(counted=True)
        with caplog.at_level(logging.WARNING):
            outcome = credit_session("r1", _session())
        assert (outcome.ok, outcome.credited, outcome.duplicate) == (True, False, False)
        assert "slot" in outcome.reason
        assert "not credited" in caplog.text
        assert len(_logged_ids(log_file)) == 1

    @pytest.mark.parametrize("day", [None, "", 20261009])
    def test_session_without_a_usable_date_is_refused(
        self, log_file: Path, credit: MagicMock, day: object
    ) -> None:
        outcome = credit_session("r1", _session(date=day))
        assert (outcome.ok, outcome.credited, outcome.duplicate) == (
            False,
            False,
            False,
        )
        assert "no usable date" in outcome.reason
        assert not log_file.exists()
        credit.assert_not_called()

    @pytest.mark.parametrize(
        ("overrides", "fragment"),
        [
            ({"exercises": []}, "no exercises"),
            ({"duration_seconds": 600}, "10 min"),
            ({"duration_seconds": "long"}, "not a number"),
        ],
    )
    def test_invalid_session_is_refused_with_the_reason(
        self,
        log_file: Path,
        credit: MagicMock,
        overrides: dict[str, object],
        fragment: str,
    ) -> None:
        outcome = credit_session("r1", _session(**overrides))
        assert outcome.ok is False
        assert "does not count" in outcome.reason
        assert fragment in outcome.reason
        assert not log_file.exists()
        credit.assert_not_called()

    def test_the_day_is_reset_before_the_credit(
        self, log_file: Path, credit: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        order: list[str] = []

        def reset(_self: PokeLocker) -> None:
            order.append("reset")

        def paid(*_args: object) -> WorkoutCreditResult:
            order.append("credit")
            return _result()

        monkeypatch.setattr(PokeLocker, "start_the_day", reset)
        credit.side_effect = paid
        credit_session("r1", _session())
        assert order == ["reset", "credit"]


class TestCreditSessions:
    def test_batch_counts_ingested_and_credited(
        self, log_file: Path, credit: MagicMock
    ) -> None:
        other = _session(date="2026-10-08", start_time="2026-10-08T09:00:00.000")
        outcome = credit_sessions([("r1", _session()), ("r2", other)])
        assert outcome == BatchOutcome(ingested=("r1", "r2"), credited=2)
        assert credit.call_count == 2

    def test_already_logged_ids_cost_nothing(
        self, log_file: Path, credit: MagicMock
    ) -> None:
        credit_sessions([("r1", _session())])
        outcome = credit_sessions([("r1", _session())])
        assert outcome == BatchOutcome(ingested=(), credited=0)
        assert credit.call_count == 1

    def test_invalid_session_in_a_batch_is_skipped(
        self, log_file: Path, credit: MagicMock
    ) -> None:
        outcome = credit_sessions([("bad", _session(exercises=[]))])
        assert outcome == BatchOutcome(ingested=(), credited=0)
        assert not log_file.exists()

    def test_sessions_that_shared_a_paid_slot_are_warned_about(
        self,
        log_file: Path,
        credit: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        credit.return_value = _result(counted=True)
        with caplog.at_level(logging.WARNING):
            outcome = credit_sessions([("r1", _session())])
        assert outcome == BatchOutcome(ingested=("r1",), credited=0)
        assert "1 streamed session(s)" in caplog.text
