"""Tests for early bird carrot feature in screen locker."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

from screen_locker.tests.conftest import (
    create_locker,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestIsEarlyBirdPending:
    """Tests for _is_early_bird_pending method.

    early_bird is a same-day pending marker stored in its own HMAC-signed
    file (EARLY_BIRD_PENDING_FILE), not in log.json — see
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
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        pending_file = tmp_path / "early_bird_pending.json"
        pending_file.write_text(json.dumps({"date": today, "hmac": "bad"}))
        with (
            patch("screen_locker._early_bird.EARLY_BIRD_PENDING_FILE", pending_file),
            patch(
                "screen_locker._compliance_predicates.verify_entry_hmac",
                return_value=False,
            ),
            patch(
                "screen_locker._compliance_predicates.compute_entry_hmac",
                return_value="sig",
            ),
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
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        pending_file = tmp_path / "early_bird_pending.json"
        pending_file.write_text(json.dumps({"date": today, "hmac": "sig"}))
        with (
            patch("screen_locker._early_bird.EARLY_BIRD_PENDING_FILE", pending_file),
            patch(
                "screen_locker._compliance_predicates.verify_entry_hmac",
                return_value=True,
            ),
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
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        pending_file = tmp_path / "early_bird_pending.json"
        pending_file.write_text(json.dumps({"date": today}))
        with (
            patch("screen_locker._early_bird.EARLY_BIRD_PENDING_FILE", pending_file),
            patch(
                "screen_locker._compliance_predicates.verify_entry_hmac",
                return_value=False,
            ),
            patch(
                "screen_locker._compliance_predicates.compute_entry_hmac",
                return_value=None,
            ),
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
        """Saves a date-stamped marker to the pending file, not log.json."""
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
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
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
