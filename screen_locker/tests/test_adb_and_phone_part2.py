"""Tests for ADB commands, phone connection, and database operations."""
# pylint: disable=protected-access,unused-argument

from __future__ import annotations

import datetime
import json
import sqlite3
import time
from typing import TYPE_CHECKING

import pytest

from python_pkg.screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path
    from unittest.mock import MagicMock


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

        assert not locker._get_today_workout_duration_minutes(db_file)

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

        assert not locker._get_today_workout_duration_minutes(db_file)

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

        assert not locker._get_today_workout_duration_minutes(bad_file)

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

        assert not locker._get_today_workout_duration_minutes(db_file)


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
            "(id TEXT PRIMARY KEY, start INTEGER, finish INTEGER, exercises TEXT)",
        )
        now_ms = int(time.time() * 1000)
        exercises_json = json.dumps(
            [
                {"id": "squat", "name": "Squat"},
                {"id": "bench_press", "name": "Bench Press"},
                {"id": "squat", "name": "Squat"},
                {"category": "WARMUP"},
            ]
        )
        conn.execute(
            "INSERT INTO workouts VALUES (?, ?, ?, ?)",
            ("w1", now_ms, now_ms + 3600000, exercises_json),
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
            "(id TEXT PRIMARY KEY, start INTEGER, finish INTEGER, exercises TEXT)",
        )
        now_ms = int(time.time() * 1000)
        conn.execute(
            "INSERT INTO workouts VALUES (?, ?, ?, ?)",
            ("w1", now_ms, now_ms + 3600000, "[]"),
        )
        conn.commit()
        conn.close()

        assert not locker._get_today_exercise_count(db_file)

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

        assert not locker._get_today_exercise_count(bad_file)

    def test_missing_exercises_column_returns_zero(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns 0 when workouts table has no exercises column."""
        locker = create_locker(mock_tk, tmp_path)
        db_file = tmp_path / "empty.db"
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
        conn.commit()
        conn.close()

        assert not locker._get_today_exercise_count(db_file)

    def test_null_exercises_json_returns_zero(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns 0 when exercises JSON is NULL."""
        locker = create_locker(mock_tk, tmp_path)
        db_file = tmp_path / "null_ex.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute(
            "CREATE TABLE workouts "
            "(id TEXT PRIMARY KEY, start INTEGER, finish INTEGER, exercises TEXT)",
        )
        now_ms = int(time.time() * 1000)
        conn.execute(
            "INSERT INTO workouts VALUES (?, ?, ?, ?)",
            ("w1", now_ms, now_ms + 3600000, None),
        )
        conn.commit()
        conn.close()

        assert not locker._get_today_exercise_count(db_file)

    def test_malformed_exercises_json_returns_zero(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns 0 when exercises JSON is malformed."""
        locker = create_locker(mock_tk, tmp_path)
        db_file = tmp_path / "bad_json.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute(
            "CREATE TABLE workouts "
            "(id TEXT PRIMARY KEY, start INTEGER, finish INTEGER, exercises TEXT)",
        )
        now_ms = int(time.time() * 1000)
        conn.execute(
            "INSERT INTO workouts VALUES (?, ?, ?, ?)",
            ("w1", now_ms, now_ms + 3600000, "not valid json"),
        )
        conn.commit()
        conn.close()

        assert not locker._get_today_exercise_count(db_file)


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
        # Anchor to local noon to avoid midnight boundary issues: the SQL
        # date() filter requires start and now to share the same local date.
        local_noon = (
            datetime.datetime.now(tz=datetime.timezone.utc)
            .astimezone()
            .replace(hour=12, minute=0, second=0, microsecond=0)
        )
        local_noon_ms = int(local_noon.timestamp() * 1000)
        conn.execute(
            "INSERT INTO workouts VALUES (?, ?, ?)",
            ("w1", local_noon_ms, local_noon_ms + 3_600_000),
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
        """Test returns False for workout that finished >24 hours ago."""
        locker = create_locker(mock_tk, tmp_path)
        db_file = tmp_path / "sl_test.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute(
            "CREATE TABLE workouts "
            "(id TEXT PRIMARY KEY, start INTEGER, finish INTEGER)",
        )
        # Finished 25 hours ago (not "today" in local time either)
        now_ms = int(time.time() * 1000)
        old_finish = now_ms - 25 * 3600 * 1000  # beyond 24h window
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
