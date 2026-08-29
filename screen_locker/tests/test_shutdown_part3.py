"""Tests for shutdown schedule adjustment coverage gaps (part 3)."""

from __future__ import annotations

from datetime import UTC
import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker._constants import ADJUST_SHUTDOWN_SCRIPT
from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestRestoreOriginalConfigIfNeeded:
    """Tests for _restore_original_config_if_needed method."""

    def test_no_state_file_does_nothing(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test does nothing when no state file exists."""
        locker = create_locker(mock_tk, tmp_path)
        mock_file = MagicMock()
        mock_file.exists.return_value = False
        with patch(
            "screen_locker._shutdown_sick_state.SICK_DAY_STATE_FILE",
            mock_file,
        ):
            locker._restore_original_config_if_needed()

    def test_restores_when_state_from_previous_day(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test restores config when state date differs from today."""
        locker = create_locker(mock_tk, tmp_path)
        state_file = tmp_path / "state.json"
        state_file.write_text(
            json.dumps(
                {
                    "date": "2020-01-01",
                    "original_mon_wed_hour": 21,
                    "original_thu_sun_hour": 20,
                }
            )
        )
        with (
            patch(
                "screen_locker._shutdown_sick_state.SICK_DAY_STATE_FILE",
                state_file,
            ),
            patch.object(locker, "_write_restored_config") as mock_restore,
        ):
            locker._restore_original_config_if_needed()
        mock_restore.assert_called_once_with(21, 20, "2020-01-01")

    def test_does_not_restore_when_state_from_today(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test does not restore when state date matches today."""
        locker = create_locker(mock_tk, tmp_path)
        from datetime import datetime

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        state_file = tmp_path / "state.json"
        state_file.write_text(
            json.dumps(
                {
                    "date": today,
                    "original_mon_wed_hour": 21,
                    "original_thu_sun_hour": 20,
                }
            )
        )
        with (
            patch(
                "screen_locker._shutdown_sick_state.SICK_DAY_STATE_FILE",
                state_file,
            ),
            patch.object(locker, "_write_restored_config") as mock_restore,
        ):
            locker._restore_original_config_if_needed()
        mock_restore.assert_not_called()

    def test_returns_when_loaded_state_is_none(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns early when loaded state is None."""
        locker = create_locker(mock_tk, tmp_path)
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({"date": "2020-01-01"}))
        with (
            patch(
                "screen_locker._shutdown_sick_state.SICK_DAY_STATE_FILE",
                state_file,
            ),
            patch.object(locker, "_write_restored_config") as mock_restore,
        ):
            locker._restore_original_config_if_needed()
        mock_restore.assert_not_called()

    def test_handles_oserror(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test handles OSError when loading state."""
        locker = create_locker(mock_tk, tmp_path)
        mock_file = MagicMock()
        mock_file.exists.return_value = True
        mock_file.open.side_effect = OSError("fail")
        with patch(
            "screen_locker._shutdown_sick_state.SICK_DAY_STATE_FILE",
            mock_file,
        ):
            locker._restore_original_config_if_needed()

    def test_handles_json_decode_error(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test handles JSONDecodeError when loading state."""
        locker = create_locker(mock_tk, tmp_path)
        state_file = tmp_path / "state.json"
        state_file.write_text("not valid json{{{")
        with patch(
            "screen_locker._shutdown_sick_state.SICK_DAY_STATE_FILE",
            state_file,
        ):
            locker._restore_original_config_if_needed()


class TestReadShutdownConfig:
    """Tests for _read_shutdown_config method."""

    def test_returns_none_when_file_missing(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns None when config file doesn't exist."""
        locker = create_locker(mock_tk, tmp_path)
        mock_file = MagicMock()
        mock_file.exists.return_value = False
        with patch(
            "screen_locker._shutdown.SHUTDOWN_CONFIG_FILE",
            mock_file,
        ):
            assert locker._read_shutdown_config() is None

    def test_reads_valid_config(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test reads all three config values from file."""
        locker = create_locker(mock_tk, tmp_path)
        config_file = tmp_path / "shutdown.conf"
        config_file.write_text("MON_WED_HOUR=21\nTHU_SUN_HOUR=20\nMORNING_END_HOUR=8\n")
        with patch(
            "screen_locker._shutdown.SHUTDOWN_CONFIG_FILE",
            config_file,
        ):
            result = locker._read_shutdown_config()
        assert result == (21, 20, 8)

    def test_returns_none_when_values_missing(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns None when config has missing keys."""
        locker = create_locker(mock_tk, tmp_path)
        config_file = tmp_path / "shutdown.conf"
        config_file.write_text("MON_WED_HOUR=21\n")
        with patch(
            "screen_locker._shutdown.SHUTDOWN_CONFIG_FILE",
            config_file,
        ):
            result = locker._read_shutdown_config()
        assert result is None


class TestBuildShutdownCmd:
    """Tests for _build_shutdown_cmd method."""

    def test_without_restore(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test command without restore flag."""
        locker = create_locker(mock_tk, tmp_path)
        cmd = locker._build_shutdown_cmd(21, 20, 8, restore=False)
        assert cmd == [
            "/usr/bin/sudo",
            str(ADJUST_SHUTDOWN_SCRIPT),
            "21",
            "20",
            "8",
        ]

    def test_with_restore(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test command with restore flag."""
        locker = create_locker(mock_tk, tmp_path)
        cmd = locker._build_shutdown_cmd(21, 20, 8, restore=True)
        assert cmd == [
            "/usr/bin/sudo",
            str(ADJUST_SHUTDOWN_SCRIPT),
            "--restore",
            "21",
            "20",
            "8",
        ]
