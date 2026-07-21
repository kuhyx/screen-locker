"""Mixin: heat-skip dialog and log entry for the screen locker."""

from __future__ import annotations

import logging
import tkinter as tk

from gatelock import LockConfig

from screen_locker._constants import HEAT_SKIP_CITY, HEAT_SKIP_TEMP_THRESHOLD

_logger = logging.getLogger(__name__)

# Sourced from the shared gatelock LockConfig (unified-design-system) instead
# of a locally-invented token block -- this was the one file in the package
# that already knew centralizing tokens was worth doing; now it points at
# the actual shared source instead of its own unshared copy.
_COLORS = LockConfig()
_FONT = "monospace"


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

        # Content centred on the fullscreen canvas
        outer = tk.Frame(root, bg=_COLORS.bg)
        outer.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(
            outer,
            text="☀  Too hot to workout?",
            font=(_FONT, 18, "bold"),
            bg=_COLORS.bg,
            fg=_COLORS.warning,
        ).pack(pady=(0, 10))

        tk.Label(
            outer,
            text=(
                f"{HEAT_SKIP_CITY}: {temp:.0f}°C"
                f"  (threshold: {HEAT_SKIP_TEMP_THRESHOLD}°C)"
            ),
            font=(_FONT, 16),
            bg=_COLORS.bg,
            fg=_COLORS.muted,
        ).pack(pady=6)

        tk.Label(
            outer,
            text="Skip today's workout due to extreme heat?",
            font=(_FONT, 16),
            bg=_COLORS.bg,
            fg=_COLORS.muted,
        ).pack(pady=(6, 0))

        btn_frame = tk.Frame(outer, bg=_COLORS.bg)
        btn_frame.pack(pady=28)

        def _on_skip() -> None:
            result[0] = True
            root.destroy()

        def _on_no() -> None:
            result[0] = False
            root.destroy()

        tk.Button(
            btn_frame,
            text="Skip workout",
            command=_on_skip,
            bg=_COLORS.warning,
            fg=_COLORS.on_fill,
            activebackground=_COLORS.warning,
            font=(_FONT, 14),
            padx=16,
            pady=8,
            relief="flat",
        ).pack(side="left", padx=12)

        tk.Button(
            btn_frame,
            text="No, I'll workout",
            command=_on_no,
            bg=_COLORS.field_bg,
            fg=_COLORS.fg,
            activebackground=_COLORS.field_bg,
            font=(_FONT, 14),
            padx=16,
            pady=8,
            relief="flat",
        ).pack(side="left", padx=12)

        root.mainloop()

        return result[0]

    def _save_heat_skip_log(self, temp: float) -> None:
        """Append a heat_skip entry to workout_log.json."""
        self.workout_data = {
            "type": "heat_skip",
            "temperature_celsius": str(round(temp)),
            "city": HEAT_SKIP_CITY,
        }
        self.save_workout_log()
