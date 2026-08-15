"""More RunnerUp week-scan backfill edge cases.

Split out of test_runnerup_verification_part10.py for the 250-line cap.
"""

from __future__ import annotations

import json
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


class TestScanAndFillWeekRunnerupSkips:
    """Days the scan declines to fill, and failures it survives."""

    def test_handles_corrupt_log_file(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Corrupt log JSON → starts with empty dict, still works."""
        locker = create_locker(mock_tk, tmp_path)
        log_file = tmp_path / "log.json"
        log_file.write_text("not-json")
        object.__setattr__(locker, "_has_adb_device", MagicMock(return_value=True))
        object.__setattr__(
            locker,
            "_find_runnerup_exports_for_date",
            MagicMock(return_value=[]),
        )
        # Should not raise; returns 0 (no exports found).
        assert locker._scan_and_fill_week_runnerup(log_file) == 0

    def test_hmac_none_still_fills_entry(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """HMAC key absent (compute_entry_hmac returns None) → entry still written."""
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
            return_value=None,
        ):
            result = locker._scan_and_fill_week_runnerup(log_file)

        assert result > 0
        # No "hmac" key when signature is None; each day holds a list of entries.
        logs = json.loads(log_file.read_text())
        for entries in logs.values():
            for entry in entries:
                assert "hmac" not in entry


# ---------------------------------------------------------------------------
# _find_runnerup_package
# ---------------------------------------------------------------------------
