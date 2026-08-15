"""Tests for JSON workout validation and HTTP fallback (part 4).

Replaces the obsolete StrongLifts-DB-based ``test_phone_check_unlock.py``.
Covers ``_validate_json_data`` (all status branches) and the HTTP fallback
``_scan_for_http_server`` / ``_fetch_http_workout`` used when ADB is
unavailable. Network is fully mocked — no test touches a real socket.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker._constants import (
    MIN_WORKOUT_DURATION_MINUTES,
    WORKOUT_DURATION_ACCEPT_MINUTES,
)
from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


def _today() -> str:
    """Return today's date as the validator computes it (local YYYY-MM-DD)."""
    return time.strftime("%Y-%m-%d")


def _mock_cm(return_value: MagicMock) -> MagicMock:
    """Build a MagicMock usable as a context manager yielding ``return_value``."""
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=return_value)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


class TestValidateJsonData:
    """Tests for _validate_json_data across every status branch."""

    def test_stale_when_not_today(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        status, message = locker._validate_json_data(
            {"date": "2000-01-01", "exercises": ["x"], "duration_seconds": 4000}
        )
        assert status == "stale"
        assert "2000-01-01" in message

    def test_no_exercises_when_empty(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        status, message = locker._validate_json_data(
            {"date": _today(), "exercises": [], "duration_seconds": 4000}
        )
        assert status == "no_exercises"
        assert "exercise" in message.lower()

    def test_too_short_under_minimum(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        # Derive from the ACCEPT bar, not the advertised one: a duration
        # merely under 40 may still clear the hidden leeway and verify.
        short_seconds = int((WORKOUT_DURATION_ACCEPT_MINUTES - 5) * 60)
        status, message = locker._validate_json_data(
            {"date": _today(), "exercises": ["x"], "duration_seconds": short_seconds}
        )
        assert status == "too_short"
        # ...but the message still advertises 40, never the real cutoff.
        assert f"{MIN_WORKOUT_DURATION_MINUTES}" in message
        assert f"{WORKOUT_DURATION_ACCEPT_MINUTES}" not in message

    def test_verified_all_succeeded(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        status, message = locker._validate_json_data(
            {
                "date": _today(),
                "exercises": ["x"],
                "duration_seconds": 6000,
                "succeeded": True,
            }
        )
        assert status == "verified"
        assert "all succeeded" in message

    def test_verified_partial_when_not_succeeded(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        status, message = locker._validate_json_data(
            {
                "date": _today(),
                "exercises": ["x"],
                "duration_seconds": 6000,
                "succeeded": False,
            }
        )
        assert status == "verified"
        assert "partial" in message


class TestScanForHttpServer:
    """Tests for _scan_for_http_server subnet probing."""

    def test_returns_none_without_prefix(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        with patch.object(locker, "_get_local_subnet_prefix", return_value=None):
            assert locker._scan_for_http_server() is None

    def test_returns_url_when_probe_connects(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch.object(locker, "_get_local_subnet_prefix", return_value="192.168.1"),
            patch(
                "screen_locker._phone_verification.socket.create_connection",
                return_value=_mock_cm(MagicMock()),
            ),
        ):
            result = locker._scan_for_http_server()
        assert result is not None
        assert result.startswith("http://192.168.1.")
        assert result.endswith(":8765/workout")

    def test_returns_none_when_all_probes_refused(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch.object(locker, "_get_local_subnet_prefix", return_value="192.168.1"),
            patch(
                "screen_locker._phone_verification.socket.create_connection",
                side_effect=OSError("refused"),
            ),
        ):
            assert locker._scan_for_http_server() is None


class TestVerifyPhoneWorkoutSyncStaleness:
    """A stale/non-verified sync result must not preempt a fresher fallback."""

    def test_stale_synced_data_falls_through_to_a_fresh_adb_pull(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """A stale cloud entry must not preempt a fresher ADB result."""
        locker = create_locker(mock_tk, tmp_path)
        stale_synced = {
            "date": "2000-01-01",
            "exercises": ["old"],
            "duration_seconds": 4000,
            "succeeded": True,
        }
        fresh_adb = {
            "date": _today(),
            "exercises": ["new"],
            "duration_seconds": 4000,
            "succeeded": True,
        }
        with (
            patch(
                "screen_locker._phone_verification.check_clock_skew",
                return_value=(True, ""),
            ),
            patch(
                "screen_locker._phone_verification.pull_synced_workout",
                return_value=(stale_synced, None),
            ),
            patch.object(locker, "_is_phone_connected", return_value=True),
            patch.object(locker, "_pull_workout_app_json", return_value=fresh_adb),
        ):
            status, _ = locker._verify_phone_workout()
        assert status == "verified"

    def test_stale_synced_data_used_as_last_resort_when_fallback_is_empty(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """A non-verified sync result still beats no_phone/not_verified."""
        locker = create_locker(mock_tk, tmp_path)
        stale_synced = {
            "date": "2000-01-01",
            "exercises": ["old"],
            "duration_seconds": 4000,
            "succeeded": True,
        }
        with (
            patch(
                "screen_locker._phone_verification.check_clock_skew",
                return_value=(True, ""),
            ),
            patch(
                "screen_locker._phone_verification.pull_synced_workout",
                return_value=(stale_synced, None),
            ),
            patch.object(locker, "_is_phone_connected", return_value=False),
            patch.object(locker, "_fetch_http_workout", return_value=None),
        ):
            status, message = locker._verify_phone_workout()
        assert status == "stale"
        assert "2000-01-01" in message


class TestFetchHttpWorkout:
    """Tests for _fetch_http_workout over the local HTTP server."""

    def test_returns_none_when_scan_finds_nothing(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        with patch.object(locker, "_scan_for_http_server", return_value=None):
            assert locker._fetch_http_workout() is None

    def test_returns_json_on_http_200(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
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
