"""Tests for RunnerUpVerificationMixin in _runnerup_verification.py."""

from __future__ import annotations

import os
import shutil
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


class TestFindRunnerupPackage:
    """Tests for _find_runnerup_package (lines 256-260)."""

    def test_returns_none_when_no_package_found(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """No package installed → None."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(locker, "_adb_shell", MagicMock(return_value=(True, "")))
        assert locker._find_runnerup_package() is None

    def test_returns_first_installed_package(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """First package found → returned."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_adb_shell",
            MagicMock(return_value=(True, "package:org.runnerup")),
        )
        result = locker._find_runnerup_package()
        assert result == "org.runnerup"


# ---------------------------------------------------------------------------
# _cleanup_runnerup_sdcard
# ---------------------------------------------------------------------------


class TestCleanupRunnerupSdcard:
    """Tests for _cleanup_runnerup_sdcard (lines 315-316)."""

    def test_calls_adb_shell_for_each_suffix(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Cleanup invokes _adb_shell for '', '-wal', '-shm'."""
        locker = create_locker(mock_tk, tmp_path)
        mock_shell = MagicMock(return_value=(True, ""))
        object.__setattr__(locker, "_adb_shell", mock_shell)
        locker._cleanup_runnerup_sdcard()
        assert mock_shell.call_count == 3


# ---------------------------------------------------------------------------
# _pull_runnerup_db
# ---------------------------------------------------------------------------


class TestPullRunnerupDb:
    """Tests for _pull_runnerup_db (lines 272-311)."""

    def test_returns_none_when_package_not_found(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """No RunnerUp package installed → None."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker, "_find_runnerup_package", MagicMock(return_value=None)
        )
        assert locker._pull_runnerup_db() is None

    def test_returns_none_when_cp_fails(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Root cp fails → None (cleanup still called)."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_find_runnerup_package",
            MagicMock(return_value="org.runnerup"),
        )
        object.__setattr__(
            locker, "_adb_shell", MagicMock(return_value=(False, "permission denied"))
        )
        assert locker._pull_runnerup_db() is None

    def test_returns_none_when_pull_fails(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """cp succeeds but adb pull fails → None, cleanup called."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_find_runnerup_package",
            MagicMock(return_value="org.runnerup"),
        )
        object.__setattr__(locker, "_adb_shell", MagicMock(return_value=(True, "")))
        object.__setattr__(locker, "_run_adb", MagicMock(return_value=(False, "")))
        mock_cleanup = MagicMock()
        object.__setattr__(locker, "_cleanup_runnerup_sdcard", mock_cleanup)
        assert locker._pull_runnerup_db() is None
        mock_cleanup.assert_called()

    def test_returns_local_path_on_success(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Successful cp + pull + sidecar pulls → returns local db path string."""
        locker = create_locker(mock_tk, tmp_path)

        # Create a placeholder db so _pull returns a real path.
        def _fake_run_adb(args: list[str]) -> tuple[bool, str]:
            if args[0] == "pull" and args[2].endswith(".db"):
                # Create the local file so the caller finds it.
                open(args[2], "w").close()
            return True, ""

        object.__setattr__(
            locker,
            "_find_runnerup_package",
            MagicMock(return_value="org.runnerup"),
        )
        object.__setattr__(locker, "_adb_shell", MagicMock(return_value=(True, "")))
        object.__setattr__(locker, "_run_adb", MagicMock(side_effect=_fake_run_adb))
        object.__setattr__(locker, "_cleanup_runnerup_sdcard", MagicMock())

        result = locker._pull_runnerup_db()
        assert result is not None
        assert result.endswith(".db")
        # Cleanup temp dir.
        if result and os.path.exists(result):
            shutil.rmtree(os.path.dirname(result), ignore_errors=True)


# ---------------------------------------------------------------------------
# _query_todays_run
# ---------------------------------------------------------------------------


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
