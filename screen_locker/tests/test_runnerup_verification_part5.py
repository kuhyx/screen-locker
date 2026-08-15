"""Tests for RunnerUpVerificationMixin in _runnerup_verification.py."""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import time
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
