"""Tests for _count_today_workouts and related database queries."""
# pylint: disable=protected-access,unused-argument

from __future__ import annotations

import sqlite3
import time
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


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

        assert not locker._count_today_workouts(db_file)

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

        assert not locker._count_today_workouts(bad_file)

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

        assert not locker._count_today_workouts(db_file)

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
