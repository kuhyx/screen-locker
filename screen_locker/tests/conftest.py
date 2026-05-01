"""Shared fixtures and helpers for screen_locker tests.

Safety:
  ``_block_real_tk_and_exit`` (autouse) replaces the **entire** ``tk``
  module reference inside ``screen_lock`` with a MagicMock and stubs
  ``sys.exit``.  This makes it physically impossible for any test to
  create a real Tk root window, go fullscreen, or grab input — even if
  the test forgets to request the explicit ``mock_tk`` fixture.
"""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from python_pkg.screen_locker.screen_lock import ScreenLocker

if TYPE_CHECKING:
    from collections.abc import Generator, Iterator
    from typing import Literal


def _make_mock_tk() -> MagicMock:
    """Build a MagicMock that stands in for the ``tkinter`` module."""
    mock = MagicMock()
    mock_root = MagicMock()
    mock_root.winfo_screenwidth.return_value = 1920
    mock_root.winfo_screenheight.return_value = 1080
    mock.Tk.return_value = mock_root

    mock_frame = MagicMock()
    mock_frame.winfo_children.return_value = []
    mock.Frame.return_value = mock_frame

    # Keep real TclError so ``except tk.TclError`` still works.
    mock.TclError = tk.TclError
    return mock


@pytest.fixture(autouse=True)
def _block_real_tk_and_exit() -> Iterator[None]:
    """Replace the whole ``tk`` module and ``sys.exit`` for every test.

    Patching the entire module (not just ``tk.Tk``) ensures that
    **nothing** in tkinter can touch the real display server.
    """
    mock = _make_mock_tk()

    with (
        patch("python_pkg.screen_locker.screen_lock.tk", mock),
        patch("python_pkg.screen_locker.screen_lock.sys.exit"),
    ):
        yield


@pytest.fixture
def mock_tk() -> Generator[MagicMock]:
    """Mock tkinter module for testing without display."""
    with patch("python_pkg.screen_locker.screen_lock.tk") as mock:
        # Set up Tk root mock
        mock_root = MagicMock()
        mock_root.winfo_screenwidth.return_value = 1920
        mock_root.winfo_screenheight.return_value = 1080
        mock.Tk.return_value = mock_root

        # Set up Frame mock
        mock_frame = MagicMock()
        mock_frame.winfo_children.return_value = []
        mock.Frame.return_value = mock_frame

        # Set up TclError as actual exception class
        mock.TclError = tk.TclError

        yield mock


@pytest.fixture
def mock_sys_exit() -> Generator[MagicMock]:
    """Mock sys.exit to prevent test termination."""
    with patch("python_pkg.screen_locker.screen_lock.sys.exit") as mock:
        yield mock


@pytest.fixture
def _mock_sys_exit(mock_sys_exit: MagicMock) -> MagicMock:
    """Alias for mock_sys_exit when the return value is unused."""
    return mock_sys_exit


@pytest.fixture
def temp_log_file(tmp_path: Path) -> Path:
    """Create a temporary log file path."""
    return tmp_path / "workout_log.json"


def create_locker(
    _mock_tk: MagicMock,
    tmp_path: Path,
    *,
    demo_mode: bool = True,
    has_logged: bool = False,
    verify_only: bool = False,
    is_sick_day_log: bool = False,
) -> ScreenLocker:
    """Create a ScreenLocker instance with early bird paths disabled."""
    with (
        patch.object(Path, "resolve", return_value=tmp_path),
        patch.object(ScreenLocker, "has_logged_today", return_value=has_logged),
        patch.object(
            ScreenLocker,
            "_is_sick_day_log",
            return_value=is_sick_day_log,
        ),
        patch.object(ScreenLocker, "_is_early_bird_log", return_value=False),
        patch.object(ScreenLocker, "_is_early_bird_time", return_value=False),
        patch.object(
            ScreenLocker,
            "_try_auto_upgrade_early_bird",
            return_value=False,
        ),
        patch.object(ScreenLocker, "_start_phone_check"),
        patch.object(ScreenLocker, "_start_verify_workout_check"),
    ):
        return ScreenLocker(
            demo_mode=demo_mode,
            verify_only=verify_only,
        )


def create_locker_early_bird(
    _mock_tk: MagicMock,
    tmp_path: Path,
    *,
    state: Literal["none", "log_active", "log_expired"] = "none",
    has_logged: bool = False,
    demo_mode: bool = True,
) -> ScreenLocker:
    """Create a ScreenLocker configured for early bird path testing.

    Args:
        state: One of:
            - "none": outside early bird window, no early bird log.
            - "log_active": early bird log exists, still in window.
            - "log_expired": early bird log exists, past 8:30 AM.
        has_logged: Return value for has_logged_today mock.
        demo_mode: Passed to ScreenLocker constructor.
    """
    is_early_bird_log = state in ("log_active", "log_expired")
    is_early_bird_time = state == "log_active"
    with (
        patch.object(Path, "resolve", return_value=tmp_path),
        patch.object(ScreenLocker, "has_logged_today", return_value=has_logged),
        patch.object(ScreenLocker, "_is_sick_day_log", return_value=False),
        patch.object(
            ScreenLocker, "_is_early_bird_log", return_value=is_early_bird_log
        ),
        patch.object(
            ScreenLocker, "_is_early_bird_time", return_value=is_early_bird_time
        ),
        patch.object(ScreenLocker, "_try_auto_upgrade_early_bird", return_value=False),
        patch.object(ScreenLocker, "_start_phone_check"),
        patch.object(ScreenLocker, "_start_verify_workout_check"),
    ):
        return ScreenLocker(demo_mode=demo_mode)
