"""Tests for JSON workout validation and HTTP fallback (part 4).

Replaces the obsolete StrongLifts-DB-based ``test_phone_check_unlock.py``.
Covers ``_validate_json_data`` (all status branches) and the HTTP fallback
``_scan_for_http_server`` / ``_fetch_http_workout`` used when ADB is
unavailable. Network is fully mocked — no test touches a real socket.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestFetchHttpWorkout:
    """Tests for _fetch_http_workout over the local HTTP server."""

    def test_returns_none_when_scan_finds_nothing(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Returns none when scan finds nothing."""
        locker = create_locker(mock_tk, tmp_path)
        with patch.object(locker, "_scan_for_http_server", return_value=None):
            assert locker._fetch_http_workout() is None

    def test_returns_json_on_http_200(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Returns JSON on HTTP 200."""
        locker = create_locker(mock_tk, tmp_path)
        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = b'{"date": "2026-06-12", "exercises": ["a"]}'
        conn = MagicMock()
        conn.getresponse.return_value = resp
        with (
            patch.object(
                locker,
                "_scan_for_http_server",
                return_value="http://192.168.1.5:8765/workout",
            ),
            patch(
                "screen_locker._phone_verification._HTTPConnection",
                return_value=conn,
            ),
        ):
            result = locker._fetch_http_workout()
        assert result == {"date": "2026-06-12", "exercises": ["a"]}

    def test_returns_none_on_non_ok_status(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Returns none on non ok status."""
        locker = create_locker(mock_tk, tmp_path)
        resp = MagicMock()
        resp.status = 404
        conn = MagicMock()
        conn.getresponse.return_value = resp
        with (
            patch.object(
                locker,
                "_scan_for_http_server",
                return_value="http://192.168.1.5:8765/workout",
            ),
            patch(
                "screen_locker._phone_verification._HTTPConnection",
                return_value=conn,
            ),
        ):
            assert locker._fetch_http_workout() is None

    def test_returns_none_on_connection_error(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Returns none on connection error."""
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch.object(
                locker,
                "_scan_for_http_server",
                return_value="http://192.168.1.5:8765/workout",
            ),
            patch(
                "screen_locker._phone_verification._HTTPConnection",
                side_effect=OSError("unreachable"),
            ),
        ):
            assert locker._fetch_http_workout() is None
