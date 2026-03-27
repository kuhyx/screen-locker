"""Shared fixtures and helpers for screen_locker tests."""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from python_pkg.screen_locker.screen_lock import ScreenLocker

if TYPE_CHECKING:
    from collections.abc import Generator


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
) -> ScreenLocker:
    """Create a ScreenLocker instance for testing."""
    with (
        patch.object(Path, "resolve", return_value=tmp_path),
        patch.object(ScreenLocker, "has_logged_today", return_value=has_logged),
        patch.object(ScreenLocker, "_start_phone_check"),
    ):
        return ScreenLocker(demo_mode=demo_mode)
