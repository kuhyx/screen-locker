"""The tkinter mock and the list of modules it must be patched into.

Split out of ``conftest.py`` to keep every file under the 250-line cap.

Only this scaffolding moved: every ``autouse`` fixture stays in ``conftest.py``,
because pytest collects autouse fixtures from conftest only -- one moved here
would simply stop running, and the suite would still pass while the guard it
provides was gone.

When a new module imports ``tkinter as tk`` and calls it, add it to
``_TK_MODULES`` below or its widgets are built on a real display.
"""

from __future__ import annotations

import tkinter as tk
from unittest.mock import MagicMock

# Every module that imports ``tkinter as tk`` and calls it directly. The UI is
# split across these, so each ``tk`` must be patched — so no test touches a real
# display and a ``mock_tk`` holder sees widgets made on that same mock.
_TK_MODULES = (
    "screen_locker.screen_lock",
    "screen_locker._sick_dialog",
    "screen_locker._manual_workout_dialog",
    "screen_locker._manual_workout_sport_fields",
    "screen_locker._manual_workout_widgets",
    "screen_locker._ui_form_fields",
    "screen_locker._ui_widgets",
    "screen_locker._window_setup",
    "screen_locker.status_view",
    "screen_locker._heat_skip",
    "screen_locker._surface_group",
    # The scroll viewport the lock surfaces are built from lives in gatelock
    # and imports tkinter independently, so it needs the same mock -- otherwise
    # container.first is a *real* tk.Frame whose winfo_children() cannot be
    # stubbed, and every surface assertion breaks.
    "gatelock._scrollable",
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
