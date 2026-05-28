"""Tests for early bird auto-upgrade, has_logged_today, and init flow."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from screen_locker.screen_lock import ScreenLocker
from screen_locker.tests.conftest import (
    create_locker,
    create_locker_early_bird,
)


class TestTryAutoUpgradeEarlyBird:
    """Tests for _try_auto_upgrade_early_bird method."""

    def test_upgrade_succeeds_when_verified(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Returns True, saves phone_verified entry, adjusts shutdown."""
        log_file = tmp_path / "workout_log.json"
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        object.__setattr__(
            locker,
            "_verify_phone_workout",
            MagicMock(return_value=("verified", "Workout verified! (67 min)")),
        )
        object.__setattr__(
            locker,
            "_adjust_shutdown_time_later",
            MagicMock(return_value=True),
        )
        with patch(
            "screen_locker.screen_lock.compute_entry_hmac",
            return_value=None,
        ):
            result = locker._try_auto_upgrade_early_bird()

        assert result is True
        with log_file.open() as f:
            data: dict[str, Any] = json.load(f)
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        assert data[today]["workout_data"]["type"] == "phone_verified"
        assert data[today]["workout_data"]["after_early_bird"] == "true"

    def test_upgrade_fails_when_not_verified(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Returns False when phone shows no workout."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_verify_phone_workout",
            MagicMock(return_value=("no_phone", "No phone connected")),
        )
        assert locker._try_auto_upgrade_early_bird() is False

    def test_upgrade_fails_on_os_error(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Returns False when _verify_phone_workout raises OSError."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_verify_phone_workout",
            MagicMock(side_effect=OSError("adb fail")),
        )
        assert locker._try_auto_upgrade_early_bird() is False

    def test_upgrade_fails_on_runtime_error(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Returns False when _verify_phone_workout raises RuntimeError."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_verify_phone_workout",
            MagicMock(side_effect=RuntimeError("unexpected")),
        )
        assert locker._try_auto_upgrade_early_bird() is False


class TestHasLoggedTodayEarlyBird:
    """Tests that has_logged_today returns False for early_bird entries."""

    def test_early_bird_entry_not_counted_as_logged(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """early_bird entries must not satisfy has_logged_today."""
        log_file = tmp_path / "workout_log.json"
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        log_file.write_text(
            json.dumps({today: {"workout_data": {"type": "early_bird"}}})
        )
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        with patch(
            "screen_locker.screen_lock.verify_entry_hmac",
            return_value=True,
        ):
            assert locker.has_logged_today() is False


class TestInitEarlyBirdFlow:
    """Integration tests for early bird branches in __init__."""

    def test_init_saves_log_and_exits_during_early_bird_window(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """First login during 5-8:30 window: save early_bird log, exit."""
        mock_sys_exit.side_effect = SystemExit(0)
        with (
            patch.object(Path, "resolve", return_value=tmp_path),
            patch.object(ScreenLocker, "has_logged_today", return_value=False),
            patch.object(ScreenLocker, "_is_sick_day_log", return_value=False),
            patch.object(ScreenLocker, "_is_early_bird_log", return_value=False),
            patch.object(ScreenLocker, "_is_early_bird_time", return_value=True),
            patch.object(
                ScreenLocker,
                "_try_auto_upgrade_early_bird",
                return_value=False,
            ),
            patch.object(ScreenLocker, "_save_early_bird_log") as mock_save,
            patch.object(ScreenLocker, "_start_phone_check"),
            patch.object(ScreenLocker, "_start_verify_workout_check"),
            patch(
                "screen_locker.screen_lock.has_workout_skip_today",
                return_value=False,
            ),
            pytest.raises(SystemExit),
        ):
            ScreenLocker(demo_mode=True)

        mock_save.assert_called_once()
        mock_sys_exit.assert_called_with(0)

    def test_init_exits_when_early_bird_log_still_in_window(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Early bird log exists and window still active: skip lock, exit."""
        mock_sys_exit.side_effect = SystemExit(0)

        with pytest.raises(SystemExit):
            create_locker_early_bird(mock_tk, tmp_path, state="log_active")

        mock_sys_exit.assert_called_with(0)

    def test_init_exits_when_early_bird_log_upgrades_successfully(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Early bird log + past 8:30 + workout done: upgrade, exit."""
        mock_sys_exit.side_effect = SystemExit(0)
        with (
            patch.object(Path, "resolve", return_value=tmp_path),
            patch.object(ScreenLocker, "has_logged_today", return_value=False),
            patch.object(ScreenLocker, "_is_sick_day_log", return_value=False),
            patch.object(ScreenLocker, "_is_early_bird_log", return_value=True),
            patch.object(ScreenLocker, "_is_early_bird_time", return_value=False),
            patch.object(
                ScreenLocker, "_try_auto_upgrade_early_bird", return_value=True
            ),
            patch.object(ScreenLocker, "_start_phone_check"),
            patch.object(ScreenLocker, "_start_verify_workout_check"),
            pytest.raises(SystemExit),
        ):
            ScreenLocker(demo_mode=True)

        mock_sys_exit.assert_called_with(0)

    def test_init_shows_lock_when_early_bird_log_no_workout(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Early bird log + past 8:30 + no workout: show lock, no early exit."""
        locker = create_locker_early_bird(mock_tk, tmp_path, state="log_expired")

        # _try_auto_upgrade_early_bird returns False (default in create_locker)
        # so __init__ falls through to show the lock without calling sys.exit
        mock_sys_exit.assert_not_called()
        assert locker.demo_mode is True
