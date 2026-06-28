"""Tests for screen_locker._status.run_status()."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker._status import _load_extra_benefits, _load_log, run_status

if TYPE_CHECKING:
    import pytest

# ---------------------------------------------------------------------------
# _load_log helpers
# ---------------------------------------------------------------------------


class TestLoadLog:
    """Tests for _load_log."""

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        """Non-existent file → {}."""
        assert _load_log(tmp_path / "nope.json") == {}

    def test_valid_json_returned(self, tmp_path: Path) -> None:
        """Valid JSON file → contents."""
        f = tmp_path / "log.json"
        f.write_text(json.dumps({"2026-06-01": {"x": 1}}))
        assert _load_log(f) == {"2026-06-01": {"x": 1}}

    def test_invalid_json_returns_empty(self, tmp_path: Path) -> None:
        """Corrupt JSON → {}."""
        f = tmp_path / "log.json"
        f.write_text("{not json}")
        assert _load_log(f) == {}

    def test_oserror_returns_empty(self, tmp_path: Path) -> None:
        """OSError on open → {}."""
        f = tmp_path / "log.json"
        f.write_text("{}")
        with patch("builtins.open", side_effect=OSError("perm")):
            assert _load_log(f) == {}


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


def _make_locker(
    log_file: Path,
    *,
    n_filled: int = 0,
    bonus_applied: bool = False,
    cfg: tuple | None = (22, 22, 5),
) -> SimpleNamespace:
    """Build a minimal locker-like namespace for run_status."""
    locker = SimpleNamespace(
        log_file=log_file,
        workout_data={},
    )
    locker._scan_and_fill_week_runnerup = MagicMock(return_value=n_filled)
    locker._adjust_shutdown_time_by = MagicMock(return_value=bonus_applied)
    locker._read_shutdown_config = MagicMock(return_value=cfg)
    return locker


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

    def test_skip_credits_and_streak_shown(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """skip_credits=3, streak=2, eb_ext=True → shown in output."""
        eb_file = tmp_path / "eb.json"
        eb_file.write_text(json.dumps({"skip_credits": 3}))
        locker = _make_locker(tmp_path / "log.json", n_filled=0)
        with (
            patch("screen_locker._status.EXTRA_BENEFITS_FILE", eb_file),
            patch("screen_locker._status.current_streak", return_value=2),
            patch("screen_locker._status.has_extended_early_bird", return_value=True),
            patch("screen_locker._status.count_weekly_workouts", return_value=0),
            patch("sys.exit"),
        ):
            run_status(locker)
        out = capsys.readouterr().out
        assert "Skip credits banked : 3" in out
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
            json.dumps({today: {"workout_data": {"type": "early_bird", "source": ""}}})
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
        assert "early_bird" in out


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
            def now(cls, tz=None):  # type: ignore[override]
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
