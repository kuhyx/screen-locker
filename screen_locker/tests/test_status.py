"""Tests for screen_locker._status.run_status()."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker._status import _load_extra_benefits, run_status
from screen_locker.tests.conftest import _make_locker

if TYPE_CHECKING:
    import pytest

# ---------------------------------------------------------------------------
# _load_extra_benefits helpers
# ---------------------------------------------------------------------------


class TestLoadExtraBenefits:
    """Tests for _load_extra_benefits."""

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        """Non-existent EXTRA_BENEFITS_FILE → {}."""
        with patch("screen_locker._status.EXTRA_BENEFITS_FILE", tmp_path / "nope.json"):
            assert _load_extra_benefits() == {}

    def test_valid_json_returned(self, tmp_path: Path) -> None:
        """Valid JSON → dict."""
        f = tmp_path / "eb.json"
        f.write_text(json.dumps({"skip_credits": 2}))
        with patch("screen_locker._status.EXTRA_BENEFITS_FILE", f):
            assert _load_extra_benefits() == {"skip_credits": 2}

    def test_invalid_json_returns_empty(self, tmp_path: Path) -> None:
        """ValueError (invalid JSON) → {}."""
        f = tmp_path / "eb.json"
        f.write_text("{bad}")
        with patch("screen_locker._status.EXTRA_BENEFITS_FILE", f):
            assert _load_extra_benefits() == {}

    def test_oserror_returns_empty(self, tmp_path: Path) -> None:
        """OSError on read_text → {}."""
        f = tmp_path / "eb.json"
        f.write_text("{}")
        with (
            patch("screen_locker._status.EXTRA_BENEFITS_FILE", f),
            patch.object(Path, "read_text", side_effect=OSError("perm")),
        ):
            assert _load_extra_benefits() == {}


# ---------------------------------------------------------------------------
# run_status integration tests
# ---------------------------------------------------------------------------


class TestRunStatusNormal:
    """Tests for run_status display paths (no workouts in log)."""

    def test_empty_log_no_fill(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Empty log, no RunnerUp fill → 'No new workouts found', need-more message."""
        eb_file = tmp_path / "eb.json"
        log_file = tmp_path / "log.json"
        locker = _make_locker(log_file, n_filled=0)
        with (
            patch("screen_locker._status.EXTRA_BENEFITS_FILE", eb_file),
            patch("screen_locker._status.current_streak", return_value=0),
            patch("screen_locker._status.has_extended_early_bird", return_value=False),
            patch("screen_locker._status.count_weekly_workouts", return_value=0),
            patch("sys.exit"),
        ):
            run_status(locker)
        out = capsys.readouterr().out
        assert "No new workouts found" in out
        assert "Need" in out

    def test_full_week_no_break_when_today_is_sunday(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Today == the week's Sunday: the per-day loop runs all 7 days, never breaking early."""
        from datetime import datetime, timezone

        fixed_now = datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)  # a real Sunday
        eb_file = tmp_path / "eb.json"
        log_file = tmp_path / "log.json"
        locker = _make_locker(log_file, n_filled=0)
        mock_datetime_cls = MagicMock()
        mock_datetime_cls.now.return_value = fixed_now
        with (
            patch("screen_locker._status.datetime", mock_datetime_cls),
            patch("screen_locker._status.EXTRA_BENEFITS_FILE", eb_file),
            patch("screen_locker._status.current_streak", return_value=0),
            patch("screen_locker._status.has_extended_early_bird", return_value=False),
            patch("screen_locker._status.count_weekly_workouts", return_value=0),
            patch("sys.exit"),
        ):
            run_status(locker)
        out = capsys.readouterr().out
        assert out.count("no entry") == 7

    def test_sick_day_shown_when_no_log_entry(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """A date with no workout_log entry but in sick_history → shown as sick_day."""
        from datetime import datetime, timezone

        today = datetime.now(tz=timezone.utc).astimezone().date().isoformat()
        eb_file = tmp_path / "eb.json"
        log_file = tmp_path / "log.json"
        history_file = tmp_path / "sick_history.json"
        history_file.write_text(json.dumps({"sick_days": [today]}))
        locker = _make_locker(log_file, n_filled=0)
        with (
            patch("screen_locker._status.EXTRA_BENEFITS_FILE", eb_file),
            patch("screen_locker._status.current_streak", return_value=0),
            patch("screen_locker._status.has_extended_early_bird", return_value=False),
            patch("screen_locker._status.count_weekly_workouts", return_value=0),
            patch("sys.exit"),
        ):
            run_status(locker)
        out = capsys.readouterr().out
        assert "sick_day" in out

    def test_shutdown_config_printed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Shutdown config present → shutdown time line shown."""
        eb_file = tmp_path / "eb.json"
        locker = _make_locker(tmp_path / "log.json", cfg=(22, 22, 5))
        with (
            patch("screen_locker._status.EXTRA_BENEFITS_FILE", eb_file),
            patch("screen_locker._status.current_streak", return_value=0),
            patch("screen_locker._status.has_extended_early_bird", return_value=False),
            patch("screen_locker._status.count_weekly_workouts", return_value=0),
            patch("sys.exit"),
        ):
            run_status(locker)
        out = capsys.readouterr().out
        assert "Shutdown tonight" in out
        assert "22:00" in out

    def test_no_shutdown_config(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Shutdown config None → no shutdown line."""
        eb_file = tmp_path / "eb.json"
        locker = _make_locker(tmp_path / "log.json", cfg=None)
        with (
            patch("screen_locker._status.EXTRA_BENEFITS_FILE", eb_file),
            patch("screen_locker._status.current_streak", return_value=0),
            patch("screen_locker._status.has_extended_early_bird", return_value=False),
            patch("screen_locker._status.count_weekly_workouts", return_value=0),
            patch("sys.exit"),
        ):
            run_status(locker)
        out = capsys.readouterr().out
        assert "Shutdown tonight" not in out

    def test_shutdown_bonus_and_streak_shown(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """bonus_hours=3, streak=2, eb_ext=True → shown in output."""
        eb_file = tmp_path / "eb.json"
        locker = _make_locker(tmp_path / "log.json", n_filled=0)
        with (
            patch("screen_locker._status.EXTRA_BENEFITS_FILE", eb_file),
            patch("screen_locker._status.weekly_shutdown_bonus_hours", return_value=3),
            patch("screen_locker._status.current_streak", return_value=2),
            patch("screen_locker._status.has_extended_early_bird", return_value=True),
            patch("screen_locker._status.count_weekly_workouts", return_value=0),
            patch("sys.exit"),
        ):
            run_status(locker)
        out = capsys.readouterr().out
        assert "Shutdown bonus (this wk): 3h" in out
        assert "Streak (5+ wks)     : 2" in out
        assert "Yes — until 09:00" in out


class TestRunStatusWorkoutLog:
    """Tests for per-day log display and counted/uncounted workout marking."""

    def test_counted_entry_shown_with_checkmark(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Log entry with counted type → ✓ mark printed."""
        from datetime import datetime, timezone

        today = datetime.now(tz=timezone.utc).astimezone().date().isoformat()
        log_file = tmp_path / "log.json"
        log_file.write_text(
            json.dumps(
                {
                    today: {
                        "workout_data": {
                            "type": "runnerup_verified",
                            "source": "run.tcx",
                        }
                    }
                }
            )
        )
        eb_file = tmp_path / "eb.json"
        locker = _make_locker(log_file, n_filled=0)
        with (
            patch("screen_locker._status.EXTRA_BENEFITS_FILE", eb_file),
            patch("screen_locker._status.current_streak", return_value=0),
            patch("screen_locker._status.has_extended_early_bird", return_value=False),
            patch("screen_locker._status.count_weekly_workouts", return_value=1),
            patch("sys.exit"),
        ):
            run_status(locker)
        out = capsys.readouterr().out
        assert "✓" in out
        assert "runnerup_verified" in out
        assert "run.tcx" in out

    def test_uncounted_entry_shown_with_x(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Log entry with uncounted type → ✗ mark printed."""
        from datetime import datetime, timezone

        today = datetime.now(tz=timezone.utc).astimezone().date().isoformat()
        log_file = tmp_path / "log.json"
        log_file.write_text(
            json.dumps({today: {"workout_data": {"type": "heat_skip", "source": ""}}})
        )
        eb_file = tmp_path / "eb.json"
        locker = _make_locker(log_file, n_filled=0)
        with (
            patch("screen_locker._status.EXTRA_BENEFITS_FILE", eb_file),
            patch("screen_locker._status.current_streak", return_value=0),
            patch("screen_locker._status.has_extended_early_bird", return_value=False),
            patch("screen_locker._status.count_weekly_workouts", return_value=0),
            patch("sys.exit"),
        ):
            run_status(locker)
        out = capsys.readouterr().out
        assert "heat_skip" in out


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
        from datetime import datetime, timezone

        today = datetime.now(tz=timezone.utc).astimezone().date().isoformat()
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
