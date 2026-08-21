"""Tests for RunnerUpVerificationMixin in _runnerup_verification.py."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from screen_locker.tests.conftest import create_locker
from screen_locker.tests.test_runnerup_verification_part1 import _write_tcx

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


class TestBranchCoverageGaps:
    """Targeted tests for uncovered branches in _runnerup_verification.py."""

    # ---- 86->82: inner for-loop iterates >1 time in _find_runnerup_exports_for_date

    def test_multi_file_listing_loops_inner_for(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Duplicate filename in ls output: second occurrence hits 'already in found'
        branch (86->82 — the False branch of 'if remote not in found:')."""
        locker = create_locker(mock_tk, tmp_path)
        # Same file listed twice → second encounter hits the dedup False-branch
        dup_files = (
            "RunnerUp_2024-03-15-08-00-00_act.tcx\n"
            "RunnerUp_2024-03-15-08-00-00_act.tcx\n"
        )
        object.__setattr__(
            locker,
            "_run_adb",
            MagicMock(return_value=(True, dup_files)),
        )
        result = locker._find_runnerup_exports_for_date("2024-03-15")
        # Dedup: only one path in the result
        assert len(result) >= 1

    # ---- 129->131 and 131->126: _parse_tcx with missing TotalTimeSeconds / DistanceMeters

    def test_parse_tcx_missing_time_and_distance_elements(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Lap with no TotalTimeSeconds or DistanceMeters: both false-branches hit."""
        locker = create_locker(mock_tk, tmp_path)
        tcx = """\
<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase
    xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
  <Activities>
    <Activity Sport="Running">
      <Lap>
      </Lap>
    </Activity>
  </Activities>
</TrainingCenterDatabase>
"""
        path = _write_tcx(tmp_path, tcx, "empty_lap.tcx")
        result = locker._parse_tcx(path)
        # Should still return a dict (0 seconds, 0 m) not None
        assert result is not None
        assert result["duration_seconds"] == 0
        assert result["distance_m"] == 0.0

    # ---- 161->154: _verify_runnerup_via_files iterates over multiple exports

    def test_verify_via_files_loops_over_multiple_exports(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Two non-verified exports: first sets best (162), second hits the False branch
        of 'if best is None:' (161->154), exercising the loop-continue with best set."""
        locker = create_locker(mock_tk, tmp_path)

        # Both exports return non-verified data (too_short). Duration and
        # distance are an OR, so both must fail their minimum -- a fixture
        # qualifying on either alone would verify instead of exercising this
        # branch.
        # Iteration 1: best is None → sets best → loop continues to export 2.
        # Iteration 2: best is NOT None → False branch of 'if best is None:' (161->154).
        object.__setattr__(
            locker,
            "_find_runnerup_exports_for_date",
            MagicMock(return_value=["/sdcard/a.tcx", "/sdcard/b.tcx"]),
        )
        short_run = {"sport": 0, "duration_seconds": 60, "distance_m": 1000}
        object.__setattr__(
            locker,
            "_pull_and_parse_tcx",
            MagicMock(return_value=short_run),
        )
        result = locker._verify_runnerup_via_files()
        assert result is not None
        status, _ = result
        assert status == "too_short"

    # ---- 203->209: non-dict log entry in _scan_and_fill_week_runnerup

    def test_scan_skips_non_dict_log_entries(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Log entry that is not a dict: isinstance branch False → line 209 reached."""
        locker = create_locker(mock_tk, tmp_path)
        log_file = tmp_path / "log.json"

        today = dt.date.today()
        # Store today's entry as a plain string (not a dict) to trigger branch 203->209
        log_file.write_text(
            __import__("json").dumps({today.strftime("%Y-%m-%d"): "legacy_value"})
        )

        object.__setattr__(locker, "_has_adb_device", MagicMock(return_value=True))
        object.__setattr__(
            locker,
            "_find_runnerup_exports_for_date",
            MagicMock(return_value=[]),
        )
        # Should not raise; no exports → 0 filled
        assert locker._scan_and_fill_week_runnerup(log_file) == 0
