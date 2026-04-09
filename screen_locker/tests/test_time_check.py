"""Tests for _time_check NTP clock skew detection."""

from __future__ import annotations

import struct
import time
from unittest.mock import MagicMock, patch

from python_pkg.screen_locker._time_check import (
    _NTP_EPOCH_OFFSET,
    _query_ntp_offset,
    check_clock_skew,
)


class TestQueryNtpOffset:
    """Tests for _query_ntp_offset."""

    def test_returns_offset_on_success(self) -> None:
        """Test returns float offset when NTP server responds."""
        now = time.time()
        # Build a fake NTP response with server time close to now
        server_ntp = int(now + _NTP_EPOCH_OFFSET)
        fraction = 0
        response = b"\x00" * 40 + struct.pack("!II", server_ntp, fraction)

        mock_socket = MagicMock()
        mock_socket.__enter__ = MagicMock(return_value=mock_socket)
        mock_socket.__exit__ = MagicMock(return_value=False)
        mock_socket.recvfrom.return_value = (response, ("pool.ntp.org", 123))

        with patch("socket.socket", return_value=mock_socket):
            offset = _query_ntp_offset()

        assert offset is not None
        assert abs(offset) < 5  # Should be very close to zero

    def test_returns_none_on_oserror(self) -> None:
        """Test returns None when socket fails."""
        mock_socket = MagicMock()
        mock_socket.__enter__ = MagicMock(return_value=mock_socket)
        mock_socket.__exit__ = MagicMock(return_value=False)
        mock_socket.sendto.side_effect = OSError("network unreachable")

        with patch("socket.socket", return_value=mock_socket):
            offset = _query_ntp_offset()

        assert offset is None

    def test_returns_none_on_short_response(self) -> None:
        """Test returns None when NTP response is too short."""
        mock_socket = MagicMock()
        mock_socket.__enter__ = MagicMock(return_value=mock_socket)
        mock_socket.__exit__ = MagicMock(return_value=False)
        mock_socket.recvfrom.return_value = (b"\x00" * 10, ("pool.ntp.org", 123))

        with patch("socket.socket", return_value=mock_socket):
            offset = _query_ntp_offset()

        assert offset is None


class TestCheckClockSkew:
    """Tests for check_clock_skew."""

    def test_ok_within_threshold(self) -> None:
        """Test returns ok when clock offset is small."""
        with patch(
            "python_pkg.screen_locker._time_check._query_ntp_offset",
            return_value=2.5,
        ):
            ok, message = check_clock_skew()

        assert ok is True
        assert "OK" in message

    def test_fails_when_skew_exceeds_threshold(self) -> None:
        """Test returns failure when clock offset exceeds max."""
        with patch(
            "python_pkg.screen_locker._time_check._query_ntp_offset",
            return_value=600.0,
        ):
            ok, message = check_clock_skew()

        assert ok is False
        assert "600" in message

    def test_ntp_unreachable_passes(self) -> None:
        """Test returns ok when NTP server is unreachable (fail-open)."""
        with patch(
            "python_pkg.screen_locker._time_check._query_ntp_offset",
            return_value=None,
        ):
            ok, message = check_clock_skew()

        assert ok is True
        assert "skipped" in message.lower()

    def test_negative_offset_detected(self) -> None:
        """Test detects clock ahead with negative offset."""
        with patch(
            "python_pkg.screen_locker._time_check._query_ntp_offset",
            return_value=-400.0,
        ):
            ok, message = check_clock_skew()

        assert ok is False
        assert "ahead" in message.lower()
