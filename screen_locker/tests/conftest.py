"""Shared fixtures and helpers for screen_locker tests.

Safety:
  ``_block_real_tk_and_exit`` (autouse) replaces the **entire** ``tk`` module
  reference inside ``screen_lock`` with a MagicMock, replaces ``GateRoot``
  with a callable returning that same mock root, and stubs ``sys.exit`` — no
  test can create a real Tk root, go fullscreen, or grab input, even one
  that forgets to request the explicit ``mock_tk`` fixture.
"""

from __future__ import annotations

from contextlib import ExitStack
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from screen_locker.tests._gatelock_fixtures import (
    FAKE_OUTPUTS,
    TWO_OUTPUTS,
    _hermetic_gatelock,
    dual_output,
)
from screen_locker.tests._isolated_state import ISOLATED_STATE
from screen_locker.tests._locker_factories import (
    _make_locker,
    create_locker,
    create_locker_early_bird,
    create_locker_relaxed_day,
)
from screen_locker.tests._opt_in_fixtures import (
    _mock_sys_exit,
    mock_sys_exit,
    mock_tk,
    temp_log_file,
)
from screen_locker.tests._tk_mocks import (
    _TK_MODULES,
    _VT_SHUTIL,
    _VT_SUBPROCESS,
    _make_mock_tk,
)

# Re-exported so pytest still resolves these by name: a fixture defined in a
# sibling module is only visible to tests once conftest imports it. __all__
# keeps ruff from pruning them as unused.
__all__ = [
    "FAKE_OUTPUTS",
    "TWO_OUTPUTS",
    "_hermetic_gatelock",
    "_make_locker",
    "_mock_sys_exit",
    "create_locker",
    "create_locker_early_bird",
    "create_locker_relaxed_day",
    "dual_output",
    "mock_sys_exit",
    "mock_tk",
    "temp_log_file",
]

if TYPE_CHECKING:
    from collections.abc import Generator, Iterator


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
        # The startup early-exit checks moved to _startup_checks; sys.exit is
        # bound there now, so it needs blocking separately.
        stack.enter_context(patch("screen_locker._startup_checks.sys.exit"))
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
    """Block real subnet probes and wttr.in calls for every test.

    Otherwise phone verification / StatusWindow's temperature fetch would
    reach the real network. Tests needing a real probe patch it locally.
    """
    targets = (
        # The subnet probes moved out of _phone_verification when it was split;
        # both new homes must be blocked or a test reaches the real network.
        "screen_locker._adb_transport.socket.create_connection",
        "screen_locker._http_workout_fetch.socket.create_connection",
        "screen_locker._temperature.urllib.request.urlopen",
    )
    with ExitStack() as stack:
        for target in targets:
            stack.enter_context(patch(target, side_effect=OSError("blocked")))
        yield


@pytest.fixture(autouse=True)
def _isolate_state_files(tmp_path: Path) -> Iterator[None]:
    """Redirect every on-disk state path to tmp_path for every test.

    Stays in conftest.py and stays autouse: pytest only applies autouse
    fixtures declared here, so moving this to a sibling module would leave
    tests writing to the user's real state files while still passing. The
    table itself (ISOLATED_STATE) has no such constraint -- see
    _isolated_state.py.
    """
    with ExitStack() as stack:
        for filename, bindings in ISOLATED_STATE:
            target = tmp_path / filename
            for binding in bindings:
                stack.enter_context(patch(f"screen_locker.{binding}", target))
        yield


@pytest.fixture(autouse=True)
def _isolate_shutdown_base(tmp_path: Path) -> Iterator[None]:
    """Redirect SHUTDOWN_BASE_FILE to tmp_path so tests cannot touch real state.

    Pre-seeded with today's date so reset_to_base_if_new_day() is a no-op by
    default (matching the real file's steady state) -- tests that want to
    exercise the actual reset path patch reset_to_base_if_new_day directly,
    same as the rest of the suite already does.
    """
    target = tmp_path / "shutdown_base.json"
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    target.write_text(
        json.dumps(
            {"base_mon_wed_hour": 21, "base_thu_sun_hour": 21, "last_reset_date": today}
        )
    )
    with (
        patch("screen_locker._constants.SHUTDOWN_BASE_FILE", target),
        patch("screen_locker._startup_checks.SHUTDOWN_BASE_FILE", target),
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
            "screen_locker._startup_checks.is_relaxed_day",
            return_value=False,
        ),
        patch(
            "screen_locker._startup_checks.has_weekly_minimum",
            return_value=False,
        ),
    ):
        yield


@pytest.fixture(autouse=True)
def _no_real_firebase_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the Firebase config at a path that does not exist.

    ``remote_client`` reads ``crdt_sync.CONFIG_FILE`` to decide whether to
    build a Firebase-primary mirror. On a developer machine that file *does*
    exist, so without this the sync tests would reach the real database and
    assert against live data instead of their own fakes. Tests that want the
    Firebase path point it back at a file they control.
    """
    # CONFIG_FILE is read by remote_client, which lives in _sync_client since
    # _workout_sync was split. Patching the old module would leave the real
    # config in play and the sync tests would assert against live data.
    from screen_locker import _sync_client

    monkeypatch.setattr(_sync_client, "CONFIG_FILE", Path("/nonexistent/firebase.json"))
