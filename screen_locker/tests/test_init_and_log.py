"""Tests for screen_locker initialization, logging, and basic operations."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import tkinter as tk
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from screen_locker.screen_lock import _assert_not_under_pytest
from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestAssertNotUnderPytest:
    """Tests for the _assert_not_under_pytest runtime guard."""

    def test_raises_when_tk_is_real(self) -> None:
        """Guard fires if tk.Tk is the real tkinter class under pytest."""
        with (
            patch("screen_locker.screen_lock.tk", tk),
            pytest.raises(RuntimeError, match="SAFETY"),
        ):
            _assert_not_under_pytest()

    def test_silent_when_tk_is_mocked(self) -> None:
        """Guard stays silent when tk is already mocked (normal test run)."""
        _assert_not_under_pytest()


class TestScreenLockerInit:
    """Tests for ScreenLocker initialization."""

    def test_init_demo_mode(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Test initialization in demo mode."""
        locker = create_locker(mock_tk, tmp_path, demo_mode=True)

        assert locker.demo_mode is True
        assert locker.lockout_time == 10
        mock_sys_exit.assert_not_called()

    def test_init_production_mode(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Test initialization in production mode."""
        locker = create_locker(mock_tk, tmp_path, demo_mode=False)

        assert locker.demo_mode is False
        assert locker.lockout_time == 1800
        mock_sys_exit.assert_not_called()

    def test_init_exits_if_logged_today(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Test that init exits early if workout logged today."""
        mock_sys_exit.side_effect = SystemExit(0)

        with pytest.raises(SystemExit):
            create_locker(mock_tk, tmp_path, has_logged=True)

        mock_sys_exit.assert_called_once_with(0)


class TestHasLoggedToday:
    """Tests for has_logged_today method."""

    def test_no_log_file(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test when log file doesn't exist."""
        log_file = tmp_path / "workout_log.json"
        locker = create_locker(mock_tk, tmp_path)

        locker.log_file = log_file
        assert locker.has_logged_today() is False

    def test_empty_log_file(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test when log file is empty/invalid JSON."""
        log_file = tmp_path / "workout_log.json"
        log_file.write_text("")

        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        assert locker.has_logged_today() is False

    def test_invalid_json(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test when log file contains invalid JSON."""
        log_file = tmp_path / "workout_log.json"
        log_file.write_text("{invalid json}")

        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        assert locker.has_logged_today() is False

    def test_today_logged(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test when today's workout is logged with valid HMAC."""
        log_file = tmp_path / "workout_log.json"
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        log_file.write_text(
            json.dumps({today: {"workout": "data", "hmac": "valid"}}),
        )

        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        with patch(
            "screen_locker._compliance_predicates.verify_entry_hmac",
            return_value=True,
        ):
            assert locker.has_logged_today() is True

    def test_today_logged_invalid_hmac(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test rejects entry when HMAC verification fails."""
        log_file = tmp_path / "workout_log.json"
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        log_file.write_text(
            json.dumps({today: {"workout": "data", "hmac": "tampered"}}),
        )

        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        with patch(
            "screen_locker._compliance_predicates.verify_entry_hmac",
            return_value=False,
        ):
            assert locker.has_logged_today() is False

    def test_today_unsigned_entry_no_hmac_key(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Accept unsigned entry when HMAC key is unavailable."""
        log_file = tmp_path / "workout_log.json"
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        log_file.write_text(
            json.dumps({today: {"workout": "data"}}),
        )

        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        with (
            patch(
                "screen_locker._compliance_predicates.verify_entry_hmac",
                return_value=False,
            ),
            patch(
                "screen_locker._compliance_predicates.compute_entry_hmac",
                return_value=None,
            ),
        ):
            assert locker.has_logged_today() is True

    def test_today_unsigned_entry_with_hmac_key(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Reject unsigned entry when HMAC key IS available."""
        log_file = tmp_path / "workout_log.json"
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        log_file.write_text(
            json.dumps({today: {"workout": "data"}}),
        )

        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        with (
            patch(
                "screen_locker._compliance_predicates.verify_entry_hmac",
                return_value=False,
            ),
            patch(
                "screen_locker._compliance_predicates.compute_entry_hmac",
                return_value="some-signature",
            ),
        ):
            assert locker.has_logged_today() is False

    def test_other_day_logged(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test when only other days are logged."""
        log_file = tmp_path / "workout_log.json"
        log_file.write_text(json.dumps({"2020-01-01": {"workout": "data"}}))

        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        assert locker.has_logged_today() is False
