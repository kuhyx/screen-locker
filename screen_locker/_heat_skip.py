"""Mixin: heat-skip dialog and log entry for the screen locker."""

from __future__ import annotations

import logging
import tkinter as tk
from typing import TYPE_CHECKING

from gatelock import LockConfig, bind_activate, bind_cancel

from screen_locker._constants import HEAT_SKIP_CITY, HEAT_SKIP_TEMP_THRESHOLD

if TYPE_CHECKING:
    from collections.abc import Callable

_logger = logging.getLogger(__name__)

# Sourced from the shared gatelock LockConfig (unified-design-system) instead
# of a locally-invented token block -- this was the one file in the package
# that already knew centralizing tokens was worth doing; now it points at
# the actual shared source instead of its own unshared copy.
_COLORS = LockConfig()
_FONT = "monospace"


def build_heat_skip_content(
    parent: tk.Misc,
    temp: float,
    *,
    on_skip: Callable[[], None],
    on_decline: Callable[[], None],
) -> tk.Frame:
    """Build the heat-skip screen inside ``parent`` and return its frame.

    Separate from :meth:`HeatSkipMixin._show_heat_skip_dialog` because that
    method owns a fullscreen ``tk.Tk()`` of its own, which
    ``scripts/verify_screen_fits.py`` cannot measure. This is a lock screen
    like any other -- grabbed, undecorated, ``place``-centred, so it clips at
    *both* edges if it ever outgrows the display -- and it has to be in the
    fit check for that reason.
    """
    outer = tk.Frame(parent, bg=_COLORS.bg)
    outer.place(relx=0.5, rely=0.5, anchor="center")

    tk.Label(
        outer,
        text="\u2600  Too hot to workout?",
        font=_COLORS.font("body", bold=True, family=_FONT),
        bg=_COLORS.bg,
        fg=_COLORS.warning,
    ).pack(pady=(0, _COLORS.space("sm")))

    tk.Label(
        outer,
        text=(
            f"{HEAT_SKIP_CITY}: {temp:.0f}\u00b0C"
            f"  (threshold: {HEAT_SKIP_TEMP_THRESHOLD}\u00b0C)"
        ),
        font=_COLORS.font("body", family=_FONT),
        bg=_COLORS.bg,
        fg=_COLORS.muted,
    ).pack(pady=_COLORS.space("xs"))

    tk.Label(
        outer,
        text="Skip today's workout due to extreme heat?",
        font=_COLORS.font("body", family=_FONT),
        bg=_COLORS.bg,
        fg=_COLORS.muted,
    ).pack(pady=(_COLORS.space("xs"), 0))

    btn_frame = tk.Frame(outer, bg=_COLORS.bg)
    btn_frame.pack(pady=_COLORS.space("lg"))

    skip_button = tk.Button(
        btn_frame,
        text="Skip workout",
        command=on_skip,
        bg=_COLORS.warning,
        fg=_COLORS.on_fill,
        activebackground=_COLORS.warning,
        font=_COLORS.font("label", family=_FONT),
        padx=_COLORS.space("md"),
        pady=_COLORS.space("sm"),
        relief="flat",
        **_COLORS.focus_kwargs(),
    )
    skip_button.pack(side="left", padx=_COLORS.space("sm"))

    decline_button = tk.Button(
        btn_frame,
        text="No, I'll workout",
        command=on_decline,
        bg=_COLORS.field_bg,
        fg=_COLORS.fg,
        activebackground=_COLORS.field_bg,
        font=_COLORS.font("label", family=_FONT),
        padx=_COLORS.space("md"),
        pady=_COLORS.space("sm"),
        relief="flat",
        **_COLORS.focus_kwargs(),
    )
    decline_button.pack(side="left", padx=_COLORS.space("sm"))

    # This modal grabs input and sits fullscreen with no window decoration, so
    # the keyboard is the only way out for a pointerless user. It used to
    # focus_force() the root and stop there: nothing was focused, no ring was
    # visible (Tk's default is black on bg), Enter did nothing because Tk binds
    # only <space> on Button, and there was no <Escape>. Default focus goes to
    # the *declining* option, so a blind Return keeps the workout rather than
    # silently skipping it.
    for button in (skip_button, decline_button):
        bind_activate(button)
    decline_button.focus_set()
    return outer


class HeatSkipMixin:
    """Provides _show_heat_skip_dialog and _save_heat_skip_log."""

    def _show_heat_skip_dialog(self, temp: float) -> bool:
        """Show a modal confirmation dialog for skipping due to extreme heat.

        Creates a temporary Tk root (destroyed before the main GateRoot is
        initialised) so this can be called early in the startup flow. Returns
        True if the user confirms the skip, False if they decline.
        """
        result: list[bool] = [False]

        # Use the root itself (not a Toplevel) so we can go fullscreen.
        # This window is destroyed before the main GateRoot is created.
        root = tk.Tk()
        root.title("Extreme Heat")
        root.configure(bg=_COLORS.bg)
        root.attributes("-fullscreen", True)
        root.attributes("-topmost", True)
        root.grab_set()
        root.focus_force()

        def _on_skip() -> None:
            result[0] = True
            root.destroy()

        def _on_no() -> None:
            result[0] = False
            root.destroy()

        build_heat_skip_content(root, temp, on_skip=_on_skip, on_decline=_on_no)
        bind_cancel(root, _on_no)

        root.mainloop()

        return result[0]

    def _save_heat_skip_log(self, temp: float) -> None:
        """Append a heat_skip entry to log.json."""
        self.workout_data = {
            "type": "heat_skip",
            "temperature_celsius": str(round(temp)),
            "city": HEAT_SKIP_CITY,
        }
        self.save_workout_log()
