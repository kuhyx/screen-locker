"""The live sick floor: a day marked sick after its reset is lifted to 20:00.

The lift is recorded like the grace lift, so a workout credited afterwards is
paid out of it first and lands on max(20:00, ladder) -- not 20:00 plus the
workout's whole reward.
"""

from __future__ import annotations

from datetime import date
import logging
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import earned_time
import pytest
import sickdays

from screen_locker import _grace_floor, _shutdown, _sick_floor
from screen_locker._earned import first_minutes
from screen_locker._grace_floor import plan_absorb
from screen_locker._shutdown import ShutdownMixin
from screen_locker.tests._sick_helpers import mark_sick

if TYPE_CHECKING:
    from collections.abc import Iterator

# A Saturday on the ladder; any day works, the floor is 20:00 everywhere.
_DAY = date(2026, 10, 17)
_ISO = _DAY.isoformat()
_FLOOR = earned_time.SICK_SHUTDOWN_FLOOR_MINUTES


class Host(ShutdownMixin):
    """The real floor and add paths over an in-memory config."""

    def __init__(self, config: tuple[int, int, int] | None, *, ok: bool = True):
        self.config = config
        self.ok = ok

    def _read_shutdown_config(self) -> tuple[int, int, int] | None:
        return self.config

    def _write_shutdown_config(
        self, mon_wed: int, thu_sun: int, morning_end: int, *, restore: bool = False
    ) -> bool:
        assert restore
        if self.ok:
            self.config = (mon_wed, thu_sun, morning_end)
        return self.ok


@pytest.fixture(autouse=True)
def _on_the_day() -> Iterator[Any]:
    with (
        patch.object(_sick_floor, "today_str", return_value=_ISO),
        patch.object(_grace_floor, "today_str", return_value=_ISO),
        patch.object(_shutdown, "today_str", return_value=_ISO),
    ):
        yield


class TestApplySickFloor:
    def test_not_sick_does_nothing(self) -> None:
        host = Host((18 * 60, 18 * 60, 300))
        assert host._apply_sick_floor() is False
        assert host.config == (18 * 60, 18 * 60, 300)

    def test_a_kept_workout_lock_does_not_lift_the_floor_away(self) -> None:
        """The 20:00 floor is the day's, not the workout lock's: keep is moot."""
        mark_sick(_DAY, keep=[sickdays.LOCKER_WORKOUT])
        host = Host((18 * 60, 18 * 60 + 30, 300))
        assert host._apply_sick_floor() is True
        assert host.config == (_FLOOR, _FLOOR, 300)

    def test_marked_sick_lifts_to_20_00_and_records_the_lift(self) -> None:
        mark_sick(_DAY)
        host = Host((18 * 60, 18 * 60 + 30, 300))
        assert host._apply_sick_floor() is True
        # Saturday reads the Thu-Sun band (18:30): lifted by 90 minutes.
        assert host.config == (_FLOOR, _FLOOR, 300)
        assert plan_absorb(0) == (0, 90)

    def test_already_at_or_above_the_floor_is_left_alone(self) -> None:
        mark_sick(_DAY)
        host = Host((21 * 60, 21 * 60, 300))
        assert host._apply_sick_floor() is False
        assert host.config == (21 * 60, 21 * 60, 300)

    def test_unreadable_config_is_logged(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        mark_sick(_DAY)
        with caplog.at_level(logging.WARNING):
            assert Host(None)._apply_sick_floor() is False
        assert "config unreadable" in caplog.text

    def test_failed_write_records_no_lift(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        mark_sick(_DAY)
        with caplog.at_level(logging.WARNING):
            assert Host((18 * 60, 18 * 60, 300), ok=False)._apply_sick_floor() is False
        assert "failed to write" in caplog.text
        assert plan_absorb(0) == (0, 0)


class TestNoStackingOnTop:
    def test_a_workout_after_the_mark_lands_on_the_ladder_not_above_it(self) -> None:
        """Mark sick at 10:00 (18:50 -> 20:00), then a workout: the ladder value."""
        start = 18 * 60 + 50
        host = Host((start, start, 300))
        mark_sick(_DAY)
        host._apply_sick_floor()
        host._adjust_shutdown_time_later()
        ladder = start + first_minutes(earned_time.WORKOUT, _DAY)
        assert host.config is not None
        assert host.config[1] == max(_FLOOR, ladder)

    def test_a_small_credit_is_absorbed_entirely(self) -> None:
        host = Host((18 * 60, 18 * 60, 300))
        mark_sick(_DAY)
        host._apply_sick_floor()
        assert host._adjust_shutdown_time_by(60) is True
        assert host.config is not None
        assert host.config[1] == _FLOOR
        assert plan_absorb(0) == (0, 60)
