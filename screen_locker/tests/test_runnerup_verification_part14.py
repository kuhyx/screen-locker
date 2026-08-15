"""Tests for RunnerUpVerificationMixin in _runnerup_verification.py."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

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


class TestVerifyRunnerupViaFiles:
    """Tests for _verify_runnerup_via_files (lines 147-165)."""

    def test_returns_none_when_no_exports_found(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """No exports for today → None (caller tries DB path)."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_find_runnerup_exports_for_date",
            MagicMock(return_value=[]),
        )
        assert locker._verify_runnerup_via_files() is None

    def test_returns_verified_when_file_passes(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """First valid file → verified immediately."""
        locker = create_locker(mock_tk, tmp_path)
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
        status, _ = locker._verify_runnerup_via_files()
        assert status == "verified"

    def test_returns_best_when_no_file_verified(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Files found but none verified → returns first non-None validation result.

        Both duration and distance are held under their minimums so the OR
        in _validate_runnerup_data cannot rescue this fixture on either
        branch — otherwise a fixture qualifying on one branch alone would
        turn this into a test of that branch, not of the "no file verified"
        return-first-result behavior this test is actually about.
        """
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_find_runnerup_exports_for_date",
            MagicMock(return_value=["/sdcard/run.tcx"]),
        )
        object.__setattr__(
            locker,
            "_pull_and_parse_tcx",
            MagicMock(
                return_value={"sport": 0, "duration_seconds": 60, "distance_m": 1000}
            ),
        )
        result = locker._verify_runnerup_via_files()
        assert result is not None
        status, _ = result
        assert status == "too_short"

    def test_returns_fallback_when_all_files_unreadable(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """_pull_and_parse_tcx returns None for every file → fallback not_verified."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_find_runnerup_exports_for_date",
            MagicMock(return_value=["/sdcard/run.tcx"]),
        )
        object.__setattr__(locker, "_pull_and_parse_tcx", MagicMock(return_value=None))
        status, _ = locker._verify_runnerup_via_files()
        assert status == "not_verified"


# ---------------------------------------------------------------------------
# _scan_and_fill_week_runnerup
# ---------------------------------------------------------------------------
