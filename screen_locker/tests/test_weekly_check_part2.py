"""Tests for _weekly_check.has_weekly_minimum.

Split out of test_weekly_check.py for the 250-line cap; the shared _dt /
_make_log helpers stay in that module and are imported here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from screen_locker._weekly_check import (
    WEEKLY_WORKOUT_MINIMUM,
    has_weekly_minimum,
)
from screen_locker.tests.test_weekly_check import _dt, _make_log

if TYPE_CHECKING:
    from pathlib import Path


class TestHasWeeklyMinimum:
    """has_weekly_minimum counts verified workouts against the weekly bar."""

    def test_zero_workouts_is_false(self, tmp_path: Path) -> None:
        """An empty log does not meet the weekly minimum."""
        log = tmp_path / "workout_log.json"
        assert has_weekly_minimum(log, today=_dt(4)) is False

    def test_three_workouts_is_false(self, tmp_path: Path) -> None:
        """Three workouts is short of the five-workout bar."""
        log = tmp_path / "workout_log.json"
        _make_log(
            {
                "2025-05-19": "phone_verified",
                "2025-05-20": "phone_verified",
                "2025-05-21": "phone_verified",
            },
            log,
        )
        assert has_weekly_minimum(log, today=_dt(4)) is False

    def test_four_workouts_is_false(self, tmp_path: Path) -> None:
        """Four workouts is still one short of the bar."""
        log = tmp_path / "workout_log.json"
        _make_log(
            {
                "2025-05-19": "phone_verified",
                "2025-05-20": "phone_verified",
                "2025-05-21": "phone_verified",
                "2025-05-22": "phone_verified",
            },
            log,
        )
        assert has_weekly_minimum(log, today=_dt(4)) is False

    def test_five_workouts_is_true(self, tmp_path: Path) -> None:
        """Five workouts meets the bar exactly."""
        log = tmp_path / "workout_log.json"
        _make_log(
            {
                "2025-05-19": "phone_verified",
                "2025-05-20": "phone_verified",
                "2025-05-21": "phone_verified",
                "2025-05-22": "phone_verified",
                "2025-05-23": "phone_verified",
            },
            log,
        )
        assert has_weekly_minimum(log, today=_dt(4)) is True

    def test_weekly_workout_minimum_constant(self) -> None:
        """The bar is five workouts per ISO week."""
        assert WEEKLY_WORKOUT_MINIMUM == 5
