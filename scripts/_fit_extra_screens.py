"""Lock screens the fit check measures through their own builders.

Split out of ``verify_screen_fits`` for the 250-line cap. These screens are
not painted by a ``ScreenHost`` flow: heat-skip owns a fullscreen ``tk.Tk()``
of its own in production, and the "choose lockers" panel is sickdays'
KeepPanel laid over the lock rather than a repaint of it.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
from typing import TYPE_CHECKING

from gatelock import LockConfig
import sickdays

from screen_locker._heat_skip import build_heat_skip_content
from screen_locker._ui_flows_sick_panel import build_sick_panel

if TYPE_CHECKING:
    import tkinter as tk

    from gatelock import ScrollableSurface


def _build_heat_skip(surface: ScrollableSurface) -> tk.Misc:
    """Paint the heat-skip screen and return the frame to measure.

    Built through its extracted content builder because in production it owns
    a fullscreen ``tk.Tk()`` of its own, which this harness cannot measure.
    """
    return build_heat_skip_content(
        surface.content, 34.0, on_skip=lambda: None, on_decline=lambda: None
    )


def _build_sick_panel(surface: ScrollableSurface) -> tk.Misc:
    """Paint the "choose lockers" panel on a throwaway pool and return it.

    Today is marked sick there first, because that variant is the tallest
    (Save + Clear + Cancel) and because a pool that does not exist keeps the
    measurement independent of the live sick-day and free-day pools. The panel
    reads the pool once, while it is built, so the directory can go after.
    """
    with tempfile.TemporaryDirectory(prefix="fit-sickdays-") as tmp:
        pool = sickdays.Paths.under(Path(tmp))
        sickdays.add_sick_day(sickdays.today(), is_free=lambda _day: False, paths=pool)
        return build_sick_panel(
            surface.content,
            LockConfig(),
            on_saved=lambda _entry: None,
            on_cancel=lambda: None,
            paths=pool,
        )


# Screens built without a ScreenHost, measured through their own builder.
EXTRA_SCREENS: tuple[tuple[str, object], ...] = (
    ("heat-skip", _build_heat_skip),
    ("sick-keep-panel", _build_sick_panel),
)
