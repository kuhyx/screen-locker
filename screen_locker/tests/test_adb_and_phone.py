"""Tests for ADB commands, phone connection, and database operations."""

from __future__ import annotations

import sqlite3
import subprocess
import time
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from python_pkg.screen_locker.screen_lock import STRONGLIFTS_DB_REMOTE
from python_pkg.screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestRunAdb:
    """Tests for _run_adb ADB command execution."""

    def test_run_adb_success(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test successful ADB command."""
        locker = create_locker(mock_tk, tmp_path)
        mock_result = MagicMock(returncode=0, stdout="ok\n")
        with patch(
            "python_pkg.screen_locker._phone_verification.subprocess.run",
            return_value=mock_result,
        ) as mock_run:
            success, output = locker._run_adb(["devices"])

        assert success is True
        assert output == "ok\n"
        mock_run.assert_called_once()

    def test_run_adb_failure(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test failed ADB command."""
        locker = create_locker(mock_tk, tmp_path)
        mock_result = MagicMock(returncode=1, stdout="")
        with patch(
            "python_pkg.screen_locker._phone_verification.subprocess.run",
            return_value=mock_result,
        ):
            success, _output = locker._run_adb(["devices"])

        assert success is False

    def test_run_adb_not_found(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test ADB binary not found."""
        locker = create_locker(mock_tk, tmp_path)
        with patch(
            "python_pkg.screen_locker._phone_verification.subprocess.run",
            side_effect=FileNotFoundError("adb not found"),
        ):
            success, output = locker._run_adb(["devices"])

        assert success is False
        assert output == ""

    def test_run_adb_oserror(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test ADB OSError."""
        locker = create_locker(mock_tk, tmp_path)
        with patch(
            "python_pkg.screen_locker._phone_verification.subprocess.run",
            side_effect=OSError("permission denied"),
        ):
            success, output = locker._run_adb(["devices"])

        assert success is False
        assert output == ""

    def test_run_adb_timeout(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test ADB command timeout."""
        locker = create_locker(mock_tk, tmp_path)
        with patch(
            "python_pkg.screen_locker._phone_verification.subprocess.run",
            side_effect=subprocess.TimeoutExpired("adb", 15),
        ):
            success, output = locker._run_adb(["devices"])

        assert success is False
        assert output == ""


class TestAdbShell:
    """Tests for _adb_shell method."""

    def test_adb_shell_no_root(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test ADB shell without root."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_run_adb",
            MagicMock(
                return_value=(True, "output"),
            ),
        )

        success, output = locker._adb_shell("ls /sdcard")

        locker._run_adb.assert_called_once_with(["shell", "ls /sdcard"])
        assert success is True
        assert output == "output"

    def test_adb_shell_with_root(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test ADB shell with root."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_run_adb",
            MagicMock(
                return_value=(True, "output"),
            ),
        )

        success, _output = locker._adb_shell("ls /data", root=True)

        locker._run_adb.assert_called_once_with(
            ["shell", "su", "-c", "ls /data"],
        )
        assert success is True


class TestIsPhoneConnected:
    """Tests for _is_phone_connected method."""

    def test_phone_connected(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test phone detected as connected."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_run_adb",
            MagicMock(
                return_value=(
                    True,
                    "List of devices attached\nABC123\tdevice\n\n",
                ),
            ),
        )

        assert locker._is_phone_connected() is True

    def test_phone_not_connected(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test no phone connected."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_run_adb",
            MagicMock(
                return_value=(True, "List of devices attached\n\n"),
            ),
        )
        object.__setattr__(
            locker,
            "_try_wireless_reconnect",
            MagicMock(
                return_value=False,
            ),
        )

        assert locker._is_phone_connected() is False

    def test_phone_offline(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test phone connected but offline."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_run_adb",
            MagicMock(
                return_value=(
                    True,
                    "List of devices attached\nABC123\toffline\n\n",
                ),
            ),
        )
        object.__setattr__(
            locker,
            "_try_wireless_reconnect",
            MagicMock(
                return_value=False,
            ),
        )

        assert locker._is_phone_connected() is False

    def test_adb_command_fails(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test ADB command failure."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_run_adb",
            MagicMock(
                return_value=(False, ""),
            ),
        )
        object.__setattr__(
            locker,
            "_try_wireless_reconnect",
            MagicMock(
                return_value=False,
            ),
        )

        assert locker._is_phone_connected() is False


class TestFindHealthConnectDb:
    """Tests for _pull_stronglifts_db method."""

    def test_db_pulled_successfully(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test StrongLifts DB pulled from device."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_adb_shell",
            MagicMock(
                return_value=(True, ""),
            ),
        )
        object.__setattr__(
            locker,
            "_run_adb",
            MagicMock(
                return_value=(True, ""),
            ),
        )

        result = locker._pull_stronglifts_db()

        assert result is not None
        locker._adb_shell.assert_called_once()
        locker._run_adb.assert_called_once()
        call_args = locker._run_adb.call_args[0][0]
        assert call_args[0] == "pull"

    def test_db_cat_fails(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns None when cat command fails."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_adb_shell",
            MagicMock(
                return_value=(False, ""),
            ),
        )

        assert locker._pull_stronglifts_db() is None

    def test_db_pull_fails(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns None when adb pull fails."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_adb_shell",
            MagicMock(
                return_value=(True, ""),
            ),
        )
        object.__setattr__(
            locker,
            "_run_adb",
            MagicMock(
                return_value=(False, ""),
            ),
        )

        assert locker._pull_stronglifts_db() is None

    def test_db_uses_correct_remote_path(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test uses the correct StrongLifts DB remote path."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_adb_shell",
            MagicMock(
                return_value=(True, ""),
            ),
        )
        object.__setattr__(
            locker,
            "_run_adb",
            MagicMock(
                return_value=(True, ""),
            ),
        )

        locker._pull_stronglifts_db()

        shell_cmd = locker._adb_shell.call_args[0][0]
        assert STRONGLIFTS_DB_REMOTE in shell_cmd


class TestCountTodayWorkouts:
    """Tests for _count_today_workouts method."""

    def test_workouts_found_today(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test workouts found today."""
        locker = create_locker(mock_tk, tmp_path)
        db_file = tmp_path / "sl_test.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute(
            "CREATE TABLE workouts "
            "(id TEXT PRIMARY KEY, start INTEGER, finish INTEGER)",
        )
        # Insert a workout with today's timestamp (ms)
        now_ms = int(time.time() * 1000)
        conn.execute(
            "INSERT INTO workouts VALUES (?, ?, ?)",
            ("w1", now_ms, now_ms + 3600000),
        )
        conn.commit()
        conn.close()

        assert locker._count_today_workouts(db_file) == 1

    def test_no_workouts_today(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test no workouts today."""
        locker = create_locker(mock_tk, tmp_path)
        db_file = tmp_path / "sl_test.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute(
            "CREATE TABLE workouts "
            "(id TEXT PRIMARY KEY, start INTEGER, finish INTEGER)",
        )
        # Insert a workout from yesterday (24h+ ago)
        yesterday_ms = int((time.time() - 200000) * 1000)
        conn.execute(
            "INSERT INTO workouts VALUES (?, ?, ?)",
            ("w1", yesterday_ms, yesterday_ms + 3600000),
        )
        conn.commit()
        conn.close()

        assert locker._count_today_workouts(db_file) == 0

    def test_invalid_db_returns_zero(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns 0 for invalid database file."""
        locker = create_locker(mock_tk, tmp_path)
        bad_file = tmp_path / "not_a_db.db"
        bad_file.write_text("not a database")

        assert locker._count_today_workouts(bad_file) == 0

    def test_missing_table_returns_zero(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns 0 when workouts table doesn't exist."""
        locker = create_locker(mock_tk, tmp_path)
        db_file = tmp_path / "empty.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute("CREATE TABLE other (id TEXT)")
        conn.commit()
        conn.close()

        assert locker._count_today_workouts(db_file) == 0

    def test_multiple_workouts_today(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test counts multiple workouts today correctly."""
        locker = create_locker(mock_tk, tmp_path)
        db_file = tmp_path / "sl_test.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute(
            "CREATE TABLE workouts "
            "(id TEXT PRIMARY KEY, start INTEGER, finish INTEGER)",
        )
        now_ms = int(time.time() * 1000)
        conn.execute(
            "INSERT INTO workouts VALUES (?, ?, ?)",
            ("w1", now_ms, now_ms + 3600000),
        )
        conn.execute(
            "INSERT INTO workouts VALUES (?, ?, ?)",
            ("w2", now_ms + 100000, now_ms + 3700000),
        )
        conn.commit()
        conn.close()

        assert locker._count_today_workouts(db_file) == 2


class TestGetTodayWorkoutDurationMinutes:
    """Tests for _get_today_workout_duration_minutes method."""

    def test_returns_duration_for_today_workout(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns correct duration for a 60-minute workout."""
        locker = create_locker(mock_tk, tmp_path)
        db_file = tmp_path / "sl_test.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute(
            "CREATE TABLE workouts "
            "(id TEXT PRIMARY KEY, start INTEGER, finish INTEGER)",
        )
        now_ms = int(time.time() * 1000)
        duration_ms = 60 * 60 * 1000  # 60 minutes
        conn.execute(
            "INSERT INTO workouts VALUES (?, ?, ?)",
            ("w1", now_ms, now_ms + duration_ms),
        )
        conn.commit()
        conn.close()

        result = locker._get_today_workout_duration_minutes(db_file)
        assert result == pytest.approx(60.0, abs=1.0)

    def test_returns_zero_for_no_workouts(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns 0.0 when no workouts today."""
        locker = create_locker(mock_tk, tmp_path)
        db_file = tmp_path / "sl_test.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute(
            "CREATE TABLE workouts "
            "(id TEXT PRIMARY KEY, start INTEGER, finish INTEGER)",
        )
        yesterday_ms = int((time.time() - 200000) * 1000)
        conn.execute(
            "INSERT INTO workouts VALUES (?, ?, ?)",
            ("w1", yesterday_ms, yesterday_ms + 3600000),
        )
        conn.commit()
        conn.close()

        assert locker._get_today_workout_duration_minutes(db_file) == 0.0

    def test_sums_multiple_workouts(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test sums durations of multiple workouts today."""
        locker = create_locker(mock_tk, tmp_path)
        db_file = tmp_path / "sl_test.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute(
            "CREATE TABLE workouts "
            "(id TEXT PRIMARY KEY, start INTEGER, finish INTEGER)",
        )
        now_ms = int(time.time() * 1000)
        # 30 min + 25 min = 55 min total
        conn.execute(
            "INSERT INTO workouts VALUES (?, ?, ?)",
            ("w1", now_ms, now_ms + 30 * 60 * 1000),
        )
        conn.execute(
            "INSERT INTO workouts VALUES (?, ?, ?)",
            ("w2", now_ms + 31 * 60 * 1000, now_ms + 56 * 60 * 1000),
        )
        conn.commit()
        conn.close()

        result = locker._get_today_workout_duration_minutes(db_file)
        assert result == pytest.approx(55.0, abs=1.0)

    def test_ignores_invalid_finish(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test ignores workouts where finish <= start."""
        locker = create_locker(mock_tk, tmp_path)
        db_file = tmp_path / "sl_test.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute(
            "CREATE TABLE workouts "
            "(id TEXT PRIMARY KEY, start INTEGER, finish INTEGER)",
        )
        now_ms = int(time.time() * 1000)
        # finish == start (zero duration - should be excluded by WHERE)
        conn.execute(
            "INSERT INTO workouts VALUES (?, ?, ?)",
            ("w1", now_ms, now_ms),
        )
        conn.commit()
        conn.close()

        assert locker._get_today_workout_duration_minutes(db_file) == 0.0

    def test_invalid_db_returns_zero(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns 0.0 for invalid database file."""
        locker = create_locker(mock_tk, tmp_path)
        bad_file = tmp_path / "not_a_db.db"
        bad_file.write_text("not a database")

        assert locker._get_today_workout_duration_minutes(bad_file) == 0.0

    def test_missing_table_returns_zero(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns 0.0 when workouts table doesn't exist."""
        locker = create_locker(mock_tk, tmp_path)
        db_file = tmp_path / "empty.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute("CREATE TABLE other (id TEXT)")
        conn.commit()
        conn.close()

        assert locker._get_today_workout_duration_minutes(db_file) == 0.0


class TestGetTodayExerciseCount:
    """Tests for _get_today_exercise_count method."""

    def test_counts_exercises(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test counts distinct exercises in today's workouts."""
        locker = create_locker(mock_tk, tmp_path)
        db_file = tmp_path / "sl_test.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute(
            "CREATE TABLE workouts "
            "(id TEXT PRIMARY KEY, start INTEGER, finish INTEGER)",
        )
        conn.execute(
            "CREATE TABLE exercises (id TEXT, workout TEXT, exercise TEXT)",
        )
        now_ms = int(time.time() * 1000)
        conn.execute(
            "INSERT INTO workouts VALUES (?, ?, ?)",
            ("w1", now_ms, now_ms + 3600000),
        )
        conn.execute(
            "INSERT INTO exercises VALUES (?, ?, ?)",
            ("e1", "w1", "squat"),
        )
        conn.execute(
            "INSERT INTO exercises VALUES (?, ?, ?)",
            ("e2", "w1", "bench_press"),
        )
        conn.execute(
            "INSERT INTO exercises VALUES (?, ?, ?)",
            ("e3", "w1", "squat"),
        )
        conn.commit()
        conn.close()

        assert locker._get_today_exercise_count(db_file) == 2

    def test_no_exercises_returns_zero(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns 0 when no exercises exist."""
        locker = create_locker(mock_tk, tmp_path)
        db_file = tmp_path / "sl_test.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute(
            "CREATE TABLE workouts "
            "(id TEXT PRIMARY KEY, start INTEGER, finish INTEGER)",
        )
        conn.execute(
            "CREATE TABLE exercises (id TEXT, workout TEXT, exercise TEXT)",
        )
        now_ms = int(time.time() * 1000)
        conn.execute(
            "INSERT INTO workouts VALUES (?, ?, ?)",
            ("w1", now_ms, now_ms + 3600000),
        )
        conn.commit()
        conn.close()

        assert locker._get_today_exercise_count(db_file) == 0

    def test_invalid_db_returns_zero(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns 0 for invalid database file."""
        locker = create_locker(mock_tk, tmp_path)
        bad_file = tmp_path / "bad.db"
        bad_file.write_text("not a db")

        assert locker._get_today_exercise_count(bad_file) == 0

    def test_missing_table_returns_zero_exercises(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns 0 when exercises table doesn't exist."""
        locker = create_locker(mock_tk, tmp_path)
        db_file = tmp_path / "empty.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute(
            "CREATE TABLE workouts "
            "(id TEXT PRIMARY KEY, start INTEGER, finish INTEGER)",
        )
        conn.commit()
        conn.close()

        assert locker._get_today_exercise_count(db_file) == 0


class TestIsWorkoutFinishRecent:
    """Tests for _is_workout_finish_recent method."""

    def test_recent_workout_returns_true(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns True for workout that finished recently."""
        locker = create_locker(mock_tk, tmp_path)
        db_file = tmp_path / "sl_test.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute(
            "CREATE TABLE workouts "
            "(id TEXT PRIMARY KEY, start INTEGER, finish INTEGER)",
        )
        now_ms = int(time.time() * 1000)
        conn.execute(
            "INSERT INTO workouts VALUES (?, ?, ?)",
            ("w1", now_ms - 3600000, now_ms),
        )
        conn.commit()
        conn.close()

        assert locker._is_workout_finish_recent(db_file) is True

    def test_old_workout_returns_false(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns False for workout that finished >4 hours ago."""
        locker = create_locker(mock_tk, tmp_path)
        db_file = tmp_path / "sl_test.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute(
            "CREATE TABLE workouts "
            "(id TEXT PRIMARY KEY, start INTEGER, finish INTEGER)",
        )
        # Finished 5 hours ago (but still "today" in local time)
        now_ms = int(time.time() * 1000)
        old_finish = now_ms - 5 * 3600 * 1000
        conn.execute(
            "INSERT INTO workouts VALUES (?, ?, ?)",
            ("w1", old_finish - 3600000, old_finish),
        )
        conn.commit()
        conn.close()

        assert locker._is_workout_finish_recent(db_file) is False

    def test_no_workouts_returns_false(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns False when no workouts exist."""
        locker = create_locker(mock_tk, tmp_path)
        db_file = tmp_path / "sl_test.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute(
            "CREATE TABLE workouts "
            "(id TEXT PRIMARY KEY, start INTEGER, finish INTEGER)",
        )
        conn.commit()
        conn.close()

        assert locker._is_workout_finish_recent(db_file) is False

    def test_invalid_db_returns_false(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns False for invalid database file."""
        locker = create_locker(mock_tk, tmp_path)
        bad_file = tmp_path / "bad.db"
        bad_file.write_text("not a db")

        assert locker._is_workout_finish_recent(bad_file) is False
