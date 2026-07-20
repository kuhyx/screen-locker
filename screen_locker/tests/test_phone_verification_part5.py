"""Tests for _try_fill_stronglifts_for_week (StrongLifts week-scan backfill)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


# These two tests need a day that is BOTH in the past and inside the current
# ISO week. On a Monday no such day exists (week_start == today), so using
# date.today() made them fail every Monday and pass Tue-Sun. Pin "now" to a
# Wednesday instead: yesterday is then Tuesday, comfortably inside the week.
_FROZEN_NOW = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)  # a Wednesday
_FROZEN_YESTERDAY = (_FROZEN_NOW.date() - timedelta(days=1)).isoformat()


class _FakeDatetime(datetime):
    """datetime whose now() is pinned to _FROZEN_NOW."""

    @classmethod
    def now(cls, tz=None):
        return _FROZEN_NOW.astimezone(tz) if tz else _FROZEN_NOW


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
        yesterday = _FROZEN_YESTERDAY
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
        yesterday = _FROZEN_YESTERDAY
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

        with (
            patch("screen_locker._log_mixin.compute_entry_hmac", return_value="sig"),
            patch("screen_locker._phone_verification.datetime", _FakeDatetime),
        ):
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
        yesterday = _FROZEN_YESTERDAY
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

        with (
            patch("screen_locker._log_mixin.compute_entry_hmac", return_value="sig"),
            patch("screen_locker._phone_verification.datetime", _FakeDatetime),
        ):
            first = locker._try_fill_stronglifts_for_week(log_file)
            second = locker._try_fill_stronglifts_for_week(log_file)

        assert (first, second) == (1, 0)

    def test_in_week_but_unverified_json_is_not_written(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """A this-week JSON that fails validation is rejected, not backfilled.

        The date gate and the content gate are separate: being in the current
        week only earns the JSON a validation attempt, never a log entry.
        """
        locker = create_locker(mock_tk, tmp_path)
        log_file = tmp_path / "log.json"
        log_file.write_text("{}")
        object.__setattr__(locker, "_has_adb_device", MagicMock(return_value=True))
        object.__setattr__(
            locker,
            "_pull_workout_app_json",
            MagicMock(return_value={"date": _FROZEN_YESTERDAY, "exercises": []}),
        )
        object.__setattr__(
            locker,
            "_validate_json_content",
            MagicMock(return_value=("rejected", "no exercises")),
        )

        with patch("screen_locker._phone_verification.datetime", _FakeDatetime):
            assert locker._try_fill_stronglifts_for_week(log_file) == 0
        assert json.loads(log_file.read_text()) == {}
