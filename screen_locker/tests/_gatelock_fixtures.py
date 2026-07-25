"""Keeping gatelock v0.2.0's per-output machinery off the real machine.

``conftest``'s ``_block_real_tk_and_exit`` patches ``tk`` inside
*screen_locker*, which is not enough any more: since v0.2.0 ``LockWindow``
builds one real ``tk.Toplevel`` per live output through *gatelock's* own
``tk``. Over a MagicMock root that sends real tkinter into unbounded mock
recursion, so the suite **hangs** instead of failing -- far harder to
diagnose than an error, and it is what this module exists to prevent.

Re-exported from ``conftest`` rather than defined there so neither file
exceeds the repo's 400-line limit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from gatelock import Output, OutputRect
import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

FAKE_OUTPUTS = (
    Output("DP-0", connected=True, rect=OutputRect(0, 0, 1920, 1080), primary=True),
)
"""One live output by default, so the Tk-screen fallback (which would call
int() on a MagicMock) is never reached."""

TWO_OUTPUTS = (
    Output("DP-0", connected=True, rect=OutputRect(0, 0, 3840, 2160), primary=True),
    Output("HDMI-0", connected=True, rect=OutputRect(3840, 0, 2560, 1440)),
)
"""The real desk. Opt in with the ``dual_output`` fixture for anything
asserting that work fans out across monitors: against ``FAKE_OUTPUTS`` a loop
that only ever touched the primary passes every assertion."""


def _make_toplevel(_parent: object = None, **_kwargs: object) -> MagicMock:
    """A Toplevel stand-in for gatelock's per-output surfaces."""
    window = MagicMock()
    window.winfo_children.return_value = []
    return window


@pytest.fixture(autouse=True)
def _hermetic_gatelock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """Block every path from the lock to the real display or machine.

    The runtime dir is redirected as well, so a test cannot reach the real
    ``$XDG_RUNTIME_DIR`` and stand a *production* locker down through the
    arbiter.
    """
    monkeypatch.setenv("GATELOCK_RUNTIME_DIR", str(tmp_path / "gatelock-runtime"))
    with (
        patch("gatelock._surfaces.tk.Toplevel", side_effect=_make_toplevel),
        patch("gatelock._outputs.RandrBackend.create", return_value=None),
        patch("gatelock._outputs.scan_xrandr", return_value=FAKE_OUTPUTS),
        patch("gatelock._detect._RandrEventSource.start", return_value=False),
    ):
        yield


@pytest.fixture
def dual_output(_hermetic_gatelock: None) -> Iterator[None]:
    """Re-scan as a two-monitor desk, layered over the single-output default.

    Depends on ``_hermetic_gatelock`` so pytest is obliged to apply it
    second; the ``scan_xrandr`` patch here has to be the one that wins.
    """
    with patch("gatelock._outputs.scan_xrandr", return_value=TWO_OUTPUTS):
        yield
