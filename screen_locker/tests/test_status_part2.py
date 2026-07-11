"""Tests for screen_locker._status.run_status() -- RunnerUp fill + minimum summary.

Split from test_status.py to stay under the repo's 400-line file limit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker._status import run_status
from screen_locker.tests.conftest import _make_locker

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


class TestRunStatusFill:
    """Tests for RunnerUp scan paths in run_status."""

    def test_fill_with_bonus_applied(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """n_filled > 0, bonus > 0, adjust succeeds → bonus line shown."""
        eb_file = tmp_path / "eb.json"
        locker = _make_locker(tmp_path / "log.json", n_filled=2, bonus_applied=True)
        # after_count=5 (> WEEKLY_WORKOUT_MINIMUM=4), before_count=3
        with (
            patch("screen_locker._status.EXTRA_BENEFITS_FILE", eb_file),
            patch("screen_locker._status.current_streak", return_value=0),
            patch("screen_locker._status.has_extended_early_bird", return_value=False),
            patch("screen_locker._status.count_weekly_workouts", return_value=5),
            patch("sys.exit"),
        ):
            run_status(locker)
        out = capsys.readouterr().out
        assert "Auto-filled 2 workout(s)" in out

    def test_fill_bonus_pending_when_adjust_fails(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """n_filled > 0, bonus > 0, adjust returns False → 'bonus pending' shown."""
        eb_file = tmp_path / "eb.json"
        locker = _make_locker(tmp_path / "log.json", n_filled=2, bonus_applied=False)
        with (
            patch("screen_locker._status.EXTRA_BENEFITS_FILE", eb_file),
            patch("screen_locker._status.current_streak", return_value=0),
            patch("screen_locker._status.has_extended_early_bird", return_value=False),
            patch("screen_locker._status.count_weekly_workouts", return_value=5),
            patch("sys.exit"),
        ):
            run_status(locker)
        out = capsys.readouterr().out
        assert "bonus pending" in out

    def test_fill_no_bonus_when_still_below_min(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """n_filled=1 but count still < 4 → no bonus line."""
        eb_file = tmp_path / "eb.json"
        locker = _make_locker(tmp_path / "log.json", n_filled=1, bonus_applied=False)
        with (
            patch("screen_locker._status.EXTRA_BENEFITS_FILE", eb_file),
            patch("screen_locker._status.current_streak", return_value=0),
            patch("screen_locker._status.has_extended_early_bird", return_value=False),
            patch("screen_locker._status.count_weekly_workouts", return_value=3),
            patch("sys.exit"),
        ):
            run_status(locker)
        out = capsys.readouterr().out
        assert "shutdown bonus" not in out


class TestRunStatusMinimumStatus:
    """Tests for the 'remaining/extra/exactly met' summary lines."""

    def test_extra_above_minimum(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """after_count > WEEKLY_WORKOUT_MINIMUM → 'above minimum' line.

        n_filled=1 triggers the count_weekly_workouts() branch so after_count
        is taken from that mock (5), not from the per-day log loop (0).
        """
        eb_file = tmp_path / "eb.json"
        locker = _make_locker(tmp_path / "log.json", n_filled=1, bonus_applied=False)
        with (
            patch("screen_locker._status.EXTRA_BENEFITS_FILE", eb_file),
            patch("screen_locker._status.current_streak", return_value=0),
            patch("screen_locker._status.has_extended_early_bird", return_value=False),
            patch("screen_locker._status.count_weekly_workouts", return_value=5),
            patch("sys.exit"),
        ):
            run_status(locker)
        out = capsys.readouterr().out
        assert "above minimum" in out

    def test_exactly_at_minimum(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """after_count == WEEKLY_WORKOUT_MINIMUM → 'met exactly' line.

        n_filled=1 so after_count = count_weekly_workouts() = 4 = WEEKLY_WORKOUT_MINIMUM.
        bonus = max(0, 4 - max(4, 0)) = 0, so no bonus line is printed.
        """
        eb_file = tmp_path / "eb.json"
        locker = _make_locker(tmp_path / "log.json", n_filled=1, bonus_applied=False)
        with (
            patch("screen_locker._status.EXTRA_BENEFITS_FILE", eb_file),
            patch("screen_locker._status.current_streak", return_value=0),
            patch("screen_locker._status.has_extended_early_bird", return_value=False),
            patch("screen_locker._status.count_weekly_workouts", return_value=4),
            patch("sys.exit"),
        ):
            run_status(locker)
        out = capsys.readouterr().out
        assert "Weekly minimum met exactly" in out

    def test_sys_exit_called(self, tmp_path: Path) -> None:
        """run_status always calls sys.exit(0)."""
        eb_file = tmp_path / "eb.json"
        locker = _make_locker(tmp_path / "log.json", n_filled=0)
        mock_exit = MagicMock()
        with (
            patch("screen_locker._status.EXTRA_BENEFITS_FILE", eb_file),
            patch("screen_locker._status.current_streak", return_value=0),
            patch("screen_locker._status.has_extended_early_bird", return_value=False),
            patch("screen_locker._status.count_weekly_workouts", return_value=0),
            patch("sys.exit", mock_exit),
        ):
            run_status(locker)
        mock_exit.assert_called_once_with(0)

    def test_loop_breaks_on_future_day(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Pin today to Monday so the loop hits d > today on day 2, covering line 64."""
        from datetime import datetime, timezone

        fake_now = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)

        class _FakeDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return fake_now.astimezone(tz) if tz else fake_now

        with (
            patch("screen_locker._status.datetime", _FakeDatetime),
            patch("screen_locker._status.EXTRA_BENEFITS_FILE", tmp_path / "eb.json"),
            patch("screen_locker._status.current_streak", return_value=0),
            patch("screen_locker._status.has_extended_early_bird", return_value=False),
            patch("screen_locker._status.count_weekly_workouts", return_value=0),
            patch("sys.exit"),
        ):
            run_status(_make_locker(tmp_path / "log.json", n_filled=0))
        out = capsys.readouterr().out
        assert "Mon Jun 22" in out
        assert "Tue Jun 23" not in out
