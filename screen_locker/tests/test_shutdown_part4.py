"""Tests for sick-day state save/load and config restoration."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestSaveSickDayState:
    """Tests for _save_sick_day_state method."""

    def test_saves_state_successfully(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test saves state file with correct content."""
        locker = create_locker(mock_tk, tmp_path)
        state_file = tmp_path / "state.json"
        with patch(
            "screen_locker._shutdown.SICK_DAY_STATE_FILE",
            state_file,
        ):
            result = locker._save_sick_day_state("2026-03-21", 21, 20)
        assert result is True
        data = json.loads(state_file.read_text())
        assert data["date"] == "2026-03-21"
        assert data["original_mon_wed_hour"] == 21
        assert data["original_thu_sun_hour"] == 20

    def test_returns_false_on_oserror(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns False when write fails."""
        locker = create_locker(mock_tk, tmp_path)
        mock_path = MagicMock()
        mock_path.open.side_effect = OSError("permission denied")
        with patch(
            "screen_locker._shutdown.SICK_DAY_STATE_FILE",
            mock_path,
        ):
            result = locker._save_sick_day_state("2026-03-21", 21, 20)
        assert result is False


class TestLoadSickDayState:
    """Tests for _load_sick_day_state method."""

    def test_loads_valid_state(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test loads state with all fields present."""
        locker = create_locker(mock_tk, tmp_path)
        state_file = tmp_path / "state.json"
        state_file.write_text(
            json.dumps(
                {
                    "date": "2026-03-20",
                    "original_mon_wed_hour": 21,
                    "original_thu_sun_hour": 20,
                }
            )
        )
        with patch(
            "screen_locker._shutdown.SICK_DAY_STATE_FILE",
            state_file,
        ):
            result = locker._load_sick_day_state()
        assert result == ("2026-03-20", 21, 20)

    def test_returns_none_when_fields_missing(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns None when required fields are missing."""
        locker = create_locker(mock_tk, tmp_path)
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({"date": "2026-03-20"}))
        with patch(
            "screen_locker._shutdown.SICK_DAY_STATE_FILE",
            state_file,
        ):
            result = locker._load_sick_day_state()
        assert result is None


class TestWriteRestoredConfig:
    """Tests for _write_restored_config method."""

    def test_restores_config_and_removes_state(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test restores config values and deletes state file."""
        locker = create_locker(mock_tk, tmp_path)
        state_file = tmp_path / "state.json"
        state_file.write_text("{}")
        with (
            patch.object(locker, "_read_shutdown_config", return_value=(20, 19, 8)),
            patch.object(
                locker, "_write_shutdown_config", return_value=True
            ) as mock_write,
            patch(
                "screen_locker._shutdown.SICK_DAY_STATE_FILE",
                state_file,
            ),
        ):
            locker._write_restored_config(21, 20, "2026-03-20")
        mock_write.assert_called_once_with(21, 20, 8, restore=True)
        assert not state_file.exists()

    def test_still_removes_state_when_config_read_fails(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test removes state file even when config read returns None."""
        locker = create_locker(mock_tk, tmp_path)
        state_file = tmp_path / "state.json"
        state_file.write_text("{}")
        with (
            patch.object(locker, "_read_shutdown_config", return_value=None),
            patch(
                "screen_locker._shutdown.SICK_DAY_STATE_FILE",
                state_file,
            ),
        ):
            locker._write_restored_config(21, 20, "2026-03-20")
        assert not state_file.exists()
