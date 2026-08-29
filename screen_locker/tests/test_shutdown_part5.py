"""Tests for shutdown schedule adjustment coverage gaps (part 2)."""

from __future__ import annotations

from datetime import UTC
import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestSickModeUsedToday:
    """Tests for _sick_mode_used_today method."""

    def test_returns_false_when_no_file(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns False when state file doesn't exist."""
        locker = create_locker(mock_tk, tmp_path)
        mock_file = MagicMock()
        mock_file.exists.return_value = False
        with patch(
            "screen_locker._shutdown_sick_state.SICK_DAY_STATE_FILE",
            mock_file,
        ):
            assert locker._sick_mode_used_today() is False

    def test_returns_true_when_used_today(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns True when state matches today."""
        locker = create_locker(mock_tk, tmp_path)
        state_file = tmp_path / "state.json"
        with patch(
            "screen_locker._shutdown_sick_state.SICK_DAY_STATE_FILE",
            state_file,
        ):
            from datetime import datetime

            today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
            state_file.write_text(json.dumps({"date": today}))
            assert locker._sick_mode_used_today() is True

    def test_returns_false_when_different_date(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns False when state is from different date."""
        locker = create_locker(mock_tk, tmp_path)
        state_file = tmp_path / "state.json"
        with patch(
            "screen_locker._shutdown_sick_state.SICK_DAY_STATE_FILE",
            state_file,
        ):
            state_file.write_text(json.dumps({"date": "2020-01-01"}))
            assert locker._sick_mode_used_today() is False

    def test_returns_false_on_json_error(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns False on JSONDecodeError."""
        locker = create_locker(mock_tk, tmp_path)
        state_file = tmp_path / "state.json"
        with patch(
            "screen_locker._shutdown_sick_state.SICK_DAY_STATE_FILE",
            state_file,
        ):
            state_file.write_text("not json{{{")
            assert locker._sick_mode_used_today() is False
