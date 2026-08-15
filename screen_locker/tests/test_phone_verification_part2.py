"""Tests for phone verification coverage gaps (part 2)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestGetWirelessSerial:
    """Tests for _get_wireless_serial method."""

    def test_returns_wireless_serial(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns ip:port serial for a wireless device."""
        locker = create_locker(mock_tk, tmp_path)
        output = "List of devices attached\n192.168.1.42:5555\tdevice\n"
        with patch.object(locker, "_run_adb", return_value=(True, output)):
            result = locker._get_wireless_serial()
        assert result == "192.168.1.42:5555"

    def test_returns_none_when_adb_fails(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns None when adb devices fails."""
        locker = create_locker(mock_tk, tmp_path)
        with patch.object(locker, "_run_adb", return_value=(False, "")):
            result = locker._get_wireless_serial()
        assert result is None

    def test_returns_none_when_no_wireless_device(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns None when only USB devices are connected."""
        locker = create_locker(mock_tk, tmp_path)
        output = "List of devices attached\nABC123DEF456\tdevice\n"
        with patch.object(locker, "_run_adb", return_value=(True, output)):
            result = locker._get_wireless_serial()
        assert result is None

    def test_skips_offline_wireless_device(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test skips offline wireless devices."""
        locker = create_locker(mock_tk, tmp_path)
        output = "List of devices attached\n192.168.1.42:5555\toffline\n"
        with patch.object(locker, "_run_adb", return_value=(True, output)):
            result = locker._get_wireless_serial()
        assert result is None


class TestTryAdbConnect:
    """Tests for _try_adb_connect method."""

    def test_successful_connect(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test successful ADB connect."""
        locker = create_locker(mock_tk, tmp_path)
        with patch.object(
            locker, "_run_adb", return_value=(True, "connected to 192.168.1.42:5555")
        ):
            result = locker._try_adb_connect("192.168.1.42:5555")
        assert result is True

    def test_failed_connect_unable(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test connect failure with 'unable' in output."""
        locker = create_locker(mock_tk, tmp_path)
        with patch.object(
            locker, "_run_adb", return_value=(False, "unable to connect")
        ):
            result = locker._try_adb_connect("192.168.1.42:5555")
        assert result is False

    def test_failed_connect_with_failed(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test connect failure with 'failed' in output."""
        locker = create_locker(mock_tk, tmp_path)
        with patch.object(
            locker,
            "_run_adb",
            return_value=(False, "connected but failed to authenticate"),
        ):
            result = locker._try_adb_connect("192.168.1.42:5555")
        assert result is False

    def test_no_connected_in_output(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test connect failure when 'connected' not in output."""
        locker = create_locker(mock_tk, tmp_path)
        with patch.object(
            locker, "_run_adb", return_value=(False, "some random output")
        ):
            result = locker._try_adb_connect("192.168.1.42:5555")
        assert result is False


class TestGetLocalSubnetPrefix:
    """Tests for _get_local_subnet_prefix method."""

    def test_returns_prefix(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns first three octets of local IP."""
        locker = create_locker(mock_tk, tmp_path)
        mock_sock = MagicMock()
        mock_sock.getsockname.return_value = ("192.168.1.100", 12345)
        mock_sock.__enter__ = MagicMock(return_value=mock_sock)
        mock_sock.__exit__ = MagicMock(return_value=False)
        with patch(
            "screen_locker._phone_verification.socket.socket",
            return_value=mock_sock,
        ):
            result = locker._get_local_subnet_prefix()
        assert result == "192.168.1"

    def test_returns_none_on_oserror(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns None when socket raises OSError."""
        locker = create_locker(mock_tk, tmp_path)
        with patch(
            "screen_locker._phone_verification.socket.socket",
            side_effect=OSError("no network"),
        ):
            result = locker._get_local_subnet_prefix()
        assert result is None
