"""Tests for phone verification coverage gaps (part 2)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestTryWirelessReconnect:
    """Tests for _try_wireless_reconnect method."""

    def test_returns_false_when_no_prefix(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns False when subnet prefix can't be determined."""
        locker = create_locker(mock_tk, tmp_path)
        with patch.object(locker, "_get_local_subnet_prefix", return_value=None):
            result = locker._try_wireless_reconnect()
        assert result is False

    def test_returns_true_when_probe_succeeds(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns True when a probe finds the phone."""
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch.object(locker, "_get_local_subnet_prefix", return_value="192.168.1"),
            patch.object(locker, "_try_adb_connect", return_value=True),
            patch.object(locker, "_has_adb_device", return_value=True),
            patch(
                "screen_locker._phone_verification.socket.create_connection",
            ) as mock_conn,
        ):
            mock_sock = MagicMock()
            mock_sock.__enter__ = MagicMock(return_value=mock_sock)
            mock_sock.__exit__ = MagicMock(return_value=False)
            mock_conn.return_value = mock_sock
            result = locker._try_wireless_reconnect()
        assert result is True

    def test_returns_false_when_no_probe_succeeds(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns False when no probe finds the phone."""
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch.object(locker, "_get_local_subnet_prefix", return_value="192.168.1"),
            patch(
                "screen_locker._phone_verification.socket.create_connection",
                side_effect=OSError("refused"),
            ),
        ):
            result = locker._try_wireless_reconnect()
        assert result is False

    def test_probe_connect_succeeds_but_no_device(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test probe passes socket but adb_connect succeeds without device."""
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch.object(locker, "_get_local_subnet_prefix", return_value="192.168.1"),
            patch.object(locker, "_try_adb_connect", return_value=True),
            patch.object(locker, "_has_adb_device", return_value=False),
            patch(
                "screen_locker._phone_verification.socket.create_connection",
            ) as mock_conn,
        ):
            mock_sock = MagicMock()
            mock_sock.__enter__ = MagicMock(return_value=mock_sock)
            mock_sock.__exit__ = MagicMock(return_value=False)
            mock_conn.return_value = mock_sock
            result = locker._try_wireless_reconnect()
        assert result is False

    def test_probe_adb_connect_fails(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test probe where socket connects but adb connect fails."""
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch.object(locker, "_get_local_subnet_prefix", return_value="192.168.1"),
            patch.object(locker, "_try_adb_connect", return_value=False),
            patch(
                "screen_locker._phone_verification.socket.create_connection",
            ) as mock_conn,
        ):
            mock_sock = MagicMock()
            mock_sock.__enter__ = MagicMock(return_value=mock_sock)
            mock_sock.__exit__ = MagicMock(return_value=False)
            mock_conn.return_value = mock_sock
            result = locker._try_wireless_reconnect()
        assert result is False
