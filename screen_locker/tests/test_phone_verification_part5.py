"""Tests for _try_fill_stronglifts_for_week (StrongLifts week-scan backfill)."""

from __future__ import annotations

from datetime import date, timedelta
import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestTryFillStronglifitsForWeek:
    """Tests for _try_fill_stronglifts_for_week (week-scan backfill)."""

    def test_returns_zero_when_no_phone(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        log_file = tmp_path / "log.json"
        log_file.write_text("{}")
        object.__setattr__(locker, "_has_adb_device", MagicMock(return_value=False))
        assert locker._try_fill_stronglifts_for_week(log_file) == 0

    def test_returns_zero_when_no_json_pulled(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        log_file = tmp_path / "log.json"
        log_file.write_text("{}")
        object.__setattr__(locker, "_has_adb_device", MagicMock(return_value=True))
        object.__setattr__(
            locker, "_pull_workout_app_json", MagicMock(return_value=None)
        )
        assert locker._try_fill_stronglifts_for_week(log_file) == 0

    def test_returns_zero_when_date_unparsable(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        log_file = tmp_path / "log.json"
        log_file.write_text("{}")
        object.__setattr__(locker, "_has_adb_device", MagicMock(return_value=True))
        object.__setattr__(
            locker,
            "_pull_workout_app_json",
            MagicMock(return_value={"date": "not-a-date", "exercises": ["x"]}),
        )
        assert locker._try_fill_stronglifts_for_week(log_file) == 0

    def test_returns_zero_when_date_outside_current_week(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """A stale JSON from before this ISO week is not backfilled."""
        locker = create_locker(mock_tk, tmp_path)
        log_file = tmp_path / "log.json"
        log_file.write_text("{}")
        last_week = (date.today() - timedelta(days=8)).isoformat()
        object.__setattr__(locker, "_has_adb_device", MagicMock(return_value=True))
        object.__setattr__(
            locker,
            "_pull_workout_app_json",
            MagicMock(
                return_value={
                    "date": last_week,
                    "exercises": ["x"],
                    "duration_seconds": 6000,
                    "succeeded": True,
                }
            ),
        )
        assert locker._try_fill_stronglifts_for_week(log_file) == 0

    def test_returns_zero_when_content_invalid(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """A this-week date with no exercises still fails content validation."""
        locker = create_locker(mock_tk, tmp_path)
        log_file = tmp_path / "log.json"
        log_file.write_text("{}")
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        object.__setattr__(locker, "_has_adb_device", MagicMock(return_value=True))
        object.__setattr__(
            locker,
            "_pull_workout_app_json",
            MagicMock(return_value={"date": yesterday, "exercises": []}),
        )
        assert locker._try_fill_stronglifts_for_week(log_file) == 0

    def test_fills_gap_for_past_week_day(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """A valid, this-week, not-yet-logged JSON gets appended and returns 1."""
        locker = create_locker(mock_tk, tmp_path)
        log_file = tmp_path / "log.json"
        log_file.write_text("{}")
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        object.__setattr__(locker, "_has_adb_device", MagicMock(return_value=True))
        object.__setattr__(
            locker,
            "_pull_workout_app_json",
            MagicMock(
                return_value={
                    "date": yesterday,
                    "exercises": ["x"],
                    "duration_seconds": 6000,
                    "succeeded": True,
                }
            ),
        )

        with patch("screen_locker._log_mixin.compute_entry_hmac", return_value="sig"):
            result = locker._try_fill_stronglifts_for_week(log_file)

        assert result == 1
        logs = json.loads(log_file.read_text())
        entry = logs[yesterday][0]
        assert entry["workout_data"]["type"] == "phone_verified"
        assert entry["workout_id"] == f"phone_verified:{yesterday}"

    def test_rescanning_an_already_filled_day_is_a_no_op(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        log_file = tmp_path / "log.json"
        log_file.write_text("{}")
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        data = {
            "date": yesterday,
            "exercises": ["x"],
            "duration_seconds": 6000,
            "succeeded": True,
        }
        object.__setattr__(locker, "_has_adb_device", MagicMock(return_value=True))
        object.__setattr__(
            locker, "_pull_workout_app_json", MagicMock(return_value=data)
        )

        with patch("screen_locker._log_mixin.compute_entry_hmac", return_value="sig"):
            first = locker._try_fill_stronglifts_for_week(log_file)
            second = locker._try_fill_stronglifts_for_week(log_file)

        assert (first, second) == (1, 0)
