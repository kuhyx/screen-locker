"""Tests for early bird carrot feature in screen locker."""

from __future__ import annotations

from typing import TYPE_CHECKING
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
