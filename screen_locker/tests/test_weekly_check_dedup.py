"""Tests for the StrongLifts credit-key dedup in _weekly_check.

Regression cover for 2026-08-29: one StrongLifts session is ingested through
two independent paths -- the phone sync (``phone_verified``) and the PC session
sync (``pc_workout_verified``) -- and ``workout_id`` is ``"<type>:<date>"``, so
the two copies of one workout got different IDs and both survived into
``log.json``. ``count_weekly_workouts`` then counted each entry individually,
the week reached 5/5 two workouts early, and ``has_weekly_minimum`` disabled
enforcement for two consecutive weeks without anything reporting a problem.

The fixtures below are the real log entries from those days, not invented ones:
the point of the bug is that the two halves look like separate workouts unless
you notice the matching durations.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import TYPE_CHECKING, Any

from screen_locker._weekly_check import (
    count_weekly_workouts,
    has_weekly_minimum,
)

if TYPE_CHECKING:
    from pathlib import Path

# Saturday of the ISO week beginning Monday 2026-08-24 -- the day the locker
# was expected to fire and did not.
_SATURDAY_2026_08_29 = datetime(2026, 8, 29, 21, 0, 0, tzinfo=UTC)


def _entry(wtype: str, *, timestamp: str, source: str = "") -> dict[str, Any]:
    """Build one log entry of the given workout type.

    Args:
        wtype: The ``workout_data.type`` value.
        timestamp: ISO-8601 timestamp for the entry.
        source: Human-readable provenance string, as the real log carries.

    Returns:
        A log entry dict in the current on-disk shape.
    """
    return {
        "timestamp": timestamp,
        "workout_data": {"type": wtype, "source": source},
        "workout_id": f"{wtype}:{timestamp[:10]}",
    }


def _write_log(days: dict[str, list[dict[str, Any]]], log_file: Path) -> Path:
    """Write a log.json in the current ``{date: [entry, ...]}`` shape.

    Args:
        days: Mapping of ``YYYY-MM-DD`` to its list of entries.
        log_file: Destination path.

    Returns:
        ``log_file``, for convenience at call sites.
    """
    log_file.write_text(json.dumps(days, indent=2), encoding="utf-8")
    return log_file


def _real_week_2026_08_24() -> dict[str, list[dict[str, Any]]]:
    """Return the real log contents for the ISO week of 2026-08-24.

    Three genuine workouts -- a StrongLifts session on Monday, padel on
    Thursday, a StrongLifts session on Friday -- recorded as five entries,
    because both StrongLifts sessions were ingested twice.

    Returns:
        The date-keyed log fragment for that week.
    """
    return {
        "2026-08-24": [
            _entry(
                "pc_workout_verified",
                timestamp="2026-08-24T10:55:29.565673+00:00",
                source="StrongLifts workout A (118 min, all succeeded)",
            ),
            _entry(
                "phone_verified",
                timestamp="2026-08-24T10:55:38.274973+00:00",
                source="Workout verified! (118 min, all succeeded)",
            ),
        ],
        "2026-08-27": [
            _entry(
                "manual_workout",
                timestamp="2026-08-27T18:45:32.328067+00:00",
                source="padel at Padel PGE Narodowy",
            ),
        ],
        "2026-08-28": [
            _entry(
                "phone_verified",
                timestamp="2026-08-28T09:24:00.798562+00:00",
                source="Workout verified! (113 min, all succeeded)",
            ),
            _entry(
                "pc_workout_verified",
                timestamp="2026-08-28T09:30:07.715751+00:00",
                source="StrongLifts workout B (113 min, all succeeded)",
            ),
        ],
    }


class TestStrongliftsDoubleCountRegression:
    """The 2026-08-29 outage: five entries, three workouts, no lock."""

    def test_real_week_counts_three_not_five(self, tmp_path: Path) -> None:
        """The week of 2026-08-24 holds three workouts, not five entries."""
        log = _write_log(_real_week_2026_08_24(), tmp_path / "log.json")
        assert count_weekly_workouts(log, today=_SATURDAY_2026_08_29) == 3

    def test_real_week_does_not_meet_the_minimum(self, tmp_path: Path) -> None:
        """Three workouts is short of five, so enforcement must not be waived."""
        log = _write_log(_real_week_2026_08_24(), tmp_path / "log.json")
        assert has_weekly_minimum(log, today=_SATURDAY_2026_08_29) is False

    def test_phone_and_pc_on_one_day_share_one_credit(
        self,
        tmp_path: Path,
    ) -> None:
        """Both ingestion paths for one session count once between them."""
        log = _write_log(
            {
                "2026-08-24": [
                    _entry("phone_verified", timestamp="2026-08-24T10:55:38+00:00"),
                    _entry(
                        "pc_workout_verified",
                        timestamp="2026-08-24T10:55:29+00:00",
                    ),
                ],
            },
            tmp_path / "log.json",
        )
        assert count_weekly_workouts(log, today=_SATURDAY_2026_08_29) == 1

    def test_phone_and_pc_on_different_days_count_separately(
        self,
        tmp_path: Path,
    ) -> None:
        """The collapse is per-day: two days of StrongLifts are two workouts."""
        log = _write_log(
            {
                "2026-08-24": [
                    _entry("phone_verified", timestamp="2026-08-24T10:00:00+00:00"),
                ],
                "2026-08-25": [
                    _entry(
                        "pc_workout_verified",
                        timestamp="2026-08-25T10:00:00+00:00",
                    ),
                ],
            },
            tmp_path / "log.json",
        )
        assert count_weekly_workouts(log, today=_SATURDAY_2026_08_29) == 2
