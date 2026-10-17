"""The live sick day: tonight is raised to 20:00 plus the day's gaming pay.

Since earned_time 0.13.0 credits stack on 20:00 at gaming pay (kuhy,
2026-10-17: LeetCode + reading on a sick day is 22:00, not 20:10). The pass
raises to the derived target (``_sick_floor.sick_target``) and records no
lift, so nothing is absorbed.
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


def _target(minutes: int) -> Any:
    return patch.object(_sick_floor, "sick_target", return_value=minutes)


class TestApplySickFloor:
    def test_not_sick_does_nothing(self) -> None:
        host = Host((18 * 60, 18 * 60, 300))
        assert host._apply_sick_floor() is False
        assert host.config == (18 * 60, 18 * 60, 300)

    def test_a_kept_workout_lock_does_not_lift_the_floor_away(self) -> None:
        """The 20:00 floor is the day's, not the workout lock's: keep is moot."""
        mark_sick(_DAY, keep=[sickdays.LOCKER_WORKOUT])
        host = Host((18 * 60, 18 * 60 + 30, 300))
        with _target(_FLOOR):
            assert host._apply_sick_floor() is True
        assert host.config == (_FLOOR, _FLOOR, 300)

    def test_raises_to_the_derived_target_and_records_no_lift(self) -> None:
        mark_sick(_DAY)
        host = Host((18 * 60, 20 * 60 + 10, 300))
        with _target(22 * 60):
            assert host._apply_sick_floor() is True
        assert host.config == (22 * 60, 22 * 60, 300)
        assert plan_absorb(60) == (60, 0)

    def test_already_at_or_above_the_target_is_left_alone(self) -> None:
        mark_sick(_DAY)
        host = Host((21 * 60, 21 * 60, 300))
        with _target(21 * 60):
            assert host._apply_sick_floor() is False
        assert host.config == (21 * 60, 21 * 60, 300)

    def test_unreadable_config_is_logged(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        mark_sick(_DAY)
        with caplog.at_level(logging.WARNING), _target(_FLOOR):
            assert Host(None)._apply_sick_floor() is False
        assert "config unreadable" in caplog.text

    def test_failed_write_is_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        mark_sick(_DAY)
        with caplog.at_level(logging.WARNING), _target(_FLOOR):
            assert Host((18 * 60, 18 * 60, 300), ok=False)._apply_sick_floor() is False
        assert "failed to write" in caplog.text

    def test_the_target_is_the_derived_sick_resolution(self) -> None:
        mark_sick(_DAY)
        with patch.object(_sick_floor, "gather") as gather:
            gather.return_value.minutes = 22 * 60
            assert _sick_floor.sick_target(_DAY, None) == 22 * 60
        gather.assert_called_once_with(_DAY, None)


class TestStackingAtGamingPay:
    def test_a_workout_on_a_sick_day_lands_on_the_target(self) -> None:
        host = Host((_FLOOR, _FLOOR, 300))
        mark_sick(_DAY)
        with _target(22 * 60):
            assert host._adjust_shutdown_time_later() is True
        assert host.config == (22 * 60, 22 * 60, 300)

    def test_a_flat_credit_is_not_added_on_top_of_the_target(self) -> None:
        """The ledger row is already in the derived sum: adding would pay twice."""
        host = Host((21 * 60, 21 * 60, 300))
        mark_sick(_DAY)
        with _target(22 * 60):
            assert host._adjust_shutdown_time_by(60) is True
        assert host.config == (22 * 60, 22 * 60, 300)

    def test_not_sick_still_adds(self) -> None:
        host = Host((19 * 60, 19 * 60, 300))
        assert host._adjust_shutdown_time_by(60) is True
        assert host.config == (20 * 60, 20 * 60, 300)
