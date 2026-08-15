"""Tests for multi-path workout-JSON pull and HTTP fall-through (part 3).

Covers the fix for the path mismatch where the app writes
``/sdcard/workout_result.json`` (primary) but the locker only checked the
app-external fallback path. The locker now pulls every candidate path, prefers
the one dated today, and falls through to the HTTP scan when an ADB pull yields
no usable JSON even though a device is connected.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker._constants import WORKOUT_APP_JSON_REMOTES
from screen_locker.tests.conftest import create_locker
from screen_locker.tests.test_phone_verification_part3 import _today

if TYPE_CHECKING:
    from pathlib import Path

_PRIMARY, _FALLBACK = WORKOUT_APP_JSON_REMOTES


class TestVerifyPhoneWorkoutFallthrough:
    """Tests for the ADB→HTTP fall-through in _verify_phone_workout."""

    def test_adb_connected_but_pull_empty_falls_through_to_http(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A connected device with no pullable JSON still tries the HTTP scan."""
        locker = create_locker(mock_tk, tmp_path)
        http_data = {
            "date": _today(),
            "exercises": ["a"],
            "duration_seconds": 4000,
            "succeeded": True,
        }
        with (
            patch(
                "screen_locker._phone_verification.check_clock_skew",
                return_value=(True, ""),
            ),
            patch.object(locker, "_is_phone_connected", return_value=True),
            patch.object(locker, "_pull_workout_app_json", return_value=None),
            patch.object(locker, "_fetch_http_workout", return_value=http_data),
        ):
            status, _ = locker._verify_phone_workout()
        assert status == "verified"

    def test_adb_connected_pull_and_http_empty_is_not_verified(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Connected device, no JSON anywhere → not_verified (not no_phone)."""
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch(
                "screen_locker._phone_verification.check_clock_skew",
                return_value=(True, ""),
            ),
            patch.object(locker, "_is_phone_connected", return_value=True),
            patch.object(locker, "_pull_workout_app_json", return_value=None),
            patch.object(locker, "_fetch_http_workout", return_value=None),
        ):
            status, _ = locker._verify_phone_workout()
        assert status == "not_verified"

    def test_adb_pull_success_returns_without_http(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A successful ADB pull validates directly, never touching HTTP."""
        locker = create_locker(mock_tk, tmp_path)
        data = {
            "date": _today(),
            "exercises": ["a"],
            "duration_seconds": 4000,
            "succeeded": False,
        }
        http = MagicMock()
        with (
            patch(
                "screen_locker._phone_verification.check_clock_skew",
                return_value=(True, ""),
            ),
            patch.object(locker, "_is_phone_connected", return_value=True),
            patch.object(locker, "_pull_workout_app_json", return_value=data),
            patch.object(locker, "_fetch_http_workout", http),
        ):
            status, _ = locker._verify_phone_workout()
        assert status == "verified"
        http.assert_not_called()

    def test_clock_tampered_short_circuits(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A clock-skew failure returns clock_tampered before any phone access."""
        locker = create_locker(mock_tk, tmp_path)
        with patch(
            "screen_locker._phone_verification.check_clock_skew",
            return_value=(False, "clock skew too large"),
        ):
            status, message = locker._verify_phone_workout()
        assert status == "clock_tampered"
        assert message == "clock skew too large"

    def test_no_device_and_http_empty_is_no_phone(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """No device and no HTTP server → no_phone."""
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch(
                "screen_locker._phone_verification.check_clock_skew",
                return_value=(True, ""),
            ),
            patch.object(locker, "_is_phone_connected", return_value=False),
            patch.object(locker, "_fetch_http_workout", return_value=None),
        ):
            status, _ = locker._verify_phone_workout()
        assert status == "no_phone"

    def test_synced_data_is_validated_directly_without_adb_or_http(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A successful sync pull short-circuits ADB/HTTP entirely."""
        locker = create_locker(mock_tk, tmp_path)
        synced_data = {
            "date": _today(),
            "exercises": ["a"],
            "duration_seconds": 4000,
            "succeeded": True,
        }
        adb = MagicMock()
        http = MagicMock()
        with (
            patch(
                "screen_locker._phone_verification.check_clock_skew",
                return_value=(True, ""),
            ),
            patch(
                "screen_locker._phone_verification.pull_synced_workout",
                return_value=(synced_data, None),
            ),
            patch.object(locker, "_is_phone_connected", adb),
            patch.object(locker, "_fetch_http_workout", http),
        ):
            status, _ = locker._verify_phone_workout()
        assert status == "verified"
        adb.assert_not_called()
        http.assert_not_called()

    def test_sync_error_falls_through_to_a_successful_fallback_silently(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A sync error must never block a result the fallback can still find."""
        locker = create_locker(mock_tk, tmp_path)
        http_data = {
            "date": _today(),
            "exercises": ["a"],
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
                return_value=(None, "network unreachable"),
            ),
            patch.object(locker, "_is_phone_connected", return_value=False),
            patch.object(locker, "_fetch_http_workout", return_value=http_data),
        ):
            status, _ = locker._verify_phone_workout()
        assert status == "verified"

    def test_sync_error_and_empty_fallback_returns_sync_failed(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Nothing found anywhere AND sync errored → sync_failed, not no_phone."""
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch(
                "screen_locker._phone_verification.check_clock_skew",
                return_value=(True, ""),
            ),
            patch(
                "screen_locker._phone_verification.pull_synced_workout",
                return_value=(None, "bad token"),
            ),
            patch.object(locker, "_is_phone_connected", return_value=False),
            patch.object(locker, "_fetch_http_workout", return_value=None),
        ):
            status, message = locker._verify_phone_workout()
        assert status == "sync_failed"
        assert message == "bad token"
