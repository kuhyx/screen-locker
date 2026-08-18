"""Opt-in (non-autouse) fixtures for the screen_locker tests.

Split out of ``conftest.py`` to keep every file under the 250-line cap. These
are re-imported there, which is what keeps pytest discovering them by name --
a fixture is only visible to tests if it is reachable from ``conftest.py``.

Only fixtures a test must *request* live here. Every ``autouse`` fixture stays
in ``conftest.py``: pytest applies autouse fixtures from conftest only, so one
moved here would silently stop running and take its safety guard with it.
"""

from __future__ import annotations

from contextlib import ExitStack
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from screen_locker.tests._tk_mocks import _TK_MODULES, _make_mock_tk

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path


@pytest.fixture
def mock_tk() -> Generator[MagicMock]:
    """Mock the ``tkinter`` module across every UI module for display-free tests.

    Patches the same single mock into all ``_TK_MODULES`` so assertions on
    ``mock_tk.Button`` capture widgets created by any of the split UI mixins
    (``_ui_widgets``, ``_sick_dialog``, ...), not just ``screen_lock``.
    """
    mock = _make_mock_tk()
    with ExitStack() as stack:
        for module in _TK_MODULES:
            stack.enter_context(patch(f"{module}.tk", mock))
        stack.enter_context(
            patch(
                "screen_locker.screen_lock.GateRoot",
                return_value=mock.Tk.return_value,
            )
        )
        yield mock


@pytest.fixture
def mock_sys_exit() -> Generator[MagicMock]:
    """Mock sys.exit to prevent test termination."""
    with patch("screen_locker.screen_lock.sys.exit") as mock:
        yield mock


@pytest.fixture
def _mock_sys_exit(mock_sys_exit: MagicMock) -> MagicMock:
    """Alias for mock_sys_exit when the return value is unused."""
    return mock_sys_exit


@pytest.fixture
def temp_log_file(tmp_path: Path) -> Path:
    """Create a temporary log file path."""
    return tmp_path / "log.json"
