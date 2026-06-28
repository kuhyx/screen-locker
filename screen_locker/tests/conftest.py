"""Shared fixtures and helpers for screen_locker tests.

Safety:
  ``_block_real_tk_and_exit`` (autouse) replaces the **entire** ``tk``
  module reference inside ``screen_lock`` with a MagicMock, replaces
  ``GateRoot`` with a callable returning that same mock root, and stubs
  ``sys.exit``.  This makes it physically impossible for any test to
  create a real Tk root window, go fullscreen, or grab input — even if
  the test forgets to request the explicit ``mock_tk`` fixture.
"""

from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
import tkinter as tk
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from screen_locker.screen_lock import ScreenLocker

if TYPE_CHECKING:
    from collections.abc import Generator, Iterator
    from typing import Literal


# Every module that imports ``tkinter as tk`` and calls it directly. The UI was
# split across these modules, so each ``tk`` reference must be patched — both to
# guarantee no test can touch a real display and so a test holding ``mock_tk``
# sees widgets created on that same mock (not a divergent autouse mock).
_TK_MODULES = (
    "screen_locker.screen_lock",
    "screen_locker._sick_dialog",
    "screen_locker._ui_widgets",
    "screen_locker._window_setup",
)
_VT_SHUTIL = "gatelock._vt.shutil"
_VT_SUBPROCESS = "gatelock._vt.subprocess"


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

    with ExitStack() as stack:
        for module in _TK_MODULES:
            stack.enter_context(patch(f"{module}.tk", mock))
        stack.enter_context(
            patch(
                "screen_locker.screen_lock.GateRoot",
                return_value=mock.Tk.return_value,
            )
        )
        stack.enter_context(patch("screen_locker.screen_lock.sys.exit"))
        yield


@pytest.fixture(autouse=True)
def mock_subprocess_run() -> Generator[MagicMock]:
    """Block real subprocess calls (e.g. setxkbmap) for every test.

    Also exposed as a named fixture so individual tests can assert
    on the calls made (e.g. VT switching tests).

    ``shutil.which`` is mocked to return a stable fake path so tests work
    regardless of whether setxkbmap is installed on the host machine.
    """
    with (
        patch(f"{_VT_SHUTIL}.which", return_value="/usr/bin/setxkbmap"),
        patch(f"{_VT_SUBPROCESS}.run") as mock,
    ):
        yield mock


@pytest.fixture(autouse=True)
def _block_real_network() -> Iterator[None]:
    """Block real subnet probes for every test.

    ``_scan_for_http_server`` / ``_try_wireless_reconnect`` open real TCP
    sockets to scan the LAN; without this an unmocked ``_verify_phone_workout``
    would actually reach the phone over the network (flaky, environment-coupled).
    Defaults ``create_connection`` to refuse — tests needing a successful probe
    patch it locally, which takes precedence inside the test body.
    """
    with patch(
        "screen_locker._phone_verification.socket.create_connection",
        side_effect=OSError("network blocked in tests"),
    ):
        yield


@pytest.fixture(autouse=True)
def _isolate_sick_history(tmp_path: Path) -> Iterator[None]:
    """Redirect SICK_HISTORY_FILE to tmp_path so tests cannot touch real state."""
    target = tmp_path / "sick_history.json"
    with (
        patch(
            "screen_locker._sick_tracker.SICK_HISTORY_FILE",
            target,
        ),
        patch(
            "screen_locker._constants.SICK_HISTORY_FILE",
            target,
        ),
    ):
        yield


@pytest.fixture(autouse=True)
def _isolate_scheduled_skips(tmp_path: Path) -> Iterator[None]:
    """Redirect SCHEDULED_SKIPS_FILE to tmp_path so tests use a clean file."""
    target = tmp_path / "scheduled_skips.json"
    with patch(
        "screen_locker._log_mixin.SCHEDULED_SKIPS_FILE",
        target,
    ):
        yield


@pytest.fixture(autouse=True)
def _mock_weekly_logic() -> Iterator[None]:
    """Default to Fri-Mon enforcement with weekly minimum not yet met.

    Without this, tests that run on a Tue/Wed/Thu would hit the relaxed-day
    branch instead of the full-lock path that existing tests expect.
    Setting has_weekly_minimum=False ensures the full lock is shown
    (weekly quota not reached → enforce).
    """
    with (
        patch(
            "screen_locker.screen_lock.is_relaxed_day",
            return_value=False,
        ),
        patch(
            "screen_locker.screen_lock.has_weekly_minimum",
            return_value=False,
        ),
    ):
        yield


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
        patch.object(ScreenLocker, "_start_relaxed_day_flow"),
        patch.object(ScreenLocker, "_start_verify_workout_check"),
        patch.object(ScreenLocker, "_scan_and_fill_week_runnerup", return_value=0),
    ):
        return ScreenLocker(
            demo_mode=demo_mode,
            verify_only=verify_only,
        )


def create_locker_relaxed_day(
    _mock_tk: MagicMock,
    tmp_path: Path,
    *,
    demo_mode: bool = True,
    has_logged: bool = False,
) -> ScreenLocker:
    """Create a ScreenLocker in relaxed-day mode (Tue/Wed/Thu).

    ``is_relaxed_day`` returns True so ``_relaxed_day_mode`` is set and
    ``_start_relaxed_day_flow`` is called instead of ``_start_phone_check``.
    The autouse ``_mock_weekly_logic`` fixture is overridden here.
    """
    with (
        patch.object(Path, "resolve", return_value=tmp_path),
        patch.object(ScreenLocker, "has_logged_today", return_value=has_logged),
        patch.object(ScreenLocker, "_is_sick_day_log", return_value=False),
        patch.object(ScreenLocker, "_is_early_bird_log", return_value=False),
        patch.object(ScreenLocker, "_is_early_bird_time", return_value=False),
        patch.object(ScreenLocker, "_try_auto_upgrade_early_bird", return_value=False),
        patch("screen_locker.screen_lock.is_relaxed_day", return_value=True),
        patch(
            "screen_locker.screen_lock.has_weekly_minimum",
            return_value=False,
        ),
        patch.object(ScreenLocker, "_start_phone_check"),
        patch.object(ScreenLocker, "_start_relaxed_day_flow"),
        patch.object(ScreenLocker, "_start_verify_workout_check"),
    ):
        return ScreenLocker(demo_mode=demo_mode)


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
        patch.object(ScreenLocker, "_start_relaxed_day_flow"),
        patch.object(ScreenLocker, "_start_verify_workout_check"),
    ):
        return ScreenLocker(demo_mode=demo_mode)
