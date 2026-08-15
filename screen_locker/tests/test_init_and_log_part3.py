"""Tests for screen_locker initialization, logging, and basic operations."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestSaveWorkoutLog:
    """Tests for save_workout_log method."""

    def test_save_to_new_file(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test saving to a new log file includes HMAC."""
        log_file = tmp_path / "workout_log.json"
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        locker.workout_data = {"type": "running"}
        with patch(
            "screen_locker._log_mixin.compute_entry_hmac",
            return_value="abc123",
        ):
            locker.save_workout_log()

        assert log_file.exists()
        with log_file.open() as f:
            data: dict[str, Any] = json.load(f)
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        assert today in data
        # The log now holds a list of entries per day (multiple workouts/day).
        assert data[today][0]["workout_data"]["type"] == "running"
        assert data[today][0]["hmac"] == "abc123"

    def test_save_to_new_file_no_hmac_key(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test saving without HMAC key produces unsigned entry."""
        log_file = tmp_path / "workout_log.json"
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        locker.workout_data = {"type": "running"}
        with patch(
            "screen_locker._log_mixin.compute_entry_hmac",
            return_value=None,
        ):
            locker.save_workout_log()

        with log_file.open() as f:
            data: dict[str, Any] = json.load(f)
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        assert "hmac" not in data[today][0]

    def test_save_to_existing_file(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test saving appends to existing log file."""
        log_file = tmp_path / "workout_log.json"
        log_file.write_text(json.dumps({"2020-01-01": {"old": "data"}}))

        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        locker.workout_data = {"type": "strength"}
        with patch(
            "screen_locker._log_mixin.compute_entry_hmac",
            return_value="sig",
        ):
            locker.save_workout_log()

        with log_file.open() as f:
            data: dict[str, Any] = json.load(f)
        assert "2020-01-01" in data
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        assert today in data

    def test_save_with_corrupted_existing_file(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test saving when existing file is corrupted."""
        log_file = tmp_path / "workout_log.json"
        log_file.write_text("not valid json")

        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        locker.workout_data = {"type": "running"}
        with patch(
            "screen_locker._log_mixin.compute_entry_hmac",
            return_value="sig",
        ):
            locker.save_workout_log()

        with log_file.open() as f:
            data: dict[str, Any] = json.load(f)
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        assert today in data

    def test_save_with_write_error(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test saving handles write errors gracefully."""
        log_file = tmp_path / "nonexistent_dir" / "workout_log.json"

        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        locker.workout_data = {"type": "running"}
        with patch(
            "screen_locker._log_mixin.compute_entry_hmac",
            return_value="sig",
        ):
            # Should not raise, just log warning
            locker.save_workout_log()
