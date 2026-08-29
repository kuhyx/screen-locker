"""Tests for run_status's weekly-total rule.

Split out of test_status.py for the 250-line cap.
"""

from __future__ import annotations

from datetime import UTC
import json
from typing import TYPE_CHECKING
from unittest.mock import patch

from screen_locker._status import run_status
from screen_locker.tests.conftest import _make_locker

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


class TestWeeklyTotalUsesPerWorkoutRule:
    """The final summary must count each verified workout, not days-with-any."""

    def test_multiple_same_day_workouts_all_count(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """One day with 2 manual + 3 verified entries = 5, not capped at 1.

        Regression test: the summary used to derive its total from a
        per-day checkmark count (max 1 per day), undercounting any day
        holding more than one counted workout — exactly what multi-workout
        days are supposed to support. Also covers manual workouts counting
        individually (no once-per-day collapse), same as verified ones.
        """
        from datetime import datetime

        today = datetime.now(tz=UTC).astimezone().date().isoformat()
        log_file = tmp_path / "log.json"
        log_file.write_text(
            json.dumps(
                {
                    today: [
                        {"workout_data": {"type": "manual_workout", "source": "gym"}},
                        {"workout_data": {"type": "runnerup_verified", "source": "a"}},
                        {"workout_data": {"type": "phone_verified", "source": "b"}},
                        {"workout_data": {"type": "runnerup_verified", "source": "c"}},
                        {"workout_data": {"type": "manual_workout", "source": "gym2"}},
                    ]
                }
            )
        )
        eb_file = tmp_path / "eb.json"
        # n_filled=0 so the summary is derived purely from before_count.
        locker = _make_locker(log_file, n_filled=0)
        with (
            patch("screen_locker._status.EXTRA_BENEFITS_FILE", eb_file),
            patch("screen_locker._status.current_streak", return_value=0),
            patch("screen_locker._status.has_extended_early_bird", return_value=False),
            patch("sys.exit"),
        ):
            run_status(locker)
        out = capsys.readouterr().out
        assert "Weekly minimum met exactly (5/5)." in out
