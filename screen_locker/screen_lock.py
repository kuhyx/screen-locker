#!/usr/bin/env python3
"""Screen locker with workout verification for Arch Linux / i3wm.

Requires user to log their workout to unlock the screen.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sys
import tkinter as tk
from typing import TYPE_CHECKING

from python_pkg.screen_locker import _sick_tracker
from python_pkg.screen_locker._constants import (
    EARLY_BIRD_END_HOUR,
    EARLY_BIRD_END_MINUTE,
    EARLY_BIRD_START_HOUR,
    HMAC_KEY_FILE,
    MAX_CLOCK_SKEW_SECONDS,
    MIN_WORKOUT_DURATION_MINUTES,
    PHONE_PENALTY_DELAY_DEMO,
    PHONE_PENALTY_DELAY_PRODUCTION,
    SCHEDULED_SKIPS_FILE,
    SICK_LOCKOUT_SECONDS,
    STRONGLIFTS_DB_REMOTE,
)
from python_pkg.screen_locker._early_bird import EarlyBirdMixin
from python_pkg.screen_locker._log_integrity import (
    _load_hmac_key,
    compute_entry_hmac,
    verify_entry_hmac,
)
from python_pkg.screen_locker._phone_verification import PhoneVerificationMixin
from python_pkg.screen_locker._shutdown import ShutdownMixin
from python_pkg.screen_locker._sick_dialog import SickDialogMixin
from python_pkg.screen_locker._ui_flows import UIFlowsMixin
from python_pkg.screen_locker._weekly_check import (
    WEEKLY_WORKOUT_MINIMUM,
    has_weekly_minimum,
    is_relaxed_day,
)
from python_pkg.screen_locker._window_setup import WindowSetupMixin
from python_pkg.wake_alarm._state import has_workout_skip_today

if TYPE_CHECKING:
    from collections.abc import Callable
    from concurrent.futures import Future

__all__ = [
    "EARLY_BIRD_END_HOUR",
    "EARLY_BIRD_END_MINUTE",
    "EARLY_BIRD_START_HOUR",
    "HMAC_KEY_FILE",
    "MAX_CLOCK_SKEW_SECONDS",
    "MIN_WORKOUT_DURATION_MINUTES",
    "PHONE_PENALTY_DELAY_DEMO",
    "PHONE_PENALTY_DELAY_PRODUCTION",
    "SCHEDULED_SKIPS_FILE",
    "SICK_LOCKOUT_SECONDS",
    "STRONGLIFTS_DB_REMOTE",
    "WEEKLY_WORKOUT_MINIMUM",
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
    EarlyBirdMixin,
    WindowSetupMixin,
    ShutdownMixin,
    PhoneVerificationMixin,
    SickDialogMixin,
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
        self.workout_data: dict[str, str] = {}
        self._relaxed_day_mode: bool = False
        self._check_early_exits(verify_only=verify_only)
        self.root = tk.Tk()
        title_suffix = (
            " [VERIFY]" if verify_only else (" [DEMO MODE]" if demo_mode else "")
        )
        self.root.title("Workout Locker" + title_suffix)
        self.demo_mode = demo_mode
        self.lockout_time = 10 if demo_mode else 1800
        if verify_only:
            self._setup_verify_window()
        elif self._relaxed_day_mode:
            self._setup_relaxed_day_window()
        else:
            self._setup_window()
            if demo_mode:
                self._setup_demo_close_button()
        self.container = tk.Frame(self.root, bg="#1a1a1a")
        self.container.place(relx=0.5, rely=0.5, anchor="center")
        self._phone_future: Future[tuple[str, str]] | None = None
        if verify_only:
            self._start_verify_workout_check()
        elif self._relaxed_day_mode:
            self._start_relaxed_day_flow()
        else:
            self._start_phone_check()
            self._grab_input()

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

    def _check_early_exits(self, *, verify_only: bool) -> None:
        """Check startup conditions and exit early when appropriate."""
        if verify_only:
            if not self._is_sick_day_log():
                _logger.info(
                    "No sick day logged today. Nothing to verify.",
                )
                sys.exit(0)
            return
        self._check_non_verify_exits()

    def _check_today_state_exits(self) -> bool:
        """Handle early-bird and today's log states. Return True to stop startup."""
        if self._is_early_bird_log() and not self._is_early_bird_time():
            if self._try_auto_upgrade_early_bird():
                _logger.info("Auto-upgraded early_bird entry to phone_verified.")
                sys.exit(0)
                return True
            return False  # Expired early bird, upgrade unavailable — full lock.
        if self._is_early_bird_log():
            _logger.info("Early bird window still active — skipping lock.")
        elif self._is_sick_day_log() and self._try_auto_upgrade_sick_day():
            _logger.info("Auto-upgraded today's sick_day entry to phone_verified.")
        elif self.has_logged_today():
            _logger.info("Workout already logged today. Skipping screen lock.")
        elif has_workout_skip_today():
            _logger.info("Wake alarm earned workout skip. Skipping screen lock.")
        elif self._is_early_bird_time():
            self._save_early_bird_log()
            _logger.info("Early bird time — skipping lock, will re-check at 08:30.")
        else:
            return False
        sys.exit(0)
        return True

    def _check_non_verify_exits(self) -> None:
        """Check all normal (non-verify) startup early-exit conditions."""
        if self._is_scheduled_skip_today():
            _logger.info("Today is a scheduled skip day. Skipping screen lock.")
            sys.exit(0)
            return
        if self._check_today_state_exits():
            return
        # Day-of-week routing: Tue/Wed/Thu relaxed (optional), Fri-Mon enforced.
        if is_relaxed_day():
            _logger.info("Relaxed day (Tue-Thu) - showing optional workout prompt.")
            self._relaxed_day_mode = True
            return
        # Fri-Mon: skip lock when weekly minimum is already met.
        if has_weekly_minimum(self.log_file):
            _logger.info(
                "Weekly minimum of %d workouts met. Skipping screen lock.",
                WEEKLY_WORKOUT_MINIMUM,
            )
            sys.exit(0)
            return

    def _try_auto_upgrade_sick_day(self) -> bool:
        """Silently upgrade today's sick_day entry if phone shows a workout."""
        try:
            status, message = self._verify_phone_workout()
        except (OSError, RuntimeError) as exc:
            _logger.info("Auto-upgrade phone check failed: %s", exc)
            return False
        if status != "verified":
            _logger.info(
                "Auto-upgrade skipped (phone status=%s): %s",
                status,
                message,
            )
            return False
        self.workout_data["type"] = "phone_verified"
        self.workout_data["source"] = message
        self.workout_data["after_sick_day"] = "true"
        self._adjust_shutdown_time_later()
        self.save_workout_log()
        return True

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

    def _clear_debt_on_verified_workout(self) -> int | None:
        """Decrement workout debt by one for a verified workout.

        Returns the new debt count, or ``None`` when this wasn't a
        phone-verified workout.
        """
        if self.workout_data.get("type") != "phone_verified":
            return None
        history = _sick_tracker.load_history()
        if history.debt <= 0:
            return 0
        new_debt = _sick_tracker.clear_one_debt(history)
        _sick_tracker.save_history(history)
        return new_debt

    def unlock_screen(self) -> None:
        """Save workout log and display success message."""
        self.save_workout_log()
        shutdown_adjusted = self._try_adjust_shutdown_for_workout()
        new_debt = self._clear_debt_on_verified_workout()
        self.clear_container()
        self._label("Great job! 💪", font_size=48, color="#00ff00", pady=30)
        if shutdown_adjusted:
            self._text(
                "Shutdown time +1.5h later! 🎁",
                font_size=24,
                color="#ffaa00",
            )
        if new_debt is not None:
            self._text(
                f"Workout debt: {new_debt}",
                font_size=20,
                color="#ffaa00" if new_debt > 0 else "#888888",
            )
        self._text("Screen Unlocked!", font_size=36, pady=20)
        if self.workout_data.get("type") == "phone_verified":
            self.root.after(
                1500,
                lambda: self._show_commitment_prompt(on_done=self.close),
            )
        else:
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
            if verify_entry_hmac(entry):
                return entry.get("workout_data", {}).get("type") != "early_bird"
            if _load_hmac_key() is None and "hmac" not in entry:
                _logger.info(
                    "HMAC key unavailable — accepting unsigned entry",
                )
                return entry.get("workout_data", {}).get("type") != "early_bird"
            _logger.warning(
                "HMAC verification failed for today's log entry",
            )
            return False

    def _load_existing_logs(self) -> dict:
        """Load existing workout logs from file."""
        if not self.log_file.exists():
            return {}
        try:
            with self.log_file.open() as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

    def _is_scheduled_skip_today(self) -> bool:
        """Return True if today's date is listed in the scheduled skips file."""
        if not SCHEDULED_SKIPS_FILE.exists():
            return False
        try:
            with SCHEDULED_SKIPS_FILE.open() as f:
                skips = json.load(f)
        except (OSError, json.JSONDecodeError):
            return False
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        return today in skips

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
        if not self.demo_mode:
            self._restore_vt_switching()
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
