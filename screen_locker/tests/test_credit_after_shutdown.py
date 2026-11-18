"""A credit after tonight's shutdown adds its reward to that shutdown.

kuhy, 2026-11-18: shutdown 18:00, a run ending 19:58 must make 20:00 and the
book's +1h 21:00 -- the same sum the daily reset derives. The late-credit rule
(2026-10-17) made it 21:58 (the run's end + 2h) and then 22:58. Unpaid gates
keep the PC up behind the evening chain until 23:00 instead.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import earned_time
import pytest

from screen_locker import _sick_floor
from screen_locker._ceiling import ceiling
from screen_locker._day import today_str
from screen_locker._earned import first_minutes
from screen_locker._shutdown import ShutdownMixin
from screen_locker.tests._sick_helpers import mark_sick
from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path

    from screen_locker.screen_lock import ScreenLocker


def _today_at(hhmm: str) -> str:
    """Unix time of ``hhmm`` local today, as a ledger ``completed_at``."""
    day = date.fromisoformat(today_str())
    hour, minute = (int(p) for p in hhmm.split(":"))
    moment = datetime(day.year, day.month, day.day, hour, minute).astimezone()
    return str(moment.timestamp())


def _locker(mock_tk: MagicMock, tmp_path: Path, start: int) -> ScreenLocker:
    """A locker over an in-memory shutdown config starting at ``start``."""
    locker = create_locker(mock_tk, tmp_path)
    config = {"value": (start, start, 300)}

    def write(mw: int, ts: int, morning: int, *, restore: bool) -> bool:
        assert restore
        config["value"] = (mw, ts, morning)
        return True

    object.__setattr__(
        locker, "_read_shutdown_config", MagicMock(side_effect=lambda: config["value"])
    )
    object.__setattr__(locker, "_write_shutdown_config", MagicMock(side_effect=write))
    return locker


@pytest.mark.usefixtures("pre_ladder")
def test_a_run_after_the_shutdown_adds_to_the_shutdown(
    mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
) -> None:
    """18:00 shutdown, run ends 19:58: 18:00 + the workout reward, not 19:58 + it."""
    locker = _locker(mock_tk, tmp_path, 18 * 60)
    locker.workout_data = {
        "type": "runnerup_verified",
        "completed_at": _today_at("19:58"),
    }
    with (
        patch("screen_locker._shutdown.plan_absorb", side_effect=lambda m: (m, 0)),
        patch("screen_locker._shutdown.save_lift"),
        patch("screen_locker._workout_credit.is_rest_day", return_value=False),
        patch("screen_locker._workout_credit.count_weekly_workouts", return_value=3),
        patch("screen_locker._workout_credit._credit_notify.notify_workout_credit"),
    ):
        result = locker._apply_credit_for_written_entry([])
    reward = first_minutes(earned_time.WORKOUT, date.fromisoformat(today_str()))
    assert result.shutdown_adjusted is True
    assert locker._read_shutdown_config() == (18 * 60 + reward, 18 * 60 + reward, 300)


class _Host(ShutdownMixin):
    """The real add paths over an in-memory config."""

    def __init__(self, tonight: int) -> None:
        self.config: tuple[int, int, int] = (tonight, tonight, 300)

    def _read_shutdown_config(self) -> tuple[int, int, int] | None:
        return self.config

    def _write_shutdown_config(
        self, mon_wed: int, thu_sun: int, morning_end: int, *, restore: bool = False
    ) -> bool:
        assert restore
        self.config = (mon_wed, thu_sun, morning_end)
        return True


@pytest.mark.usefixtures("pre_ladder")
def test_the_book_after_the_run_adds_its_hour() -> None:
    """18:00 + 2h run + 1h book = 21:00, whatever the clock says (2026-11-18)."""
    host = _Host(18 * 60)
    assert host._adjust_shutdown_time_later() is True
    assert host._adjust_shutdown_time_by(60) is True
    reward = first_minutes(earned_time.WORKOUT, date.fromisoformat(today_str()))
    assert host.config == (18 * 60 + reward + 60, 18 * 60 + reward + 60, 300)


def test_the_ceiling_still_caps_the_sum() -> None:
    """An add never pushes tonight past the day's ceiling."""
    host = _Host(22 * 60 + 30)
    host._adjust_shutdown_time_by(120)
    assert host.config[1] == ceiling(date.fromisoformat(today_str()))


def test_a_sick_day_credit_only_raises_to_the_sick_target() -> None:
    """On a sick day the credit is already in the target: raise, never add."""
    day = date.fromisoformat(today_str())
    mark_sick(day)
    host = _Host(21 * 60)
    with patch.object(_sick_floor, "sick_target", return_value=22 * 60):
        assert host._adjust_shutdown_time_by(60) is True
        assert host._adjust_shutdown_time_later() is True
    assert host.config[1] == 22 * 60
