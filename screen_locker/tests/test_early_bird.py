"""Tests for early bird carrot feature in screen locker."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

from screen_locker.tests.conftest import (
    create_locker,
)

if TYPE_CHECKING:
    from pathlib import Path

    from screen_locker.screen_lock import ScreenLocker


class TestGetLocalTimeMinutes:
    """Tests for _get_local_time_minutes helper."""

    def test_returns_int_within_day_range(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Returns an integer between 0 and 1439 (minutes in a day)."""
        locker = create_locker(mock_tk, tmp_path)
        result = locker._get_local_time_minutes()
        assert isinstance(result, int)
        assert 0 <= result < 24 * 60


class TestIsEarlyBirdTime:
    """Tests for _is_early_bird_time based on local clock."""

    def _locker(
        self,
        mock_tk: MagicMock,
        tmp_path: Path,
        minutes: int,
    ) -> ScreenLocker:
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_get_local_time_minutes",
            MagicMock(return_value=minutes),
        )
        return locker

    def test_within_window(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """6:00 AM (360 min) is within the early bird window."""
        locker = self._locker(mock_tk, tmp_path, 360)
        assert locker._is_early_bird_time() is True

    def test_at_start_of_window(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """5:00 AM (300 min) is the inclusive start of the window."""
        locker = self._locker(mock_tk, tmp_path, 300)
        assert locker._is_early_bird_time() is True

    def test_just_before_start(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """4:59 AM (299 min) is before the window."""
        locker = self._locker(mock_tk, tmp_path, 299)
        assert locker._is_early_bird_time() is False

    def test_just_before_end(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """8:29 AM (509 min) is still within the window."""
        locker = self._locker(mock_tk, tmp_path, 509)
        assert locker._is_early_bird_time() is True

    def test_at_end_of_window(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """8:30 AM (510 min) is the exclusive end — not in window."""
        locker = self._locker(mock_tk, tmp_path, 510)
        assert locker._is_early_bird_time() is False

    def test_after_window(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """9:00 AM (540 min) is past the window."""
        locker = self._locker(mock_tk, tmp_path, 540)
        assert locker._is_early_bird_time() is False

    def test_extended_window_ends_at_9am(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """When has_extended_early_bird is True, window closes at 09:00 (540 min)."""
        locker = self._locker(mock_tk, tmp_path, 539)  # 08:59 — still inside
        with patch(
            "screen_locker._early_bird.has_extended_early_bird",
            return_value=True,
        ):
            assert locker._is_early_bird_time() is True

    def test_extended_window_closed_at_9am(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Extended window excludes exactly 09:00 (540 min)."""
        locker = self._locker(mock_tk, tmp_path, 540)  # 09:00 — exclusive end
        with patch(
            "screen_locker._early_bird.has_extended_early_bird",
            return_value=True,
        ):
            assert locker._is_early_bird_time() is False

    def test_midnight(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Midnight (0 min) is outside the window."""
        locker = self._locker(mock_tk, tmp_path, 0)
        assert locker._is_early_bird_time() is False


class TestIsEarlyBirdPending:
    """Tests for _is_early_bird_pending method.

    early_bird is a same-day pending marker stored in its own HMAC-signed
    file (EARLY_BIRD_PENDING_FILE), not in workout_log.json — see
    _early_bird.py's module docstring for why.
    """

    def test_no_pending_file(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Return False when the pending file does not exist."""
        locker = create_locker(mock_tk, tmp_path)
        assert locker._is_early_bird_pending() is False

    def test_invalid_json(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Return False when the pending file contains invalid JSON."""
        locker = create_locker(mock_tk, tmp_path)
        pending_file = tmp_path / "early_bird_pending.json"
        pending_file.write_text("{bad json}")
        with patch("screen_locker._early_bird.EARLY_BIRD_PENDING_FILE", pending_file):
            assert locker._is_early_bird_pending() is False

    def test_os_error_on_open(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Return False when opening the pending file raises OSError."""
        locker = create_locker(mock_tk, tmp_path)
        mock_file = MagicMock()
        mock_file.exists.return_value = True
        mock_file.open.side_effect = OSError("permission denied")
        with patch("screen_locker._early_bird.EARLY_BIRD_PENDING_FILE", mock_file):
            assert locker._is_early_bird_pending() is False

    def test_stale_date(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Return False when the marker is from a previous day."""
        locker = create_locker(mock_tk, tmp_path)
        pending_file = tmp_path / "early_bird_pending.json"
        pending_file.write_text(json.dumps({"date": "2000-01-01", "hmac": "sig"}))
        with patch("screen_locker._early_bird.EARLY_BIRD_PENDING_FILE", pending_file):
            assert locker._is_early_bird_pending() is False

    def test_hmac_invalid(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Return False when HMAC verification fails."""
        locker = create_locker(mock_tk, tmp_path)
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        pending_file = tmp_path / "early_bird_pending.json"
        pending_file.write_text(json.dumps({"date": today, "hmac": "bad"}))
        with (
            patch("screen_locker._early_bird.EARLY_BIRD_PENDING_FILE", pending_file),
            patch("screen_locker._early_bird.verify_entry_hmac", return_value=False),
            patch("screen_locker._early_bird.compute_entry_hmac", return_value="sig"),
        ):
            assert locker._is_early_bird_pending() is False

    def test_today_valid_marker(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Return True when today's marker is present and HMAC-valid."""
        locker = create_locker(mock_tk, tmp_path)
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        pending_file = tmp_path / "early_bird_pending.json"
        pending_file.write_text(json.dumps({"date": today, "hmac": "sig"}))
        with (
            patch("screen_locker._early_bird.EARLY_BIRD_PENDING_FILE", pending_file),
            patch("screen_locker._early_bird.verify_entry_hmac", return_value=True),
        ):
            assert locker._is_early_bird_pending() is True

    def test_unsigned_accepted_when_key_unavailable(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Unsigned marker is accepted when no HMAC key is configured."""
        locker = create_locker(mock_tk, tmp_path)
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        pending_file = tmp_path / "early_bird_pending.json"
        pending_file.write_text(json.dumps({"date": today}))
        with (
            patch("screen_locker._early_bird.EARLY_BIRD_PENDING_FILE", pending_file),
            patch("screen_locker._early_bird.verify_entry_hmac", return_value=False),
            patch("screen_locker._early_bird.compute_entry_hmac", return_value=None),
        ):
            assert locker._is_early_bird_pending() is True


class TestSaveEarlyBirdPending:
    """Tests for _save_early_bird_pending method."""

    def test_saves_pending_marker(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Saves a date-stamped marker to the pending file, not workout_log.json."""
        locker = create_locker(mock_tk, tmp_path)
        pending_file = tmp_path / "early_bird_pending.json"
        with (
            patch("screen_locker._early_bird.EARLY_BIRD_PENDING_FILE", pending_file),
            patch("screen_locker._early_bird.compute_entry_hmac", return_value=None),
        ):
            locker._save_early_bird_pending()

        assert pending_file.exists()
        with pending_file.open() as f:
            data: dict[str, Any] = json.load(f)
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        assert data["date"] == today
        assert not locker.log_file.exists()

    def test_signs_when_hmac_key_available(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Includes an hmac field when a signature is computed."""
        locker = create_locker(mock_tk, tmp_path)
        pending_file = tmp_path / "early_bird_pending.json"
        with (
            patch("screen_locker._early_bird.EARLY_BIRD_PENDING_FILE", pending_file),
            patch("screen_locker._early_bird.compute_entry_hmac", return_value="sig"),
        ):
            locker._save_early_bird_pending()

        data: dict[str, Any] = json.loads(pending_file.read_text())
        assert data["hmac"] == "sig"

    def test_os_error_on_save(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Warns and does not raise when writing the pending file fails."""
        locker = create_locker(mock_tk, tmp_path)
        mock_file = MagicMock()
        mock_file.open.side_effect = OSError("disk full")
        with (
            patch("screen_locker._early_bird.EARLY_BIRD_PENDING_FILE", mock_file),
            patch("screen_locker._early_bird.compute_entry_hmac", return_value=None),
        ):
            locker._save_early_bird_pending()
