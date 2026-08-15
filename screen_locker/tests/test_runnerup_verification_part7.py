"""Tests for RunnerUpVerificationMixin in _runnerup_verification.py."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path

# Minimal valid TCX XML for a 40-minute, 6-km run.
_TCX_RUNNING = """\
<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase
    xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
  <Activities>
    <Activity Sport="Running">
      <Lap>
        <TotalTimeSeconds>2400.0</TotalTimeSeconds>
        <DistanceMeters>6000.0</DistanceMeters>
      </Lap>
    </Activity>
  </Activities>
</TrainingCenterDatabase>
"""

# TCX with an unrecognised sport tag (not in RUNNERUP_ACCEPTED_SPORTS).
_TCX_GYM = """\
<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase
    xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
  <Activities>
    <Activity Sport="Gym">
      <Lap>
        <TotalTimeSeconds>3600.0</TotalTimeSeconds>
        <DistanceMeters>0.0</DistanceMeters>
      </Lap>
    </Activity>
  </Activities>
</TrainingCenterDatabase>
"""

# Two laps that together make a valid run.
_TCX_MULTI_LAP = """\
<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase
    xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
  <Activities>
    <Activity Sport="Running">
      <Lap>
        <TotalTimeSeconds>1200.0</TotalTimeSeconds>
        <DistanceMeters>3000.0</DistanceMeters>
      </Lap>
      <Lap>
        <TotalTimeSeconds>1200.0</TotalTimeSeconds>
        <DistanceMeters>3000.0</DistanceMeters>
      </Lap>
    </Activity>
  </Activities>
</TrainingCenterDatabase>
"""


class TestScanAndFillWeekRunnerup:
    """Tests for _scan_and_fill_week_runnerup (lines 186-248)."""

    def test_returns_zero_when_no_phone(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """No ADB device → 0 filled."""
        locker = create_locker(mock_tk, tmp_path)
        log_file = tmp_path / "log.json"
        log_file.write_text("{}")
        object.__setattr__(locker, "_has_adb_device", MagicMock(return_value=False))
        assert locker._scan_and_fill_week_runnerup(log_file) == 0

    def test_returns_zero_when_all_days_already_logged(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """All days this week already have counted workouts → 0 new fills."""
        from datetime import date, timedelta

        locker = create_locker(mock_tk, tmp_path)
        log_file = tmp_path / "log.json"

        # Fill Mon-today with phone_verified entries.
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        logs: dict[str, Any] = {}
        cur = monday
        while cur <= today:
            logs[cur.strftime("%Y-%m-%d")] = {
                "workout_data": {"type": "phone_verified"}
            }
            cur += timedelta(days=1)
        log_file.write_text(json.dumps(logs))

        object.__setattr__(locker, "_has_adb_device", MagicMock(return_value=True))
        object.__setattr__(
            locker, "_find_runnerup_exports_for_date", MagicMock(return_value=[])
        )
        assert locker._scan_and_fill_week_runnerup(log_file) == 0

    def test_fills_gap_for_unlogged_day(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Gap in log + exports found + validated → entry written, count > 0."""
        locker = create_locker(mock_tk, tmp_path)
        log_file = tmp_path / "log.json"
        log_file.write_text("{}")

        object.__setattr__(locker, "_has_adb_device", MagicMock(return_value=True))
        object.__setattr__(
            locker,
            "_find_runnerup_exports_for_date",
            MagicMock(return_value=["/sdcard/run.tcx"]),
        )
        object.__setattr__(
            locker,
            "_pull_and_parse_tcx",
            MagicMock(
                return_value={"sport": 0, "duration_seconds": 2400, "distance_m": 6000}
            ),
        )
        object.__setattr__(
            locker,
            "_validate_runnerup_data",
            MagicMock(return_value=("verified", "Running: 6.0 km in 40 min")),
        )

        with patch(
            "screen_locker._log_mixin.compute_entry_hmac",
            return_value="sig",
        ):
            result = locker._scan_and_fill_week_runnerup(log_file)

        assert result > 0
        logs = json.loads(log_file.read_text())
        # At least one date should have been filled; each day holds a list.
        types = [
            entry.get("workout_data", {}).get("type")
            for entries in logs.values()
            for entry in entries
        ]
        assert "runnerup_verified" in types
