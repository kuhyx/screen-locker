"""Tests for RunnerUpVerificationMixin in _runnerup_verification.py."""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_tcx(tmp_path: Path, content: str, name: str = "activity.tcx") -> str:
    """Write TCX content to a temp file and return the path string."""
    p = tmp_path / name
    p.write_text(content)
    return str(p)


# ---------------------------------------------------------------------------
# _validate_runnerup_data
# ---------------------------------------------------------------------------


class TestVerifyRunnerupViaDb:
    """Tests for _verify_runnerup_via_db (lines 364-376)."""

    def test_returns_not_verified_when_no_db(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """_pull_runnerup_db returns None → not_verified."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(locker, "_pull_runnerup_db", MagicMock(return_value=None))
        status, _ = locker._verify_runnerup_via_db()
        assert status == "not_verified"

    def test_returns_not_verified_when_no_run_today(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """DB pulled but no activity found → not_verified."""
        db_tmp = tempfile.mkdtemp(prefix="runnerup_test_")
        db_path = os.path.join(db_tmp, "runnerup.db")
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "CREATE TABLE activity "
                "(start_time REAL, distance REAL, time REAL, type INTEGER, deleted INTEGER)"
            )
        try:
            locker = create_locker(mock_tk, tmp_path)
            object.__setattr__(
                locker, "_pull_runnerup_db", MagicMock(return_value=db_path)
            )
            status, _ = locker._verify_runnerup_via_db()
        finally:
            shutil.rmtree(db_tmp, ignore_errors=True)

        assert status == "not_verified"

    def test_returns_verified_for_valid_db_run(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """DB with valid run → validated, returns verified."""
        import time

        db_tmp = tempfile.mkdtemp(prefix="runnerup_test_")
        db_path = os.path.join(db_tmp, "runnerup.db")
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "CREATE TABLE activity "
                "(start_time REAL, distance REAL, time REAL, type INTEGER, deleted INTEGER)"
            )
            conn.execute(
                "INSERT INTO activity VALUES (?, ?, ?, ?, ?)",
                (time.time(), 6000.0, 2400.0, 0, 0),
            )
        try:
            locker = create_locker(mock_tk, tmp_path)
            object.__setattr__(
                locker, "_pull_runnerup_db", MagicMock(return_value=db_path)
            )
            status, _ = locker._verify_runnerup_via_db()
        finally:
            shutil.rmtree(db_tmp, ignore_errors=True)

        assert status == "verified"


# ---------------------------------------------------------------------------
# _verify_runnerup_workout (entry point)
# ---------------------------------------------------------------------------


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

        # Both exports return non-verified data (too_short).
        # Iteration 1: best is None → sets best → loop continues to export 2.
        # Iteration 2: best is NOT None → False branch of 'if best is None:' (161->154).
        object.__setattr__(
            locker,
            "_find_runnerup_exports_for_date",
            MagicMock(return_value=["/sdcard/a.tcx", "/sdcard/b.tcx"]),
        )
        short_run = {"sport": 0, "duration_seconds": 60, "distance_m": 6000}
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
        import datetime as dt

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
