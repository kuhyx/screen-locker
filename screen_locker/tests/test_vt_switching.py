"""Tests for VT switching disable/restore during screen lock."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, call, patch

from python_pkg.screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path

_SETXKBMAP = "/usr/bin/setxkbmap"


class TestVTSwitching:
    """Tests for VT switching disable/restore behaviour."""

    def test_vt_switching_disabled_in_production_mode(
        self,
        mock_tk: MagicMock,
        mock_subprocess_run: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """setxkbmap srvrkeys:none is called when locker starts in production."""
        create_locker(mock_tk, tmp_path, demo_mode=False)

        mock_subprocess_run.assert_called_once_with(
            [_SETXKBMAP, "-option", "srvrkeys:none"],
            check=False,
        )

    def test_vt_switching_not_disabled_in_demo_mode(
        self,
        mock_tk: MagicMock,
        mock_subprocess_run: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """setxkbmap is NOT called in demo mode."""
        create_locker(mock_tk, tmp_path, demo_mode=True)

        mock_subprocess_run.assert_not_called()

    def test_vt_switching_restored_on_close_in_production(
        self,
        mock_tk: MagicMock,
        mock_subprocess_run: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """setxkbmap -option '' is called when close() runs in production."""
        locker = create_locker(mock_tk, tmp_path, demo_mode=False)
        mock_subprocess_run.reset_mock()

        locker.close()

        mock_subprocess_run.assert_called_once_with(
            [_SETXKBMAP, "-option", ""],
            check=False,
        )

    def test_vt_switching_not_restored_in_demo_mode(
        self,
        mock_tk: MagicMock,
        mock_subprocess_run: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """close() does NOT call setxkbmap in demo mode."""
        locker = create_locker(mock_tk, tmp_path, demo_mode=True)
        mock_subprocess_run.reset_mock()

        locker.close()

        mock_subprocess_run.assert_not_called()

    def test_disable_then_restore_are_complementary(
        self,
        mock_tk: MagicMock,
        mock_subprocess_run: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Full lifecycle: disable on init, restore on close in production."""
        locker = create_locker(mock_tk, tmp_path, demo_mode=False)

        assert mock_subprocess_run.call_count == 1
        assert mock_subprocess_run.call_args_list[0] == call(
            [_SETXKBMAP, "-option", "srvrkeys:none"],
            check=False,
        )

        locker.close()

        assert mock_subprocess_run.call_count == 2
        assert mock_subprocess_run.call_args_list[1] == call(
            [_SETXKBMAP, "-option", ""],
            check=False,
        )

    def test_disable_graceful_when_setxkbmap_missing(
        self,
        mock_tk: MagicMock,
        mock_subprocess_run: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """No crash and no subprocess call when setxkbmap is not installed."""
        with patch(
            "python_pkg.screen_locker.screen_lock.shutil.which",
            return_value=None,
        ):
            create_locker(mock_tk, tmp_path, demo_mode=False)

        mock_subprocess_run.assert_not_called()

    def test_restore_graceful_when_setxkbmap_missing(
        self,
        mock_tk: MagicMock,
        mock_subprocess_run: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """No crash and no subprocess call on close when setxkbmap is not installed."""
        locker = create_locker(mock_tk, tmp_path, demo_mode=False)
        mock_subprocess_run.reset_mock()

        with patch(
            "python_pkg.screen_locker.screen_lock.shutil.which",
            return_value=None,
        ):
            locker.close()

        mock_subprocess_run.assert_not_called()
