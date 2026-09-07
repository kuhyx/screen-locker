"""Tests for scheduled skip date feature in screen_lock.py."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import freedays
import pytest

from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path
    from unittest.mock import MagicMock

    from screen_locker.screen_lock import ScreenLocker


class TestIsScheduledSkipToday:
    """Tests for ScreenLocker._is_scheduled_skip_today."""

    def _make_locker(self, mock_tk: MagicMock, tmp_path: Path) -> ScreenLocker:
        return create_locker(mock_tk, tmp_path)

    def test_returns_false_when_pool_empty(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Returns False when nothing has ever been marked."""
        locker = self._make_locker(mock_tk, tmp_path)
        assert locker._is_scheduled_skip_today() is False

    def test_returns_true_when_today_marked(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Returns True when today is in the shared free-day pool."""
        locker = self._make_locker(mock_tk, tmp_path)
        freedays.mark(
            freedays.today(), paths=freedays.Paths.under(tmp_path / "freedays")
        )
        assert locker._is_scheduled_skip_today() is True

    def test_returns_false_when_only_another_day_marked(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A pool holding some other date does not free today."""
        locker = self._make_locker(mock_tk, tmp_path)
        freedays.mark(
            date(2026, 12, 24),
            paths=freedays.Paths.under(tmp_path / "freedays"),
        )
        assert locker._is_scheduled_skip_today() is False

    def test_returns_false_on_corrupt_pool(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Fail closed: an unparsable pool locks normally rather than opening."""
        locker = self._make_locker(mock_tk, tmp_path)
        pool = tmp_path / "freedays"
        pool.mkdir(exist_ok=True)
        (pool / "free_days.json").write_text("{not valid json}")
        assert locker._is_scheduled_skip_today() is False

    def test_returns_false_when_the_day_was_released(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Giving a day back re-arms the lock for it."""
        locker = self._make_locker(mock_tk, tmp_path)
        paths = freedays.Paths.under(tmp_path / "freedays")
        freedays.mark(freedays.today(), paths=paths)
        assert locker._is_scheduled_skip_today() is True
        freedays.release(freedays.today(), paths=paths)
        assert locker._is_scheduled_skip_today() is False


class TestScheduledSkipEarlyExit:
    """Tests for _check_non_verify_exits behaviour with scheduled skips."""

    @staticmethod
    def _write_today_skip(tmp_path: Path) -> None:
        """Mark today free in the shared pool the conftest redirected here."""
        freedays.mark(
            freedays.today(), paths=freedays.Paths.under(tmp_path / "freedays")
        )

    def test_exits_on_scheduled_skip_day(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Screen locker calls sys.exit(0) when today is a scheduled skip."""
        self._write_today_skip(tmp_path)
        mock_sys_exit.side_effect = SystemExit(0)

        with pytest.raises(SystemExit):
            create_locker(mock_tk, tmp_path)

        mock_sys_exit.assert_called_once_with(0)

    def test_does_not_exit_when_not_scheduled_skip(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Screen locker proceeds normally when today is not a scheduled skip."""
        # No file written — _is_scheduled_skip_today returns False
        locker = create_locker(mock_tk, tmp_path)

        mock_sys_exit.assert_not_called()
        assert locker is not None

    def test_scheduled_skip_takes_precedence_over_has_logged(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Scheduled skip exits before has_logged or other checks run."""
        self._write_today_skip(tmp_path)
        mock_sys_exit.side_effect = SystemExit(0)

        with pytest.raises(SystemExit):
            create_locker(mock_tk, tmp_path, has_logged=False)

        mock_sys_exit.assert_called_once_with(0)

    def test_verify_only_mode_ignores_scheduled_skip(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """verify_only mode does not consult scheduled skips."""
        self._write_today_skip(tmp_path)

        # verify_only exits because no sick day log, not because of scheduled skip
        create_locker(
            mock_tk,
            tmp_path,
            verify_only=True,
            is_sick_day_log=False,
        )

        mock_sys_exit.assert_called_once_with(0)
