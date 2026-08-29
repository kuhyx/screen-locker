"""Tests targeting remaining screen_lock.py coverage gaps."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestTryAutoUpgradeSickDayRunnerUp:
    """Tests for RunnerUp paths in _try_auto_upgrade_sick_day (lines 273-286)."""

    def test_runnerup_exception_returns_false(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """OSError from _verify_runnerup_workout → returns False (lines 273-275)."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_verify_phone_workout",
            MagicMock(return_value=("no_phone", "no phone")),
        )
        object.__setattr__(
            locker,
            "_verify_runnerup_workout",
            MagicMock(side_effect=OSError("adb fail")),
        )
        assert locker._try_auto_upgrade_sick_day() is False

    def test_runnerup_verified_saves_entry(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """RunnerUp returns verified → saves runnerup_verified entry (lines 281-286)."""
        log_file = tmp_path / "log.json"
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        locker.workout_data = {}
        object.__setattr__(
            locker,
            "_verify_phone_workout",
            MagicMock(return_value=("no_phone", "no phone")),
        )
        object.__setattr__(
            locker,
            "_verify_runnerup_workout",
            MagicMock(return_value=("verified", "Running: 6 km in 40 min")),
        )
        object.__setattr__(
            locker, "_adjust_shutdown_time_later", MagicMock(return_value=True)
        )
        with patch("screen_locker._log_mixin.compute_entry_hmac", return_value=None):
            result = locker._try_auto_upgrade_sick_day()

        assert result is True
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        data = json.loads(log_file.read_text())
        assert data[today][0]["workout_data"]["type"] == "runnerup_verified"
        assert data[today][0]["workout_data"]["after_sick_day"] == "true"

    def test_runnerup_not_verified_returns_false(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """RunnerUp not verified → returns False."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_verify_phone_workout",
            MagicMock(return_value=("no_phone", "no phone")),
        )
        object.__setattr__(
            locker,
            "_verify_runnerup_workout",
            MagicMock(return_value=("not_verified", "no run")),
        )
        assert locker._try_auto_upgrade_sick_day() is False


class TestTryAutoUpgradeEarlyBirdRunnerUp:
    """Tests for RunnerUp paths in screen_lock.py _try_auto_upgrade_early_bird (305-318)."""

    def test_runnerup_exception_returns_false(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """RuntimeError from _verify_runnerup_workout → returns False (lines 305-307)."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_verify_phone_workout",
            MagicMock(return_value=("no_phone", "no phone")),
        )
        object.__setattr__(
            locker,
            "_verify_runnerup_workout",
            MagicMock(side_effect=RuntimeError("adb gone")),
        )
        assert locker._try_auto_upgrade_early_bird() is False

    def test_runnerup_verified_saves_entry(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """RunnerUp returns verified → saves runnerup_verified entry (lines 313-318)."""
        log_file = tmp_path / "log.json"
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        locker.workout_data = {}
        object.__setattr__(
            locker,
            "_verify_phone_workout",
            MagicMock(return_value=("no_phone", "no phone")),
        )
        object.__setattr__(
            locker,
            "_verify_runnerup_workout",
            MagicMock(return_value=("verified", "Running: 6 km in 40 min")),
        )
        object.__setattr__(
            locker, "_adjust_shutdown_time_later", MagicMock(return_value=True)
        )
        with patch("screen_locker._log_mixin.compute_entry_hmac", return_value=None):
            result = locker._try_auto_upgrade_early_bird()

        assert result is True
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        data = json.loads(log_file.read_text())
        assert data[today][0]["workout_data"]["type"] == "runnerup_verified"
        assert data[today][0]["workout_data"]["after_early_bird"] == "true"

    def test_runnerup_not_verified_returns_false(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """RunnerUp not verified → returns False."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_verify_phone_workout",
            MagicMock(return_value=("no_phone", "no phone")),
        )
        object.__setattr__(
            locker,
            "_verify_runnerup_workout",
            MagicMock(return_value=("not_verified", "no run")),
        )
        assert locker._try_auto_upgrade_early_bird() is False


class TestSyncNow:
    """Tests for sync_now, the public entry point behind ``--sync-only``."""

    def test_runs_one_full_sync_pass(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """The timer unit's entry point must actually push and ingest.

        ``workout-sync.timer`` calls this headlessly; if it stopped delegating,
        the timer would run and silently sync nothing.
        """
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch(
                "screen_locker._sync_mixin.pull_all_manual_records",
                return_value=[("manual:x", {})],
            ),
            patch("screen_locker._sync_mixin.push_pc_workouts") as push,
            patch(
                "screen_locker._sync_mixin.ingest_manual_records",
                return_value=["manual:x"],
            ) as ingest,
        ):
            locker.sync_now()
        push.assert_called_once()
        ingest.assert_called_once()
