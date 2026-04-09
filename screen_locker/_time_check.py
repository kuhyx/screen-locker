"""System clock skew detection via NTP."""

from __future__ import annotations

import logging
import socket
import struct
import time

from python_pkg.screen_locker._constants import MAX_CLOCK_SKEW_SECONDS

_logger = logging.getLogger(__name__)

_NTP_EPOCH_OFFSET = 2208988800  # Seconds between 1900-01-01 and 1970-01-01
_NTP_PORT = 123
_NTP_TIMEOUT = 5
_NTP_MIN_PACKET_SIZE = 48


def _query_ntp_offset(server: str = "pool.ntp.org") -> float | None:
    """Query an NTP server and return the clock offset in seconds.

    Uses a minimal SNTP (RFC 4330) client-mode request.

    Returns:
        Offset in seconds (positive = local clock is ahead), or None on error.
    """
    # NTP v3, mode 3 (client), transmit timestamp at bytes 40-47
    packet = b"\x1b" + b"\0" * 47
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(_NTP_TIMEOUT)
            t1 = time.time()
            sock.sendto(packet, (server, _NTP_PORT))
            data, _ = sock.recvfrom(1024)
            t4 = time.time()
    except OSError as exc:
        _logger.info("NTP query to %s failed: %s", server, exc)
        return None

    if len(data) < _NTP_MIN_PACKET_SIZE:
        return None

    # Transmit timestamp from server (bytes 40-47)
    tx_seconds = struct.unpack("!I", data[40:44])[0] - _NTP_EPOCH_OFFSET
    tx_fraction = struct.unpack("!I", data[44:48])[0] / (2**32)
    server_time = tx_seconds + tx_fraction

    # Simplified offset: server_time should be close to (t1 + t4) / 2
    local_mid = (t1 + t4) / 2
    return server_time - local_mid


def check_clock_skew() -> tuple[bool, str]:
    """Check if system clock is within acceptable skew of NTP time.

    Returns:
        Tuple of (ok, message).
        ok is True if clock is within MAX_CLOCK_SKEW_SECONDS or NTP is unreachable.
        When NTP is unreachable, we allow through (fail-open for network issues).
    """
    offset = _query_ntp_offset()
    if offset is None:
        _logger.info("NTP unreachable — allowing through")
        return True, "NTP check skipped (server unreachable)"

    abs_offset = abs(offset)
    if abs_offset > MAX_CLOCK_SKEW_SECONDS:
        direction = "ahead" if offset < 0 else "behind"
        _logger.warning(
            "Clock skew detected: %.0f seconds %s",
            abs_offset,
            direction,
        )
        return False, (
            f"System clock is {abs_offset:.0f}s {direction} of NTP time. "
            f"Max allowed skew: {MAX_CLOCK_SKEW_SECONDS}s."
        )
    return True, f"Clock OK (offset: {offset:+.1f}s)"
