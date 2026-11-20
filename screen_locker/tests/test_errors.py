"""screen-locker's error reporting: installed once, into the shared spool."""

from __future__ import annotations

import contextlib
import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker import _cli, _errors, screen_lock
from screen_locker.screen_lock import ScreenLocker
from screen_locker.tests._locker_factories import create_locker

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_install_keeps_the_reporter_and_writes_the_spool(tmp_path: Path) -> None:
    """The CLI's install names this app and its repo in every report."""
    rep = _errors.install()
    assert _errors.SLOT.reporter is rep
    assert rep.app == "screen-locker"
    rep.report("uncaught.python", ValueError("deliberate"))
    line = (tmp_path / "app-errors-spool" / "screen-locker.jsonl").read_text()
    entry = json.loads(line)
    assert entry["repo"] == "kuhyx/screen-locker"
    assert entry["error"] == "ValueError: deliberate"


def test_cli_installs_the_reporter_before_any_mode() -> None:
    """Every mode, headless ones included, runs with errors hooked."""
    with (
        patch.object(_cli, "run_status", side_effect=SystemExit(0)),
        patch.object(_cli, "_headless_locker"),
        contextlib.suppress(SystemExit),
    ):
        _cli.main(ScreenLocker, ["screen_lock.py", "--status"])
    assert _errors.SLOT.reporter is not None


def test_lock_window_watches_stalls_once_installed(
    monkeypatch: pytest.MonkeyPatch, mock_tk: MagicMock, tmp_path: Path
) -> None:
    """A lock window built after install reports its own freezes.

    The watch arms only once the event loop is pumping: building the window
    (xrandr scan, setxkbmap, surfaces, grab) runs before ``mainloop`` and
    nothing is on screen to freeze yet, so arming it in ``__init__`` reported
    the build as a 1.5 s ``tk.mainloop`` stall (screen-locker:c890f31a21).
    """
    watch = MagicMock()
    monkeypatch.setattr(screen_lock, "watch_stalls", watch)
    monkeypatch.setattr(_errors.SLOT, "reporter", MagicMock())
    locker = create_locker(mock_tk, tmp_path)
    watch.assert_not_called()
    locker._lock = None
    locker.run()
    (arm,) = locker.root.after_idle.call_args.args
    watch.assert_not_called()
    arm()
    watch.assert_called_once_with(locker.root, _errors.SLOT.reporter)
    locker.root.mainloop.assert_called_once()


def test_lock_window_skips_the_watch_without_install(
    monkeypatch: pytest.MonkeyPatch, mock_tk: MagicMock, tmp_path: Path
) -> None:
    """Tests and library callers that never installed get no watch."""
    watch = MagicMock()
    monkeypatch.setattr(screen_lock, "watch_stalls", watch)
    locker = create_locker(mock_tk, tmp_path)
    locker._lock = None
    locker.run()
    locker.root.after_idle.assert_not_called()
    watch.assert_not_called()
