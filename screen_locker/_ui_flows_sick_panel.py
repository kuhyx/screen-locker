"""The "choose lockers…" link: sickdays' KeepPanel, inside the lock window.

The one-tap "I'm sick" button (``_ui_flows_sick``) keeps nothing. This link,
next to it, opens sickdays' embeddable :class:`~sickdays.gui.KeepPanel` so
today can be marked sick with some lockers still on. It is built in-process
on the lock's own surfaces: a separate window would get no input under the
lock's X grab.

The panel covers each surface on a full-size backdrop instead of replacing
the screen under it, so closing it reveals exactly the screen it was opened
from -- a running penalty countdown or phone check is neither restarted nor
skipped. The panel does the write and starts its own background sync; what
the lock does afterwards depends on the pool, not on the entry:

* sick and the workout lock stands down -> the one-tap path's after-effects
  (sick floor, decision, close), without a second mark or push;
* sick but the workout lock kept -> sick floor (20:00 applies on any sick
  day), the lock stays up with a short note;
* cleared, or an unchanged Save -> the panel closes, nothing else.
"""

from __future__ import annotations

import logging
import tkinter as tk
from typing import TYPE_CHECKING

from gatelock import bind_activate
import sickdays
from sickdays.gui import KeepPanel

from screen_locker._sick import stands_down_workout
from screen_locker._surface_group import FrameGroup

if TYPE_CHECKING:
    from collections.abc import Callable

    from gatelock import LockConfig

_logger = logging.getLogger(__name__)

LINK_TEXT = "choose lockers…"
KEPT_NOTE = "Workout lock kept — finish the workout to unlock."


def build_sick_panel(
    parent: tk.Misc,
    colors: LockConfig,
    *,
    on_saved: Callable[[sickdays.SickDay | None], None],
    on_cancel: Callable[[], None],
    paths: sickdays.Paths | None = None,
) -> tk.Frame:
    """Centre today's KeepPanel in ``parent`` and return the frame holding it.

    Separate from the mixin so ``scripts/verify_screen_fits.py`` can measure
    it on a throwaway pool (``paths``) instead of the live one.
    """
    outer = tk.Frame(parent, bg=colors.palette.bg)
    outer.place(relx=0.5, rely=0.5, anchor="center")
    KeepPanel(
        outer, sickdays.today(), on_saved=on_saved, on_cancel=on_cancel, paths=paths
    ).pack()
    return outer


class SickPanelFlowMixin:
    """The keep-aware sick-day panel, layered over the current lock screen."""

    _sick_overlay: FrameGroup | None = None

    def _choose_lockers_link(self, frame: FrameGroup) -> None:
        """Pack the small secondary link that opens the panel into ``frame``."""
        palette = self._colors.palette
        links = frame.child_widgets(
            tk.Button,
            text=LINK_TEXT,
            font=self._colors.font("label"),
            bg=palette.bg,
            fg=palette.muted,
            activebackground=palette.field_bg,
            activeforeground=palette.fg,
            command=self.open_sick_panel,
            cursor="hand2" if self.demo_mode else "",
            relief="flat",
            borderwidth=0,
            padx=self._colors.space("sm"),
            pady=self._colors.space("xs"),
            **self._colors.focus_kwargs(),
        )
        for link in links:
            bind_activate(link)
        links.pack(side="left", padx=self._colors.space("sm"))

    def open_sick_panel(self) -> None:
        """Lay today's KeepPanel over every monitor's surface."""
        overlay = self._new_sick_overlay()
        for backdrop in overlay:
            build_sick_panel(
                backdrop,
                self._colors,
                on_saved=self._on_sick_panel_saved,
                on_cancel=self._close_sick_panel,
            )

    def _new_sick_overlay(self) -> FrameGroup:
        """Replace any open overlay with a fresh full-surface backdrop group."""
        self._close_sick_panel()
        backdrops: list[tk.Frame] = []
        for surface in self.container.surfaces:
            backdrop = tk.Frame(surface.winfo_toplevel(), bg=self._colors.palette.bg)
            backdrop.place(relx=0, rely=0, relwidth=1, relheight=1)
            backdrop.lift()
            backdrops.append(backdrop)
        self._sick_overlay = FrameGroup(backdrops)
        return self._sick_overlay

    def _close_sick_panel(self) -> None:
        """Remove the overlay; the lock screen under it was never touched."""
        if self._sick_overlay is not None:
            self._sick_overlay.destroy()
        self._sick_overlay = None

    def _on_sick_panel_saved(self, entry: sickdays.SickDay | None) -> None:
        """React to the panel's write; the pool is already up to date."""
        self._close_sick_panel()
        if entry is None or not entry.is_sick:
            _logger.warning(
                "Sick panel saved without a sick day (%s); the lock stays as it was",
                "unchanged" if entry is None else "cleared",
            )
            return
        self._raise_sick_floor()
        kept = ", ".join(sorted(entry.keep)) or "nothing"
        if stands_down_workout():
            self._unlock_sick_day(
                f"Marked today sick from the lock screen's keep panel (kept: {kept})."
            )
            return
        _logger.warning("Sick day keeps the workout lock (kept: %s); staying up", kept)
        self._show_kept_note()

    def _show_kept_note(self) -> None:
        """Say the lock stays because the workout locker was kept."""
        box = self._new_sick_overlay().child_frame(bg=self._colors.palette.bg)
        for frame in box:
            frame.place(relx=0.5, rely=0.5, anchor="center")
        box.child_widgets(
            tk.Label,
            text=KEPT_NOTE,
            font=self._colors.font("title", bold=True),
            fg=self._colors.palette.warning,
            bg=self._colors.palette.bg,
        ).pack(pady=self._colors.space("md"))
        self._button(
            box,
            "Back",
            bg=self._colors.palette.accent,
            command=self._close_sick_panel,
            width=12,
        ).pack(pady=self._colors.space("sm"))
