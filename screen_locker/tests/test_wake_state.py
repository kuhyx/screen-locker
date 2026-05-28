"""Tests for screen_locker._wake_state — 100% branch coverage."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker._wake_state import has_workout_skip_today, load_wake_state

if TYPE_CHECKING:
    from pathlib import Path

_TODAY = "2026-05-28"
_STATE_PATH = "screen_locker._wake_state.WAKE_STATE_FILE"


# ---------------------------------------------------------------------------
# load_wake_state — file-absent / unreadable paths
# ---------------------------------------------------------------------------


class TestLoadWakeStateFileAbsent:
    def test_returns_none_when_file_missing(self, tmp_path: Path) -> None:
        """Returns None when state file does not exist."""
        missing = tmp_path / "no_such_file.json"
        with patch(_STATE_PATH, missing):
            assert load_wake_state() is None

    def test_returns_none_on_oserror(self, tmp_path: Path) -> None:
        """Returns None when the state file cannot be opened."""
        state_file = tmp_path / "wake_state.json"
        state_file.write_text("{}")
        with (
            patch(_STATE_PATH, state_file),
            patch("screen_locker._wake_state.WAKE_STATE_FILE", state_file),
            patch("builtins.open", side_effect=OSError("permission denied")),
        ):
            assert load_wake_state() is None

    def test_returns_none_on_invalid_json(self, tmp_path: Path) -> None:
        """Returns None when the state file contains invalid JSON."""
        state_file = tmp_path / "wake_state.json"
        state_file.write_text("not-valid-json")
        with patch(_STATE_PATH, state_file):
            assert load_wake_state() is None

    def test_returns_none_when_state_not_dict(self, tmp_path: Path) -> None:
        """Returns None when the JSON root is not a dict."""
        state_file = tmp_path / "wake_state.json"
        state_file.write_text("[1, 2, 3]")
        with patch(_STATE_PATH, state_file):
            assert load_wake_state() is None


# ---------------------------------------------------------------------------
# load_wake_state — date / HMAC validation paths
# ---------------------------------------------------------------------------


class TestLoadWakeStateValidation:
    def test_returns_none_when_date_stale(self, tmp_path: Path) -> None:
        """Returns None when the state file is from a previous day."""
        state_file = tmp_path / "wake_state.json"
        state = {"date": "2000-01-01", "skip_workout": True}
        state_file.write_text(json.dumps(state))
        with (
            patch(_STATE_PATH, state_file),
            patch(
                "screen_locker._wake_state._today_str",
                return_value=_TODAY,
            ),
        ):
            assert load_wake_state() is None

    def test_returns_none_when_hmac_invalid(self, tmp_path: Path) -> None:
        """Returns None when HMAC verification fails."""
        state_file = tmp_path / "wake_state.json"
        state = {"date": _TODAY, "skip_workout": True, "hmac": "bad"}
        state_file.write_text(json.dumps(state))
        with (
            patch(_STATE_PATH, state_file),
            patch(
                "screen_locker._wake_state._today_str",
                return_value=_TODAY,
            ),
            patch(
                "screen_locker._wake_state.verify_entry_hmac",
                return_value=False,
            ),
        ):
            assert load_wake_state() is None

    def test_returns_state_when_valid(self, tmp_path: Path) -> None:
        """Returns the state dict when date matches and HMAC is valid."""
        state_file = tmp_path / "wake_state.json"
        state = {"date": _TODAY, "skip_workout": True, "hmac": "sig"}
        state_file.write_text(json.dumps(state))
        with (
            patch(_STATE_PATH, state_file),
            patch(
                "screen_locker._wake_state._today_str",
                return_value=_TODAY,
            ),
            patch(
                "screen_locker._wake_state.verify_entry_hmac",
                return_value=True,
            ),
        ):
            result = load_wake_state()
        assert result is not None
        assert result["skip_workout"] is True

    def test_returns_state_when_skip_false(self, tmp_path: Path) -> None:
        """Returns the state dict even when skip_workout is False."""
        state_file = tmp_path / "wake_state.json"
        state = {"date": _TODAY, "skip_workout": False, "hmac": "sig"}
        state_file.write_text(json.dumps(state))
        with (
            patch(_STATE_PATH, state_file),
            patch(
                "screen_locker._wake_state._today_str",
                return_value=_TODAY,
            ),
            patch(
                "screen_locker._wake_state.verify_entry_hmac",
                return_value=True,
            ),
        ):
            result = load_wake_state()
        assert result is not None
        assert result["skip_workout"] is False


# ---------------------------------------------------------------------------
# has_workout_skip_today
# ---------------------------------------------------------------------------


class TestHasWorkoutSkipToday:
    def test_returns_false_when_no_state(self) -> None:
        """Returns False when load_wake_state returns None."""
        with patch(
            "screen_locker._wake_state.load_wake_state",
            return_value=None,
        ):
            assert has_workout_skip_today() is False

    def test_returns_true_when_skip_active(self) -> None:
        """Returns True when state has skip_workout=True."""
        with patch(
            "screen_locker._wake_state.load_wake_state",
            return_value={"date": _TODAY, "skip_workout": True},
        ):
            assert has_workout_skip_today() is True

    def test_returns_false_when_skip_inactive(self) -> None:
        """Returns False when state has skip_workout=False."""
        with patch(
            "screen_locker._wake_state.load_wake_state",
            return_value={"date": _TODAY, "skip_workout": False},
        ):
            assert has_workout_skip_today() is False


# ---------------------------------------------------------------------------
# _today_str
# ---------------------------------------------------------------------------


class TestTodayStr:
    def test_returns_iso_date_format(self) -> None:
        """_today_str returns a YYYY-MM-DD string."""
        from screen_locker._wake_state import _today_str

        result = _today_str()
        assert len(result) == 10
        assert result[4] == "-"
        assert result[7] == "-"


# ---------------------------------------------------------------------------
# OSError in load_wake_state body (JSON decode error path)
# ---------------------------------------------------------------------------


class TestLoadWakeStateOsError:
    def test_oserror_during_read(self, tmp_path: Path) -> None:
        """Returns None and warns when open() raises OSError."""
        state_file = tmp_path / "wake_state.json"
        state_file.write_text("{}")
        mock_open = MagicMock(side_effect=OSError("disk error"))
        with (
            patch(_STATE_PATH, state_file),
            patch("screen_locker._wake_state.open", mock_open, create=True),
            # We can't easily patch builtins.open for a specific file,
            # so we test by patching the json.load path
            patch("json.load", side_effect=OSError("disk error")),
        ):
            assert load_wake_state() is None
