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

from python_pkg.screen_locker._constants import (
    HMAC_KEY_FILE,
    MAX_CLOCK_SKEW_SECONDS,
    MIN_WORKOUT_DURATION_MINUTES,
    PHONE_PENALTY_DELAY_DEMO,
    PHONE_PENALTY_DELAY_PRODUCTION,
    SICK_LOCKOUT_SECONDS,
    STRONGLIFTS_DB_REMOTE,
)
from python_pkg.screen_locker._log_integrity import (
    compute_entry_hmac,
    verify_entry_hmac,
)
from python_pkg.screen_locker._phone_verification import PhoneVerificationMixin
from python_pkg.screen_locker._shutdown import ShutdownMixin
from python_pkg.screen_locker._ui_flows import UIFlowsMixin
from python_pkg.wake_alarm._state import has_workout_skip_today

if TYPE_CHECKING:
    from collections.abc import Callable
    from concurrent.futures import Future

__all__ = [
    "HMAC_KEY_FILE",
    "MAX_CLOCK_SKEW_SECONDS",
    "MIN_WORKOUT_DURATION_MINUTES",
    "PHONE_PENALTY_DELAY_DEMO",
    "PHONE_PENALTY_DELAY_PRODUCTION",
    "SICK_LOCKOUT_SECONDS",
    "STRONGLIFTS_DB_REMOTE",
    "ScreenLocker",
]

_logger = logging.getLogger(__name__)


def _assert_not_under_pytest() -> None:
    """Raise if the screen locker is being created inside a pytest run.

    Defence-in-depth: prevents a real fullscreen Tk window from locking
    the user's screen when tests forget to mock ``tk.Tk``.
    The check is cheap (one dict lookup) and only fires during testing.
    """
    if "pytest" in sys.modules and getattr(tk, "__name__", "") == "tkinter":
        msg = (
            "SAFETY: ScreenLocker.__init__ called under pytest with "
            "real tkinter — tk.Tk is not mocked"
        )
        raise RuntimeError(msg)


class ScreenLocker(
    ShutdownMixin,
    PhoneVerificationMixin,
    UIFlowsMixin,
):
    """Screen locker that requires workout logging to unlock."""

    def __init__(
        self,
        *,
        demo_mode: bool = True,
        verify_only: bool = False,
    ) -> None:
        """Initialize screen locker with optional demo mode."""
        _assert_not_under_pytest()
        script_dir = Path(__file__).resolve().parent
        self.log_file = script_dir / "workout_log.json"
        self.verify_only = verify_only
        if verify_only:
            if not self._is_sick_day_log():
                _logger.info(
                    "No sick day logged today. Nothing to verify.",
                )
                sys.exit(0)
        elif self.has_logged_today():
            _logger.info("Workout already logged today. Skipping screen lock.")
            sys.exit(0)
        elif has_workout_skip_today():
            _logger.info("Wake alarm earned workout skip. Skipping screen lock.")
            sys.exit(0)
        self.root = tk.Tk()
        title_suffix = (
            " [VERIFY]" if verify_only else (" [DEMO MODE]" if demo_mode else "")
        )
        self.root.title("Workout Locker" + title_suffix)
        self.demo_mode = demo_mode
        self.lockout_time = 10 if demo_mode else 1800
        self.workout_data: dict[str, str] = {}
        if verify_only:
            self._setup_verify_window()
        else:
            self._setup_window()
            if demo_mode:
                self._setup_demo_close_button()
        self.container = tk.Frame(self.root, bg="#1a1a1a")
        self.container.place(relx=0.5, rely=0.5, anchor="center")
        self._phone_future: Future[tuple[str, str]] | None = None
        if verify_only:
            self._start_verify_workout_check()
        else:
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

    def _setup_verify_window(self) -> None:
        """Configure window for post-sick-day workout verification."""
        self.root.geometry("600x400")
        self.root.configure(bg="#1a1a1a", cursor="arrow")
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _is_sick_day_log(self) -> bool:
        """Check if today's workout log is a sick day (not yet verified)."""
        if not self.log_file.exists():
            return False
        try:
            with self.log_file.open() as f:
                logs = json.load(f)
        except (OSError, json.JSONDecodeError):
            return False
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        entry = logs.get(today)
        if entry is None:
            return False
        return entry.get("workout_data", {}).get("type") == "sick_day"

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

    # ------------------------------------------------------------------
    # Unlock, logging
    # ------------------------------------------------------------------

    def _try_adjust_shutdown_for_workout(self) -> bool:
        """Try to adjust shutdown time later for actual workouts."""
        workout_type = self.workout_data.get("type", "")
        if workout_type != "phone_verified":
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
        """Check if workout has been logged today with valid HMAC."""
        if not self.log_file.exists():
            return False

        try:
            with self.log_file.open() as f:
                logs = json.load(f)
        except (OSError, json.JSONDecodeError):
            return False
        else:
            today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
            entry = logs.get(today)
            if entry is None:
                return False
            if not verify_entry_hmac(entry):
                _logger.warning("HMAC verification failed for today's log entry")
                return False
            return True

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
        """Save workout data to log file with HMAC signature."""
        logs = self._load_existing_logs()
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        entry: dict[str, object] = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "workout_data": self.workout_data,
        }
        signature = compute_entry_hmac(entry)
        if signature is not None:
            entry["hmac"] = signature
        else:
            _logger.warning("HMAC key unavailable — saving unsigned entry")
        logs[today] = entry
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
    verify_only = "--verify-workout" in sys.argv

    if "--production" in sys.argv:
        demo_mode = False

    locker = ScreenLocker(
        demo_mode=demo_mode,
        verify_only=verify_only,
    )
    locker.run()
