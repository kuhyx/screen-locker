"""The early-bird window is the wake-alarm morning-session carrot."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker._morning_session import MorningSkip
from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path

_SKIP = MorningSkip(outcome="completed", exempt_until=datetime(2099, 1, 1).astimezone())


class TestIsEarlyBirdTime:
    """``_is_early_bird_time`` is the carrot verdict, kept for the skip detail."""

    def test_open_while_the_carrot_is_in_force(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        with patch(
            "screen_locker._early_bird.morning_skip_today", return_value=_SKIP
        ) as read:
            assert locker._is_early_bird_time() is True
        read.assert_called_once_with(wait=True)
        assert locker._morning_skip == _SKIP

    def test_shut_without_a_carrot(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        with patch("screen_locker._early_bird.morning_skip_today", return_value=None):
            assert locker._is_early_bird_time() is False
        assert locker._morning_skip is None

    def test_no_wall_clock_is_consulted(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """The 05:00-08:30 clock is gone: 07:00 with a carrot is open, 06:00 without is shut."""
        locker = create_locker(mock_tk, tmp_path)
        assert not hasattr(locker, "_get_local_time_minutes")
        with patch("screen_locker._early_bird.morning_skip_today", return_value=None):
            assert locker._is_early_bird_time() is False
