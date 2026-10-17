"""A credit that lands after tonight's shutdown restarts the clock from it.

kuhy, 2026-10-17: shutting down must never make a finished task impossible to
submit. A credit timed at or after tonight's shutdown moves it to the
credit's own time plus its reward (capped at the ceiling), so LeetCode done
at 19:00 after an 18:00 shutdown means 20:00. Anchored on the credit's time,
never the sync's: a workout done at 17:00 and uploaded at 19:00 is not late.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import earned_time
import pytest

from screen_locker import _grace_floor, _late_credit, _shutdown, _sick_floor
from screen_locker._earned import first_minutes
from screen_locker._grace_floor import plan_absorb, save_lift
from screen_locker._shutdown import ShutdownMixin
from screen_locker.tests._sick_helpers import mark_sick

if TYPE_CHECKING:
    from collections.abc import Iterator

# Captured before conftest pins it to noon for every test.
_REAL_NOW = _late_credit._now

_DAY = date(2026, 10, 17)  # a Saturday: the Thu-Sun band is tonight's
_ISO = _DAY.isoformat()


def at(hhmm: str, day: date = _DAY) -> float:
    """Unix time of ``hhmm`` local on ``day``."""
    hour, minute = (int(p) for p in hhmm.split(":"))
    return datetime(day.year, day.month, day.day, hour, minute).astimezone().timestamp()


def host_workout_minutes() -> int:
    return first_minutes(earned_time.WORKOUT, _DAY)


def m(hhmm: str) -> int:
    hour, minute = (int(p) for p in hhmm.split(":"))
    return hour * 60 + minute


class Host(ShutdownMixin):
    """The real add paths over an in-memory config."""

    def __init__(self, tonight: str, *, ok: bool = True) -> None:
        self.config: tuple[int, int, int] = (m(tonight), m(tonight), 300)
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

    @property
    def tonight(self) -> int:
        return self.config[1]


@pytest.fixture(autouse=True)
def _on_the_day() -> Iterator[Any]:
    with (
        patch.object(_sick_floor, "today_str", return_value=_ISO),
        patch.object(_grace_floor, "today_str", return_value=_ISO),
        patch.object(_shutdown, "today_str", return_value=_ISO),
        patch.object(_late_credit, "today_str", return_value=_ISO),
    ):
        yield


class TestLateCredit:
    def test_a_credit_before_the_shutdown_adds_as_before(self) -> None:
        host = Host("20:00")
        assert host._adjust_shutdown_time_by(60, at=at("18:30")) is True
        assert host.tonight == m("21:00")

    def test_a_credit_after_the_shutdown_counts_from_its_own_time(self) -> None:
        host = Host("18:00")
        assert host._adjust_shutdown_time_by(60, at=at("19:00")) is True
        assert host.tonight == m("20:00")
        assert host.config[0] == m("20:00")  # both bands, like the floors

    def test_a_credit_exactly_at_the_shutdown_is_late(self) -> None:
        """The check script locks at ``now >= shutdown``."""
        host = Host("19:00")
        host._adjust_shutdown_time_by(60, at=at("19:00"))
        assert host.tonight == m("20:00")

    def test_capped_at_the_ceiling(self) -> None:
        host = Host("22:30")
        host._adjust_shutdown_time_by(120, at=at("22:45"))
        assert host.tonight == m("23:00")

    def test_after_the_ceiling_nothing_moves_past_it(self) -> None:
        host = Host("23:00")
        host._adjust_shutdown_time_by(60, at=at("23:10"))
        assert host.tonight == m("23:00")

    def test_a_late_upload_is_not_a_late_credit(self) -> None:
        """Done at 17:00, synced at 19:00: 18:00 + 2 h, not 19:00 + 2 h."""
        host = Host("18:00")
        assert host._adjust_shutdown_time_later(at=at("17:00")) is True
        assert host.tonight == m("18:00") + host_workout_minutes()

    def test_a_late_workout_counts_from_its_end(self) -> None:
        host = Host("18:00")
        host._adjust_shutdown_time_later(at=at("19:00"))
        assert host.tonight == min(m("23:00"), m("19:00") + host_workout_minutes())

    def test_a_credit_timed_on_another_day_is_never_late(self) -> None:
        host = Host("18:00")
        host._adjust_shutdown_time_by(60, at=at("19:00", date(2026, 10, 16)))
        assert host.tonight == m("19:00")

    def test_no_time_means_now(self) -> None:
        host = Host("18:00")
        with patch.object(_late_credit, "_now", return_value=at("19:30")):
            host._adjust_shutdown_time_by(60)
        assert host.tonight == m("20:30")

    def test_now_is_the_wall_clock(self) -> None:
        with patch.object(_late_credit.time, "time", return_value=123.0):
            assert _REAL_NOW() == 123.0

    def test_a_late_credit_clears_the_lift(self) -> None:
        """Past the shutdown the floor is spent: nothing is left to absorb."""
        save_lift(30)
        host = Host("18:00")
        host._adjust_shutdown_time_by(60, at=at("19:00"))
        assert host.tonight == m("20:00")
        assert plan_absorb(60) == (60, 0)

    def test_a_failed_write_keeps_the_lift(self) -> None:
        save_lift(30)
        host = Host("18:00", ok=False)
        assert host._adjust_shutdown_time_by(60, at=at("19:00")) is False
        assert plan_absorb(0) == (0, 30)

    def test_unreadable_config_fails(self) -> None:
        host = Host("18:00")
        with patch.object(Host, "_read_shutdown_config", return_value=None):
            assert host._adjust_shutdown_time_by(60, at=at("19:00")) is False


class TestLateOnASickDay:
    def test_late_after_the_sick_target(self) -> None:
        mark_sick(_DAY)
        host = Host("20:00")
        with patch.object(_sick_floor, "sick_target", return_value=m("20:00")):
            assert host._adjust_shutdown_time_by(60, at=at("21:00")) is True
        assert host.tonight == m("22:00")

    def test_not_late_raises_to_the_target_only(self) -> None:
        mark_sick(_DAY)
        host = Host("21:00")
        with patch.object(_sick_floor, "sick_target", return_value=m("22:00")):
            host._adjust_shutdown_time_by(60, at=at("15:00"))
        assert host.tonight == m("22:00")
