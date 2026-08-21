"""Tests for RunnerUpVerificationMixin in _runnerup_verification.py."""

from __future__ import annotations

import sqlite3
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


class TestQueryTodaysRun:
    """Tests for _query_todays_run (lines 328-355)."""

    def _make_db(self, tmp_path: Path) -> str:
        """Create a minimal RunnerUp DB with one activity for today."""
        import time

        db_path = str(tmp_path / "runnerup.db")
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "CREATE TABLE activity "
                "(start_time REAL, distance REAL, time REAL, type INTEGER, deleted INTEGER)"
            )
            # Insert a valid activity for today (sport=0, Running).
            now_ms = time.time()
            conn.execute(
                "INSERT INTO activity VALUES (?, ?, ?, ?, ?)",
                (now_ms, 6000.0, 2400.0, 0, 0),
            )
        return db_path

    def test_returns_none_for_no_activity_today(self, tmp_path: Path) -> None:
        """Empty DB → None."""
        db_path = str(tmp_path / "empty.db")
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "CREATE TABLE activity "
                "(start_time REAL, distance REAL, time REAL, type INTEGER, deleted INTEGER)"
            )
        # Need a locker instance to call the method.
        import tkinter as tk
        from unittest.mock import MagicMock

        mock_tk = MagicMock()
        mock_tk.Tk.return_value = MagicMock()
        mock_tk.Tk.return_value.winfo_screenwidth.return_value = 1920
        mock_tk.Tk.return_value.winfo_screenheight.return_value = 1080
        mock_tk.TclError = tk.TclError

        with (
            patch("screen_locker.screen_lock.tk", mock_tk),
            patch(
                "screen_locker.screen_lock.GateRoot",
                return_value=mock_tk.Tk.return_value,
            ),
            patch("screen_locker.screen_lock.sys.exit"),
        ):
            locker = create_locker(mock_tk, tmp_path)

        result = locker._query_todays_run(db_path)
        assert result is None

    def test_returns_activity_dict_for_todays_run(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """DB with a today activity → dict with expected keys."""
        locker = create_locker(mock_tk, tmp_path)
        db_path = self._make_db(tmp_path)
        result = locker._query_todays_run(db_path)
        assert result is not None
        assert "sport" in result
        assert result["sport"] == 0
        assert result["distance_m"] == 6000.0

    def test_returns_none_on_sqlite_error(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Corrupt DB → sqlite3.Error caught; returns None."""
        locker = create_locker(mock_tk, tmp_path)
        corrupt_db = str(tmp_path / "corrupt.db")
        with open(corrupt_db, "w") as f:
            f.write("this is not a sqlite database")
        result = locker._query_todays_run(corrupt_db)
        assert result is None


# ---------------------------------------------------------------------------
# _verify_runnerup_via_db
# ---------------------------------------------------------------------------
