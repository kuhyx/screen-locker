#!/usr/bin/env python3
"""Screen locker with workout verification for Arch Linux / i3wm.

Requires user to log their workout to unlock the screen.
"""

from __future__ import annotations

import contextlib
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sys
import tkinter as tk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from concurrent.futures import Future

from python_pkg.screen_locker._constants import (
    MAX_DISTANCE_KM,
    MAX_PACE_MIN_PER_KM,
    MAX_REPS,
    MAX_SETS,
    MAX_TIME_MINUTES,
    MAX_WEIGHT_KG,
    MIN_EXERCISE_NAME_LEN,
    PHONE_PENALTY_DELAY_DEMO,
    PHONE_PENALTY_DELAY_PRODUCTION,
    SICK_LOCKOUT_SECONDS,
    STRONGLIFTS_DB_REMOTE,
    SUBMIT_DELAY_DEMO,
    SUBMIT_DELAY_PRODUCTION,
)

__all__ = [
    "MAX_DISTANCE_KM",
    "MAX_PACE_MIN_PER_KM",
    "MAX_REPS",
    "MAX_SETS",
    "MAX_TIME_MINUTES",
    "MAX_WEIGHT_KG",
    "MIN_EXERCISE_NAME_LEN",
    "PHONE_PENALTY_DELAY_DEMO",
    "PHONE_PENALTY_DELAY_PRODUCTION",
    "SICK_LOCKOUT_SECONDS",
    "STRONGLIFTS_DB_REMOTE",
    "SUBMIT_DELAY_DEMO",
    "SUBMIT_DELAY_PRODUCTION",
    "ScreenLocker",
]
from python_pkg.screen_locker._phone_verification import PhoneVerificationMixin
from python_pkg.screen_locker._shutdown import ShutdownMixin
from python_pkg.screen_locker._ui_flows import UIFlowsMixin
from python_pkg.screen_locker._workout_forms import WorkoutFormsMixin

_logger = logging.getLogger(__name__)


