"""Tests for RunnerUpVerificationMixin in _runnerup_verification.py."""

from __future__ import annotations

from typing import TYPE_CHECKING
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

# TCX with a non-running sport tag (Gym).
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


class TestVerifyRunnerupWorkout:
    """Tests for _verify_runnerup_workout (lines 440-447 and 431)."""

    def test_returns_clock_tampered_on_skew(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Clock skew detected → clock_tampered without further checks."""
        locker = create_locker(mock_tk, tmp_path)
        with patch(
            "screen_locker._runnerup_verification.check_clock_skew",
            return_value=(False, "Clock is off"),
        ):
            status, msg = locker._verify_runnerup_workout()
        assert status == "clock_tampered"
        assert "Clock" in msg

    def test_returns_no_phone_when_device_absent(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """No ADB device → no_phone."""
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch(
                "screen_locker._runnerup_verification.check_clock_skew",
                return_value=(True, "ok"),
            ),
            patch.object(locker, "_has_adb_device", return_value=False),
        ):
            status, _ = locker._verify_runnerup_workout()
        assert status == "no_phone"

    def test_returns_file_result_when_exports_exist(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """File-based verification succeeds → result returned (line 431 logged)."""
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch(
                "screen_locker._runnerup_verification.check_clock_skew",
                return_value=(True, "ok"),
            ),
            patch.object(locker, "_has_adb_device", return_value=True),
            patch.object(
                locker,
                "_verify_runnerup_via_files",
                return_value=("verified", "Running: 6 km in 40 min"),
            ),
        ):
            status, _msg = locker._verify_runnerup_workout()
        assert status == "verified"

    def test_falls_back_to_db_when_no_files(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """No file exports → DB path tried."""
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch(
                "screen_locker._runnerup_verification.check_clock_skew",
                return_value=(True, "ok"),
            ),
            patch.object(locker, "_has_adb_device", return_value=True),
            patch.object(locker, "_verify_runnerup_via_files", return_value=None),
            patch.object(
                locker,
                "_verify_runnerup_via_db",
                return_value=("not_verified", "no run today"),
            ) as mock_db,
        ):
            status, _ = locker._verify_runnerup_workout()
        assert status == "not_verified"
        mock_db.assert_called_once()


# ---------------------------------------------------------------------------
# Branch-coverage gap fixes
# ---------------------------------------------------------------------------
