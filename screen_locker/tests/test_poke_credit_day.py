"""The poke credit's day reset, workout hand-off and the two reply snapshots."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from screen_locker import _poke_credit
from screen_locker._poke_credit import PokeLocker
from screen_locker._workout_credit import WorkoutCreditResult

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def log_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fresh PokeLocker on a tmp log; the day reset stubbed."""
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
    """Replace the shared credit step."""
    stub = MagicMock(
        return_value=WorkoutCreditResult(
            shutdown_adjusted=True,
            new_debt=None,
            extra_bonus_delta=0,
            weekly_count=1,
            already_counted_today=False,
        )
    )
    monkeypatch.setattr(PokeLocker, "_apply_credit_for_written_entry", stub)
    return stub


class TestStartTheDay:
    def test_new_day_runs_the_week_transition_then_the_reset(
        self, log_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []

        def week(*_args: object) -> list[str]:
            calls.append("week")
            return ["+1h streak"]

        def reset(*_args: object, **_kwargs: object) -> bool:
            calls.append("reset")
            return True

        monkeypatch.setattr(_poke_credit, "process_week_transition", week)
        monkeypatch.setattr(_poke_credit, "reset_to_base_if_new_day", reset)
        _poke_credit.fresh_locker().start_the_day()
        assert calls == ["week", "reset"]

    def test_credit_written_sets_the_entry_and_returns_the_result(
        self, log_file: Path, credit: MagicMock
    ) -> None:
        locker = _poke_credit.fresh_locker()
        assert locker.credit_written({"type": "x"}, [{"a": 1}]) == credit.return_value
        assert locker.workout_data == {"type": "x"}
        credit.assert_called_once_with([{"a": 1}])


class TestSnapshots:
    def test_current_shutdown_renders_tonights_time(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(_poke_credit, "read_shutdown_config", lambda _p: (1, 2, 3))
        monkeypatch.setattr(_poke_credit, "tonight_minutes", lambda _c, _d: 20 * 60 + 5)
        assert _poke_credit.current_shutdown() == "20:05"

    def test_unreadable_config_is_none_and_warned(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(_poke_credit, "read_shutdown_config", lambda _p: None)
        with caplog.at_level(logging.WARNING):
            assert _poke_credit.current_shutdown() is None
        assert "shutdown=null" in caplog.text

    def test_current_gaming_minutes_delegates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[Path] = []

        def minutes(log: Path) -> int:
            seen.append(log)
            return 90

        monkeypatch.setattr(_poke_credit, "gaming_minutes_today", minutes)
        assert _poke_credit.current_gaming_minutes(tmp_path / "log.json") == 90
        assert seen == [tmp_path / "log.json"]