class ScreenLocker(
    ShutdownMixin,
    PhoneVerificationMixin,
    WorkoutFormsMixin,
    UIFlowsMixin,
):
    """Screen locker that requires workout logging to unlock."""

    def __init__(self, *, demo_mode: bool = True) -> None:
        """Initialize screen locker with optional demo mode."""
        script_dir = Path(__file__).resolve().parent
        self.log_file = script_dir / "workout_log.json"
        if self.has_logged_today():
            _logger.info("Workout already logged today. Skipping screen lock.")
            sys.exit(0)
        self.root = tk.Tk()
        self.root.title("Workout Locker" + (" [DEMO MODE]" if demo_mode else ""))
        self.demo_mode = demo_mode
        self.lockout_time = 10 if demo_mode else 1800
        self.workout_data: dict[str, str] = {}
        self._setup_window()
        if demo_mode:
            self._setup_demo_close_button()
        self.container = tk.Frame(self.root, bg="#1a1a1a")
        self.container.place(relx=0.5, rely=0.5, anchor="center")
        self._phone_future: Future[tuple[str, str]] | None = None
        self._start_phone_check()
        self._grab_input()

    def _setup_window(self) -> None:
        """Configure the window for fullscreen lock."""
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        self.root.overrideredirect(boolean=True)
        self.root.geometry(f"{screen_w}x{screen_h}+0+0")
        self.root.attributes(fullscreen=True)
        self.root.attributes(topmost=True)
        self.root.configure(bg="#1a1a1a", cursor="arrow")

    def _setup_demo_close_button(self) -> None:
        """Add close button for demo mode."""
        close_btn = tk.Button(
            self.root,
            text="✕ Close Demo",
            font=("Arial", 12),
            bg="#ff4444",
            fg="white",
            command=self.close,
            cursor="hand2",
        )
        close_btn.place(x=10, y=10)

    def _grab_input(self) -> None:
        """Force input focus to the locker window."""
        self.root.update_idletasks()
        self.root.focus_force()
        if self.demo_mode:
            with contextlib.suppress(tk.TclError):
                self.root.grab_set()
        else:
            try:
                self.root.grab_set_global()
            except tk.TclError:
                _logger.warning("Global grab failed, falling back to local grab")
                with contextlib.suppress(tk.TclError):
                    self.root.grab_set()

    def clear_container(self) -> None:
        """Remove all widgets from the main container."""
        for widget in self.container.winfo_children():
            widget.destroy()

    # ------------------------------------------------------------------
    # UI helper methods
    # ------------------------------------------------------------------

    def _label(
        self,
        text: str,
        *,
        font_size: int = 36,
        color: str = "white",
        pady: int = 20,
    ) -> tk.Label:
        """Create and pack a bold label in the container."""
        label = tk.Label(
            self.container,
            text=text,
            font=("Arial", font_size, "bold"),
            fg=color,
            bg="#1a1a1a",
        )
        label.pack(pady=pady)
        return label

    def _text(
        self,
        text: str,
        *,
        font_size: int = 18,
        color: str = "white",
        pady: int = 10,
    ) -> tk.Label:
        """Create and pack a non-bold text label in the container."""
        label = tk.Label(
            self.container,
            text=text,
            font=("Arial", font_size),
            fg=color,
            bg="#1a1a1a",
        )
        label.pack(pady=pady)
        return label

    def _button(
        self,
        parent: tk.Widget,
        text: str,
        *,
        bg: str,
        command: Callable[[], None],
        width: int = 10,
    ) -> tk.Button:
        """Create a styled button (caller must pack)."""
        return tk.Button(
            parent,
            text=text,
            font=("Arial", 24, "bold"),
            bg=bg,
            fg="white",
            width=width,
            command=command,
            cursor="hand2" if self.demo_mode else "",
        )

    def _button_row(self) -> tk.Frame:
        """Create and pack a horizontal button container."""
        frame = tk.Frame(self.container, bg="#1a1a1a")
        frame.pack(pady=20)
        return frame

    def _entry_row(
        self,
        label_text: str,
        *,
        width: int = 10,
        font_size: int = 20,
    ) -> tk.Entry:
        """Create a labeled entry row, returning the Entry widget."""
        frame = tk.Frame(self.container, bg="#1a1a1a")
        frame.pack(pady=10)
        tk.Label(
            frame,
            text=label_text,
            font=("Arial", font_size),
            fg="white",
            bg="#1a1a1a",
        ).pack(side="left", padx=10)
        entry = tk.Entry(frame, font=("Arial", font_size), width=width)
        entry.pack(side="left", padx=10)
        return entry

    def _disabled_submit_button(self) -> tk.Button:
        """Create a disabled submit button."""
        btn = tk.Button(
            self.container,
            text="SUBMIT (locked)",
            font=("Arial", 24, "bold"),
            bg="#666666",
            fg="white",
            width=15,
            state="disabled",
            cursor="hand2" if self.demo_mode else "",
        )
        btn.pack(pady=10)
        return btn

    def _back_button(self, command: Callable[[], None]) -> tk.Button:
        """Create and pack a back button."""
        btn = tk.Button(
            self.container,
            text="← BACK",
            font=("Arial", 18),
            bg="#666666",
            fg="white",
            width=15,
            command=command,
            cursor="hand2" if self.demo_mode else "",
        )
        btn.pack(pady=10)
        return btn

    def _setup_form_controls(
        self,
        entries: list[tk.Entry],
        verify_command: Callable[[], None],
        back_command: Callable[[], None],
    ) -> None:
        """Set up timer, submit button, and back button for a form."""
        self.timer_label = self._text("", font_size=16, color="#ffaa00")
        self.submit_btn = self._disabled_submit_button()
        self._back_button(back_command)
        self.submit_unlock_time = (
            SUBMIT_DELAY_DEMO if self.demo_mode else SUBMIT_DELAY_PRODUCTION
        )
        self.entries_to_check = entries
        self.submit_command = verify_command
        self.update_submit_timer()

    # ------------------------------------------------------------------
    # Error, unlock, and logging
    # ------------------------------------------------------------------

    def show_error(self, message: str) -> None:
        """Display error message with retry option."""
        self.clear_container()
        self._label("ERROR", font_size=48, color="#ff4444", pady=20)
        msg_label = tk.Label(
            self.container,
            text=message,
            font=("Arial", 24),
            fg="white",
            bg="#1a1a1a",
            wraplength=800,
        )
        msg_label.pack(pady=20)
        self._button(
            self.container,
            "TRY AGAIN",
            bg="#0066cc",
            command=self.ask_workout_done,
            width=15,
        ).pack(pady=30)

    def _try_adjust_shutdown_for_workout(self) -> bool:
        """Try to adjust shutdown time later for actual workouts."""
        workout_type = self.workout_data.get("type", "")
        if workout_type not in ("running", "strength", "phone_verified"):
            return False
        adjusted = self._adjust_shutdown_time_later()
        if adjusted:
            _logger.info("Shutdown time moved 1.5 hours later as workout reward")
        return adjusted

    def unlock_screen(self) -> None:
        """Save workout log and display success message."""
        self.save_workout_log()
        shutdown_adjusted = self._try_adjust_shutdown_for_workout()
        self.clear_container()
        self._label("Great job! 💪", font_size=48, color="#00ff00", pady=30)
        if shutdown_adjusted:
            self._text(
                "Shutdown time +1.5h later! 🎁",
                font_size=24,
                color="#ffaa00",
            )
        self._text("Screen Unlocked!", font_size=36, pady=20)
        self.root.after(1500, self.close)

    def has_logged_today(self) -> bool:
        """Check if workout has been logged today."""
        if not self.log_file.exists():
            return False

        try:
            with self.log_file.open() as f:
                logs = json.load(f)
        except (OSError, json.JSONDecodeError):
            return False
        else:
            today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
            return today in logs

    def _load_existing_logs(self) -> dict:
        """Load existing workout logs from file."""
        if not self.log_file.exists():
            return {}
        try:
            with self.log_file.open() as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

    def save_workout_log(self) -> None:
        """Save workout data to log file."""
        logs = self._load_existing_logs()
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        logs[today] = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "workout_data": self.workout_data,
        }
        try:
            with self.log_file.open("w") as f:
                json.dump(logs, f, indent=2)
        except OSError as e:
            _logger.warning("Could not save workout log: %s", e)

    def close(self) -> None:
        """Close the application and exit."""
        self.root.destroy()
        sys.exit(0)

    def run(self) -> None:
        """Start the Tkinter main event loop."""
        self.root.mainloop()


if __name__ == "__main__":
    # Check for --production flag
    demo_mode = True  # Default to demo mode for safety

    if len(sys.argv) > 1 and sys.argv[1] == "--production":
        demo_mode = False

    locker = ScreenLocker(demo_mode=demo_mode)
    locker.run()
