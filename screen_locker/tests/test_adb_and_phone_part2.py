"""Tests for ADB commands, phone connection, and database operations."""
# pylint: disable=protected-access,unused-argument

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


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
