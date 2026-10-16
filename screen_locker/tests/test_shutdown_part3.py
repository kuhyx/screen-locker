"""Tests for shutdown schedule adjustment coverage gaps (part 3)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker._constants import ADJUST_SHUTDOWN_SCRIPT
from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


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
        config_file.write_text(
            "MON_WED_MINUTES=1260\nTHU_SUN_MINUTES=1200\nMORNING_END_MINUTES=480\n"
        )
        with patch(
            "screen_locker._shutdown.SHUTDOWN_CONFIG_FILE",
            config_file,
        ):
            result = locker._read_shutdown_config()
        assert result == (1260, 1200, 480)

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
        cmd = locker._build_shutdown_cmd(1260, 1200, 480, restore=False)
        assert cmd == [
            "/usr/bin/sudo",
            str(ADJUST_SHUTDOWN_SCRIPT),
            "21:00",
            "20:00",
            "08:00",
        ]

    def test_with_restore(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test command with restore flag."""
        locker = create_locker(mock_tk, tmp_path)
        cmd = locker._build_shutdown_cmd(1260, 1200, 480, restore=True)
        assert cmd == [
            "/usr/bin/sudo",
            str(ADJUST_SHUTDOWN_SCRIPT),
            "--restore",
            "21:00",
            "20:00",
            "08:00",
        ]
