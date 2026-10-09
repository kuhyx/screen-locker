"""The wiring around rest days, the grace lift and the ladder accessors.

Live workout credit on a rest day, lift absorption in the shutdown adds,
the day-aware ``_earned`` accessors on an ``earned_time`` without the ladder
API (0.3.0), and the new CLI flags.
"""

from __future__ import annotations

from datetime import date
import logging
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import earned_time
import pytest

from screen_locker import _cli, _earned, _grace_floor, _runnerup_tcx, _workout_credit
from screen_locker._shutdown import ShutdownMixin
from screen_locker._workout_credit import WorkoutCreditMixin

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_ISO = "2026-10-12"  # a Monday


class Host(WorkoutCreditMixin, ShutdownMixin):
    """The real credit and add paths over an in-memory config."""

    def __init__(self, tmp_path: Path, minutes: int, *, ok: bool = True) -> None:
        self.config = (minutes, minutes, 300)
        self.ok = ok
        self.log_file = tmp_path / "log.json"
        self.workout_data = {"type": "runnerup_verified"}

    def _read_shutdown_config(self) -> tuple[int, int, int] | None:
        return self.config

    def _write_shutdown_config(
        self, mon_wed: int, thu_sun: int, morning_end: int, *, restore: bool = False
    ) -> bool:
        del restore
        if self.ok:
            self.config = (min(mon_wed, 1380), min(thu_sun, 1380), morning_end)
        return self.ok


@pytest.fixture
def monday() -> Iterator[None]:
    with (
        patch("screen_locker._workout_credit.today_str", return_value=_ISO),
        patch("screen_locker._shutdown.today_str", return_value=_ISO),
        patch.object(_grace_floor, "today_str", return_value=_ISO),
    ):
        yield


_COUNTED: list[dict[str, Any]] = [{"workout_data": {"type": "runnerup_verified"}}]


@pytest.mark.usefixtures("monday")
class TestRestDayCredit:
    def test_the_first_real_workout_earns_nothing_more(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        host = Host(tmp_path, 20 * 60)
        with (
            patch.object(_workout_credit, "is_rest_day", return_value=True),
            caplog.at_level(logging.INFO),
        ):
            result = host._apply_credit_for_written_entry([])
        assert host.config[0] == 20 * 60
        assert not result.shutdown_adjusted
        assert "already in tonight's time" in caplog.text

    def test_a_second_one_earns_a_further_unit(self, tmp_path: Path) -> None:
        host = Host(tmp_path, 20 * 60)
        extra = _earned.extra_minutes(earned_time.WORKOUT, _grace_date())
        with patch.object(_workout_credit, "is_rest_day", return_value=True):
            result = host._apply_credit_for_written_entry(_COUNTED)
        assert host.config[0] == 20 * 60 + extra
        assert result.extra_bonus_delta == extra


def _grace_date() -> date:
    return date.fromisoformat(_ISO)


@pytest.mark.usefixtures("monday")
class TestLiftAbsorption:
    def test_adds_pay_from_the_lift_first(self, tmp_path: Path) -> None:
        _grace_floor.save_lift(30)
        host = Host(tmp_path, 19 * 60 + 55)
        assert host._adjust_shutdown_time_by(25)
        assert host.config[0] == 19 * 60 + 55
        assert host._adjust_shutdown_time_by(25)
        assert host.config[0] == 20 * 60 + 15

    def test_a_failed_write_keeps_the_lift(self, tmp_path: Path) -> None:
        _grace_floor.save_lift(30)
        host = Host(tmp_path, 1195, ok=False)
        assert not host._adjust_shutdown_time_by(25)
        assert not host._adjust_shutdown_time_later()
        assert _grace_floor.plan_absorb(0) == (0, 30)

    def test_the_first_workout_is_day_aware(self, tmp_path: Path) -> None:
        host = Host(tmp_path, 1140)
        assert host._adjust_shutdown_time_later()
        first = _earned.first_minutes(earned_time.WORKOUT, _grace_date())
        assert host.config[0] == 1140 + first


class TestPreLadderEarnedTime:
    """On 0.3.0 the accessors fall back to the raw fields, and say so once."""

    def test_raw_fields_without_the_ladder_api(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        for name in (
            "shutdown_minutes_for",
            "extra_shutdown_minutes_for",
            "shutdown_ceiling_for",
            "first_credit_at",
        ):
            monkeypatch.delattr(earned_time, name, raising=False)
        day = _grace_date()
        workout = earned_time.WORKOUT
        assert _earned.first_minutes(workout, day) == workout.shutdown_minutes
        assert _earned.extra_minutes(workout, day) == workout.extra_shutdown_minutes
        assert _earned.ceiling(day) == earned_time.SHUTDOWN_CEILING_MINUTES
        _earned._warn_no_first_credit.cache_clear()
        with caplog.at_level(logging.WARNING):
            assert _earned.first_credit_time(earned_time.ANKI, day) is None
            assert _earned.first_credit_time(earned_time.ANKI, day) is None
        assert caplog.text.count("has no first_credit_at") == 1

    def test_the_ladder_api_reads_the_ledger(self, tmp_path: Path) -> None:
        if not hasattr(earned_time, "first_credit_at"):
            pytest.skip("installed earned_time predates first_credit_at")
        assert _earned.first_credit_time(earned_time.ANKI, _grace_date()) is None


def test_a_failed_tcx_parse_is_not_marked() -> None:
    assert _runnerup_tcx._mark_walk(None, "x_Walking.tcx") is None


class _Bare:
    """What ``_headless_locker`` builds on: any class with a ``__dict__``."""

    log_file: Path
    workout_data: dict[str, str]


class TestCliFlags:
    def test_declare_rest_day_dispatches_the_rest_of_argv(self) -> None:
        with (
            patch.object(_cli.logging, "basicConfig"),
            patch.object(_cli, "run_declare_rest_day", return_value=0) as run,
            patch.object(_cli.sys, "exit", side_effect=SystemExit) as sys_exit,
            pytest.raises(SystemExit),
        ):
            _cli.main(_Bare, ["screen_lock.py", "--declare-rest-day", "tomorrow"])
        run.assert_called_once_with(["tomorrow"])
        sys_exit.assert_called_once_with(0)

    def test_backfill_dispatches_with_the_log(self) -> None:
        with (
            patch.object(_cli.logging, "basicConfig"),
            patch.object(_cli, "run_backfill", return_value=0) as run,
            patch.object(_cli.sys, "exit", side_effect=SystemExit),
            pytest.raises(SystemExit),
        ):
            _cli.main(
                _Bare, ["screen_lock.py", "--backfill-workout-ledger", "--dry-run"]
            )
        log_file, argv = run.call_args.args
        assert log_file.name == "log.json"
        assert argv == ["--dry-run"]
