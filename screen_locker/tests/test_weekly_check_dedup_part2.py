"""Tests that the StrongLifts dedup does not collapse unrelated workouts.

Split out of test_weekly_check_dedup.py for the 250-line cap; the shared
fixture helpers stay in that module and are imported here.

These are the guard rail on the other side of the 2026-08-29 fix: collapsing
the two StrongLifts ingestion paths must not turn into "one workout per day",
which would quietly undercount a genuine double session and lock on a day that
was actually earned.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from screen_locker._weekly_check import count_weekly_workouts
from screen_locker.tests.test_weekly_check_dedup import (
    _SATURDAY_2026_08_29,
    _entry,
    _write_log,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestDedupDoesNotOverCollapse:
    """Only the two StrongLifts ingestion paths share a slot -- nothing else."""

    def test_two_runs_on_one_day_both_count(self, tmp_path: Path) -> None:
        """Verified runs are machine-checked, so multiple per day still count."""
        log = _write_log(
            {
                "2026-08-24": [
                    _entry(
                        "runnerup_verified",
                        timestamp="2026-08-24T07:00:00+00:00",
                    ),
                    _entry(
                        "runnerup_verified",
                        timestamp="2026-08-24T19:00:00+00:00",
                    ),
                ],
            },
            tmp_path / "log.json",
        )
        assert count_weekly_workouts(log, today=_SATURDAY_2026_08_29) == 2

    def test_manual_and_phone_on_one_day_both_count(self, tmp_path: Path) -> None:
        """A manual workout is a different session from a StrongLifts one."""
        log = _write_log(
            {
                "2026-08-24": [
                    _entry("manual_workout", timestamp="2026-08-24T08:00:00+00:00"),
                    _entry("phone_verified", timestamp="2026-08-24T18:00:00+00:00"),
                ],
            },
            tmp_path / "log.json",
        )
        assert count_weekly_workouts(log, today=_SATURDAY_2026_08_29) == 2

    def test_two_manual_workouts_on_one_day_both_count(
        self,
        tmp_path: Path,
    ) -> None:
        """The manual-workout budget is the limiter, not a per-day collapse."""
        log = _write_log(
            {
                "2026-08-24": [
                    _entry("manual_workout", timestamp="2026-08-24T08:00:00+00:00"),
                    _entry("manual_workout", timestamp="2026-08-24T18:00:00+00:00"),
                ],
            },
            tmp_path / "log.json",
        )
        assert count_weekly_workouts(log, today=_SATURDAY_2026_08_29) == 2

    def test_lone_phone_verified_still_counts(self, tmp_path: Path) -> None:
        """A phone session with no PC twin is one workout, not zero."""
        log = _write_log(
            {
                "2026-08-24": [
                    _entry("phone_verified", timestamp="2026-08-24T10:00:00+00:00"),
                ],
            },
            tmp_path / "log.json",
        )
        assert count_weekly_workouts(log, today=_SATURDAY_2026_08_29) == 1

    def test_lone_pc_workout_still_counts(self, tmp_path: Path) -> None:
        """A PC session with no phone twin is one workout, not zero."""
        log = _write_log(
            {
                "2026-08-24": [
                    _entry(
                        "pc_workout_verified",
                        timestamp="2026-08-24T10:00:00+00:00",
                    ),
                ],
            },
            tmp_path / "log.json",
        )
        assert count_weekly_workouts(log, today=_SATURDAY_2026_08_29) == 1

    def test_relaxed_day_skip_never_counts(self, tmp_path: Path) -> None:
        """A skip marker is a UI dismissal, not a workout, twin or not."""
        log = _write_log(
            {
                "2026-08-25": [
                    _entry("relaxed_day_skip", timestamp="2026-08-25T18:00:00+00:00"),
                ],
            },
            tmp_path / "log.json",
        )
        assert count_weekly_workouts(log, today=_SATURDAY_2026_08_29) == 0
