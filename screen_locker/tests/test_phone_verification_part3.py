"""Tests for multi-path workout-JSON pull and HTTP fall-through (part 3).

Covers the fix for the path mismatch where the app writes
``/sdcard/workout_result.json`` (primary) but the locker only checked the
app-external fallback path. The locker now pulls every candidate path, prefers
the one dated today, and falls through to the HTTP scan when an ADB pull yields
no usable JSON even though a device is connected.
"""

from __future__ import annotations

import json
from pathlib import Path
import time
from unittest.mock import MagicMock, patch

from screen_locker._constants import WORKOUT_APP_JSON_REMOTES
from screen_locker.tests.conftest import create_locker

_PRIMARY, _FALLBACK = WORKOUT_APP_JSON_REMOTES


def _today() -> str:
    """Return today's date as the app stamps it (local YYYY-MM-DD)."""
    return time.strftime("%Y-%m-%d")


def _adb_pull_from(path_contents: dict[str, str]) -> MagicMock:
    """Build a fake ``_run_adb`` that writes per-remote content to the dest file.

    ``path_contents`` maps a remote path to the JSON text the device would
    return for it. A remote absent from the map simulates a missing file
    (``adb pull`` failure).
    """

    def fake_run_adb(args: list[str]) -> tuple[bool, str]:
        if not args or args[0] != "pull":
            return False, ""
        remote, dest = args[1], args[2]
        content = path_contents.get(remote)
        if content is None:
            return False, ""
        Path(dest).write_text(content)
        return True, ""

    return MagicMock(side_effect=fake_run_adb)


class TestPullWorkoutAppJsonMultiPath:
    """Tests for _pull_workout_app_json across multiple candidate paths."""

    def test_prefers_todays_data_over_stale_primary(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A stale primary file must not shadow today's fallback file."""
        locker = create_locker(mock_tk, tmp_path)
        stale = json.dumps({"date": "2000-01-01", "exercises": ["old"]})
        fresh = json.dumps({"date": _today(), "exercises": ["new"]})
        fake = _adb_pull_from({_PRIMARY: stale, _FALLBACK: fresh})
        with patch.object(locker, "_run_adb", fake):
            result = locker._pull_workout_app_json()
        assert result is not None
        assert result["date"] == _today()
        assert result["exercises"] == ["new"]

    def test_returns_primary_when_dated_today(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Primary path dated today is returned without needing the fallback."""
        locker = create_locker(mock_tk, tmp_path)
        fresh = json.dumps({"date": _today(), "exercises": ["primary"]})
        fake = _adb_pull_from({_PRIMARY: fresh})
        with patch.object(locker, "_run_adb", fake):
            result = locker._pull_workout_app_json()
        assert result is not None
        assert result["exercises"] == ["primary"]

    def test_falls_back_to_stale_when_none_today(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """With no today's file, the first parseable payload is returned."""
        locker = create_locker(mock_tk, tmp_path)
        stale = json.dumps({"date": "2000-01-01", "exercises": ["old"]})
        fake = _adb_pull_from({_FALLBACK: stale})
        with patch.object(locker, "_run_adb", fake):
            result = locker._pull_workout_app_json()
        assert result is not None
        assert result["date"] == "2000-01-01"

    def test_keeps_first_stale_when_multiple_non_today(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """With several non-today files, the first parseable one is kept."""
        locker = create_locker(mock_tk, tmp_path)
        first = json.dumps({"date": "2000-01-01", "exercises": ["primary"]})
        second = json.dumps({"date": "1999-12-31", "exercises": ["fallback"]})
        fake = _adb_pull_from({_PRIMARY: first, _FALLBACK: second})
        with patch.object(locker, "_run_adb", fake):
            result = locker._pull_workout_app_json()
        assert result is not None
        assert result["exercises"] == ["primary"]

    def test_skips_unparseable_payload(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A corrupt file at one path doesn't block today's file at another."""
        locker = create_locker(mock_tk, tmp_path)
        fresh = json.dumps({"date": _today(), "exercises": ["new"]})
        fake = _adb_pull_from({_PRIMARY: "{not valid json", _FALLBACK: fresh})
        with patch.object(locker, "_run_adb", fake):
            result = locker._pull_workout_app_json()
        assert result is not None
        assert result["date"] == _today()

    def test_returns_none_when_no_candidate_pulls(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Returns None when no candidate path yields a file."""
        locker = create_locker(mock_tk, tmp_path)
        fake = _adb_pull_from({})
        with patch.object(locker, "_run_adb", fake):
            result = locker._pull_workout_app_json()
        assert result is None


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
