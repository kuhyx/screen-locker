"""Tests for early bird carrot feature in screen locker."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

from screen_locker.tests.conftest import (
    create_locker,
)

if TYPE_CHECKING:
    from pathlib import Path

    from screen_locker.screen_lock import ScreenLocker


class TestGetLocalTimeMinutes:
    """Tests for _get_local_time_minutes helper."""

    def test_returns_int_within_day_range(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Returns an integer between 0 and 1439 (minutes in a day)."""
        locker = create_locker(mock_tk, tmp_path)
        result = locker._get_local_time_minutes()
        assert isinstance(result, int)
        assert 0 <= result < 24 * 60


class TestIsEarlyBirdTime:
    """Tests for _is_early_bird_time based on local clock."""

    def _locker(
        self,
        mock_tk: MagicMock,
        tmp_path: Path,
        minutes: int,
    ) -> ScreenLocker:
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_get_local_time_minutes",
            MagicMock(return_value=minutes),
        )
        return locker

    def test_within_window(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """6:00 AM (360 min) is within the early bird window."""
        locker = self._locker(mock_tk, tmp_path, 360)
        assert locker._is_early_bird_time() is True

    def test_at_start_of_window(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """5:00 AM (300 min) is the inclusive start of the window."""
        locker = self._locker(mock_tk, tmp_path, 300)
        assert locker._is_early_bird_time() is True

    def test_just_before_start(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """4:59 AM (299 min) is before the window."""
        locker = self._locker(mock_tk, tmp_path, 299)
        assert locker._is_early_bird_time() is False

    def test_just_before_end(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """8:29 AM (509 min) is still within the window."""
        locker = self._locker(mock_tk, tmp_path, 509)
        assert locker._is_early_bird_time() is True

    def test_at_end_of_window(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """8:30 AM (510 min) is the exclusive end — not in window."""
        locker = self._locker(mock_tk, tmp_path, 510)
        assert locker._is_early_bird_time() is False

    def test_after_window(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """9:00 AM (540 min) is past the window."""
        locker = self._locker(mock_tk, tmp_path, 540)
        assert locker._is_early_bird_time() is False

    def test_midnight(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Midnight (0 min) is outside the window."""
        locker = self._locker(mock_tk, tmp_path, 0)
        assert locker._is_early_bird_time() is False


class TestIsEarlyBirdLog:
    """Tests for _is_early_bird_log method."""

    def test_no_log_file(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Return False when log file does not exist."""
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = tmp_path / "workout_log.json"
        assert locker._is_early_bird_log() is False

    def test_invalid_json(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Return False when log file contains invalid JSON."""
        log_file = tmp_path / "workout_log.json"
        log_file.write_text("{bad json}")
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        assert locker._is_early_bird_log() is False

    def test_os_error_on_open(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Return False when opening the log file raises OSError."""
        locker = create_locker(mock_tk, tmp_path)
        mock_file = MagicMock()
        mock_file.exists.return_value = True
        mock_file.open.side_effect = OSError("permission denied")
        locker.log_file = mock_file
        assert locker._is_early_bird_log() is False

    def test_no_entry_today(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Return False when no entry exists for today."""
        log_file = tmp_path / "workout_log.json"
        log_file.write_text(json.dumps({"2020-01-01": {}}))
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        assert locker._is_early_bird_log() is False

    def test_today_is_phone_verified(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Return False when today's entry is phone_verified."""
        log_file = tmp_path / "workout_log.json"
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        log_file.write_text(
            json.dumps({today: {"workout_data": {"type": "phone_verified"}}})
        )
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        assert locker._is_early_bird_log() is False

    def test_today_is_early_bird(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Return True when today's entry type is early_bird."""
        log_file = tmp_path / "workout_log.json"
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        log_file.write_text(
            json.dumps({today: {"workout_data": {"type": "early_bird"}}})
        )
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        assert locker._is_early_bird_log() is True


class TestSaveEarlyBirdLog:
    """Tests for _save_early_bird_log method."""

    def test_saves_early_bird_entry(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Saves an entry with type early_bird to the log file."""
        log_file = tmp_path / "workout_log.json"
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        with patch(
            "screen_locker.screen_lock.compute_entry_hmac",
            return_value=None,
        ):
            locker._save_early_bird_log()

        assert log_file.exists()
        with log_file.open() as f:
            data: dict[str, Any] = json.load(f)
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        assert data[today]["workout_data"]["type"] == "early_bird"
