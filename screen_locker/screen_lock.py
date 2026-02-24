#!/usr/bin/env python3
"""Screen locker with workout verification for Arch Linux / i3wm.

Requires user to log their workout to unlock the screen.
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, as_completed
import contextlib
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import tkinter as tk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

_logger = logging.getLogger(__name__)

# Validation limits for workout data
MAX_DISTANCE_KM = 100
MAX_TIME_MINUTES = 600
MAX_PACE_MIN_PER_KM = 20
MIN_EXERCISE_NAME_LEN = 3
MAX_SETS = 20
MAX_REPS = 100
MAX_WEIGHT_KG = 500
SICK_LOCKOUT_SECONDS = 120  # 2 minutes wait when sick
SUBMIT_DELAY_DEMO = 30
SUBMIT_DELAY_PRODUCTION = 180
PHONE_PENALTY_DELAY_DEMO = 10
PHONE_PENALTY_DELAY_PRODUCTION = 600
ADB_TIMEOUT = 15
STRONGLIFTS_DB_REMOTE = (
    "/data/data/com.stronglifts.app/databases/StrongLifts-Database-3"
)
SHUTDOWN_CONFIG_FILE = Path("/etc/shutdown-schedule.conf")
# Helper script path (relative to this file)
ADJUST_SHUTDOWN_SCRIPT = Path(__file__).resolve().parent / "adjust_shutdown_schedule.sh"
# State file to track sick day usage and original config values
SICK_DAY_STATE_FILE = Path(__file__).resolve().parent / "sick_day_state.json"

_STRENGTH_FIELDS: list[tuple[str, int]] = [
    ("Exercises (comma-separated):", 50),
    ("Sets per exercise (comma-separated):", 20),
    ("Reps (comma-sep, + for variable: 12+11+12):", 30),
    ("Weight per exercise kg (comma-separated):", 20),
    ("Total weight lifted (kg):", 15),
]


class ScreenLocker:
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
        self.root.overrideredirect(True)
        self.root.geometry(f"{screen_w}x{screen_h}+0+0")
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-topmost", True)
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
    # Main screen flows
    # ------------------------------------------------------------------

    def ask_workout_done(self) -> None:
        """Display the initial workout question dialog."""
        self.clear_container()
        self._label("Did you work out today?", pady=30)
        frame = self._button_row()
        self._button(
            frame,
            "YES",
            bg="#00aa00",
            command=self.ask_workout_type,
        ).pack(side="left", padx=20)
        self._button(
            frame,
            "NO",
            bg="#aa0000",
            command=self.ask_if_sick,
        ).pack(side="left", padx=20)

    def _start_phone_check(self) -> None:
        """Check phone for today's workout immediately at startup."""
        self.clear_container()
        self._label("Checking phone...", font_size=36, color="#ffaa00", pady=30)
        self._text("Looking for today's workout in StrongLifts...", font_size=18)
        executor = ThreadPoolExecutor(max_workers=1)
        self._phone_future = executor.submit(self._verify_phone_workout)
        executor.shutdown(wait=False)
        self._poll_phone_check()

    def _poll_phone_check(self) -> None:
        """Poll background phone check and route to result handler when done."""
        if self._phone_future is not None and self._phone_future.done():
            status, message = self._phone_future.result()
            self._handle_startup_phone_result(status, message)
        else:
            self.root.after(500, self._poll_phone_check)

    def _handle_startup_phone_result(self, status: str, message: str) -> None:
        """Route to appropriate screen based on startup phone check result."""
        if status == "verified":
            self.workout_data["type"] = "phone_verified"
            self.workout_data["source"] = message
            self.clear_container()
            self._label(
                "\u2713 Workout Verified!", font_size=42, color="#00cc44", pady=30
            )
            self._text(message, font_size=20, color="#aaffaa")
            self._text("Unlocking...", font_size=18, color="#888888")
            unlock_delay = 1500 if self.demo_mode else 2000
            self.root.after(unlock_delay, self.unlock_screen)
        elif status == "not_verified":
            self.clear_container()
            self._label("No Workout Found", font_size=36, color="#ff4444", pady=20)
            self._text(
                f"\u274c {message}\n\n"
                "StrongLifts shows no workout today.\n"
                "Go do your workout first!",
                color="#ffaa00",
            )
            frame = self._button_row()
            self._button(
                frame,
                "TRY AGAIN",
                bg="#0066cc",
                command=self._start_phone_check,
                width=12,
            ).pack(side="left", padx=10)
            self._button(
                frame,
                "I'm sick",
                bg="#cc6600",
                command=self.ask_if_sick,
                width=12,
            ).pack(side="left", padx=10)
        else:
            # no_phone or error — penalty timer, then proceed to logging form
            self._show_phone_penalty(message, on_done=self.ask_workout_done)

    def ask_if_sick(self) -> None:
        """Display sick day question dialog."""
        self.clear_container()
        self._label("Are you sick?", pady=30)
        self._text(
            "If yes, shutdown time will be moved 1.5 hours earlier",
            color="#ffaa00",
        )
        self._sick_question_buttons()

    def _sick_question_buttons(self) -> None:
        """Create the sick day yes/no buttons."""
        frame = self._button_row()
        self._button(
            frame,
            "YES (sick)",
            bg="#cc6600",
            command=self.handle_sick_day,
            width=12,
        ).pack(side="left", padx=20)
        self._button(
            frame,
            "NO",
            bg="#aa0000",
            command=self.lockout,
            width=12,
        ).pack(side="left", padx=20)

    def _get_sick_day_status(self) -> tuple[str, str]:
        """Determine sick day status text and color."""
        if self._sick_mode_used_today():
            return "Shutdown time already adjusted today", "#ffaa00"
        if self._adjust_shutdown_time_earlier():
            return (
                "Shutdown time moved 1.5 hours earlier ✓\n(Will revert tomorrow)"
            ), "#00aa00"
        return "Could not adjust shutdown time (check permissions)", "#ff4444"

    def handle_sick_day(self) -> None:
        """Handle sick day: adjust shutdown time and start 2-minute wait."""
        self.clear_container()
        status_text, status_color = self._get_sick_day_status()
        self._show_sick_day_ui(status_text, status_color)
        self.sick_remaining_time = SICK_LOCKOUT_SECONDS
        self._update_sick_countdown()

    def _show_sick_day_ui(self, status_text: str, status_color: str) -> None:
        """Display sick day UI labels and countdown."""
        self._label("Sick Day Mode", color="#cc6600", pady=20)
        self._text(status_text, color=status_color)
        self._text(
            "Please wait 2 minutes before unlocking...",
            font_size=24,
            pady=20,
        )
        self.sick_countdown_label = self._label(
            str(SICK_LOCKOUT_SECONDS),
            font_size=80,
            pady=30,
        )

    def _update_sick_countdown(self) -> None:
        """Update the sick day countdown timer."""
        if self.sick_remaining_time > 0:
            self.sick_countdown_label.config(text=str(self.sick_remaining_time))
            self.sick_remaining_time -= 1
            self.root.after(1000, self._update_sick_countdown)
        else:
            # Record sick day and unlock
            self.workout_data["type"] = "sick_day"
            self.workout_data["note"] = "Sick day - shutdown moved earlier"
            self.unlock_screen()

    # ------------------------------------------------------------------
    # Shutdown schedule adjustment
    # ------------------------------------------------------------------

    def _apply_earlier_shutdown(self, today: str) -> bool:
        """Read config, save state, and write earlier shutdown hours."""
        config_values = self._read_shutdown_config()
        if config_values is None:
            return False
        mon_wed_hour, thu_sun_hour, morning_end_hour = config_values
        if not self._save_sick_day_state(today, mon_wed_hour, thu_sun_hour):
            _logger.error("Failed to save state - aborting adjustment")
            return False
        new_mon_wed = max(18, mon_wed_hour - 1)
        new_thu_sun = max(18, thu_sun_hour - 1)
        return self._write_shutdown_config(
            new_mon_wed,
            new_thu_sun,
            morning_end_hour,
        )

    def _adjust_shutdown_time_earlier(self) -> bool:
        """Adjust shutdown schedule 1.5 hours earlier (stricter).

        This can only be used once per day. Original values are saved and
        automatically restored when checked the next day.

        Returns True if successful, False otherwise.
        """
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        self._restore_original_config_if_needed()
        if self._sick_mode_used_today():
            _logger.warning("Sick mode already used today")
            return False
        try:
            return self._apply_earlier_shutdown(today)
        except (OSError, ValueError) as e:
            _logger.warning("Failed to adjust shutdown time: %s", e)
            return False

    def _adjust_shutdown_time_later(self) -> bool:
        """Adjust shutdown schedule 2 hours later as workout reward.

        Returns True if successful, False otherwise.
        """
        try:
            config_values = self._read_shutdown_config()
            if config_values is None:
                return False
            mon_wed_hour, thu_sun_hour, morning_end_hour = config_values
            new_mon_wed = min(23, mon_wed_hour + 2)
            new_thu_sun = min(23, thu_sun_hour + 2)
            return self._write_shutdown_config(
                new_mon_wed,
                new_thu_sun,
                morning_end_hour,
                restore=True,
            )
        except (OSError, ValueError) as e:
            _logger.warning("Failed to adjust shutdown time for workout: %s", e)
            return False

    def _sick_mode_used_today(self) -> bool:
        """Check if sick mode was already used today."""
        if not SICK_DAY_STATE_FILE.exists():
            return False

        try:
            with SICK_DAY_STATE_FILE.open() as f:
                state = json.load(f)
            today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
            return state.get("date") == today
        except (OSError, json.JSONDecodeError):
            return False

    def _save_sick_day_state(
        self,
        date: str,
        orig_mon_wed: int,
        orig_thu_sun: int,
    ) -> bool:
        """Save sick day state with original config values.

        Returns True if saved successfully, False otherwise.
        """
        state = {
            "date": date,
            "original_mon_wed_hour": orig_mon_wed,
            "original_thu_sun_hour": orig_thu_sun,
        }
        try:
            with SICK_DAY_STATE_FILE.open("w") as f:
                json.dump(state, f, indent=2)
        except OSError as e:
            _logger.warning("Failed to save sick day state: %s", e)
            return False

        _logger.info("Saved sick day state for %s", date)
        return True

    def _load_sick_day_state(self) -> tuple[str, int, int] | None:
        """Load sick day state file.

        Returns (date, orig_mon_wed_hour, orig_thu_sun_hour) or None.
        """
        with SICK_DAY_STATE_FILE.open() as f:
            state = json.load(f)
        date = state.get("date")
        orig_mw = state.get("original_mon_wed_hour")
        orig_ts = state.get("original_thu_sun_hour")
        if date is None or orig_mw is None or orig_ts is None:
            return None
        return (str(date), int(orig_mw), int(orig_ts))

    def _write_restored_config(
        self,
        orig_mw: int,
        orig_ts: int,
        state_date: str,
    ) -> None:
        """Write restored config values and clean up state file."""
        config_values = self._read_shutdown_config()
        if config_values:
            _, _, morning_end = config_values
            _logger.info(
                "Restoring original shutdown config from %s",
                state_date,
            )
            self._write_shutdown_config(
                orig_mw,
                orig_ts,
                morning_end,
                restore=True,
            )
        SICK_DAY_STATE_FILE.unlink()
        _logger.info("Removed stale sick day state from %s", state_date)

    def _restore_original_config_if_needed(self) -> None:
        """Restore original config if sick day state is from a previous day."""
        if not SICK_DAY_STATE_FILE.exists():
            return
        try:
            loaded = self._load_sick_day_state()
            if loaded is None:
                return
            state_date, orig_mw, orig_ts = loaded
            today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
            if state_date != today:
                self._write_restored_config(orig_mw, orig_ts, state_date)
        except (OSError, json.JSONDecodeError) as e:
            _logger.warning("Error checking sick day state: %s", e)

    def _read_shutdown_config(self) -> tuple[int, int, int] | None:
        """Read shutdown config. Returns (mw_hour, ts_hour, me_hour) or None."""
        if not SHUTDOWN_CONFIG_FILE.exists():
            _logger.warning("Config not found: %s", SHUTDOWN_CONFIG_FILE)
            return None
        parsed: dict[str, int] = {}
        keys = ("MON_WED_HOUR", "THU_SUN_HOUR", "MORNING_END_HOUR")
        with SHUTDOWN_CONFIG_FILE.open() as f:
            for line in f:
                stripped = line.strip()
                for key in keys:
                    if stripped.startswith(f"{key}="):
                        parsed[key] = int(stripped.split("=")[1])
        if len(parsed) < len(keys):
            _logger.warning("Shutdown config missing required values")
            return None
        return (
            parsed["MON_WED_HOUR"],
            parsed["THU_SUN_HOUR"],
            parsed["MORNING_END_HOUR"],
        )

    def _build_shutdown_cmd(
        self,
        mon_wed: int,
        thu_sun: int,
        morning: int,
        *,
        restore: bool,
    ) -> list[str]:
        """Build the shutdown adjustment command."""
        cmd = ["/usr/bin/sudo", str(ADJUST_SHUTDOWN_SCRIPT)]
        if restore:
            cmd.append("--restore")
        cmd.extend([str(mon_wed), str(thu_sun), str(morning)])
        return cmd

    def _write_shutdown_config(
        self,
        mon_wed_hour: int,
        thu_sun_hour: int,
        morning_end_hour: int,
        *,
        restore: bool = False,
    ) -> bool:
        """Write new shutdown config values using helper script.

        Args:
            mon_wed_hour: Shutdown hour for Monday-Wednesday.
            thu_sun_hour: Shutdown hour for Thursday-Sunday.
            morning_end_hour: Morning end hour.
            restore: If True, allows restoring to later times.

        Returns True if successful, False otherwise.
        """
        if not ADJUST_SHUTDOWN_SCRIPT.exists():
            _logger.warning(
                "Script not found: %s",
                ADJUST_SHUTDOWN_SCRIPT,
            )
            return False
        cmd = self._build_shutdown_cmd(
            mon_wed_hour,
            thu_sun_hour,
            morning_end_hour,
            restore=restore,
        )
        return self._run_shutdown_cmd(cmd, mon_wed_hour, thu_sun_hour)

    def _run_shutdown_cmd(
        self,
        cmd: list[str],
        mon_wed_hour: int,
        thu_sun_hour: int,
    ) -> bool:
        """Execute the shutdown adjustment command."""
        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.SubprocessError as e:
            _logger.warning("Failed to adjust shutdown config: %s", e)
            return False
        _logger.info(
            "Adjusted shutdown: Mon-Wed=%d, Thu-Sun=%d. %s",
            mon_wed_hour,
            thu_sun_hour,
            result.stdout.strip(),
        )
        return True

    # ------------------------------------------------------------------
    # Lockout flow
    # ------------------------------------------------------------------

    def lockout(self) -> None:
        """Display lockout screen with countdown timer."""
        self.clear_container()
        self.lockout_label = self._label(
            f"Go work out!\nLocked for {self.lockout_time} seconds",
            font_size=48,
            color="#ff4444",
            pady=30,
        )
        self.countdown_label = self._label(
            str(self.lockout_time),
            font_size=120,
            pady=30,
        )
        self.remaining_time = self.lockout_time
        self.update_lockout_countdown()

    def update_lockout_countdown(self) -> None:
        """Update the lockout countdown timer display."""
        if self.remaining_time > 0:
            self.countdown_label.config(text=str(self.remaining_time))
            self.remaining_time -= 1
            self.root.after(1000, self.update_lockout_countdown)
        else:
            self.ask_workout_done()

    # ------------------------------------------------------------------
    # Workout type selection
    # ------------------------------------------------------------------

    def ask_workout_type(self) -> None:
        """Display workout type selection dialog."""
        self.clear_container()
        self._label("What type of workout?", pady=30)
        frame = self._button_row()
        self._button(
            frame,
            "STRENGTH",
            bg="#cc6600",
            command=self.ask_strength_details,
            width=12,
        ).pack(side="left", padx=20)

    # ------------------------------------------------------------------
    # Running workout
    # ------------------------------------------------------------------

    def _create_running_entries(self) -> list[tk.Entry]:
        """Create running workout entry fields."""
        self.distance_entry = self._entry_row("Distance (km):")
        self.time_entry = self._entry_row("Time (minutes):")
        self.pace_entry = self._entry_row("Pace (min/km):")
        return [self.distance_entry, self.time_entry, self.pace_entry]

    def ask_running_details(self) -> None:
        """Display running workout input form."""
        self.clear_container()
        self.workout_data["type"] = "running"
        self._label("Running Details", pady=20)
        entries = self._create_running_entries()
        self._setup_form_controls(
            entries,
            self.verify_running_data,
            self.ask_workout_type,
        )

    def _check_running_ranges(
        self,
        distance: float,
        time_mins: float,
        pace: float,
    ) -> str | None:
        """Check if running values are in valid ranges."""
        if distance <= 0 or distance > MAX_DISTANCE_KM:
            return f"Distance seems unrealistic (0-{MAX_DISTANCE_KM} km)"
        if time_mins <= 0 or time_mins > MAX_TIME_MINUTES:
            return f"Time seems unrealistic (0-{MAX_TIME_MINUTES} minutes)"
        if pace <= 0 or pace > MAX_PACE_MIN_PER_KM:
            return f"Pace seems unrealistic (0-{MAX_PACE_MIN_PER_KM} min/km)"
        expected_pace = time_mins / distance
        tolerance = expected_pace * 0.15  # 15% tolerance
        if abs(pace - expected_pace) > tolerance:
            return (
                f"Pace doesn't match! "
                f"Expected ~{expected_pace:.2f} min/km, got {pace:.2f}"
            )
        return None

    def _validate_running_input(self) -> tuple[float, float, float] | None:
        """Parse and validate running input fields."""
        try:
            distance = float(self.distance_entry.get())
            time_mins = float(self.time_entry.get())
            pace = float(self.pace_entry.get())
        except ValueError:
            self.show_error("Please enter valid numbers")
            return None
        error = self._check_running_ranges(distance, time_mins, pace)
        if error:
            self.show_error(error)
            return None
        return distance, time_mins, pace

    def verify_running_data(self) -> None:
        """Validate running workout data and unlock if valid."""
        result = self._validate_running_input()
        if result is None:
            return
        distance, time_mins, pace = result
        self.workout_data["distance_km"] = str(distance)
        self.workout_data["time_minutes"] = str(time_mins)
        self.workout_data["pace_min_per_km"] = str(pace)
        self._attempt_unlock()

    # ------------------------------------------------------------------
    # Strength workout
    # ------------------------------------------------------------------

    def _create_strength_entries(self) -> list[tk.Entry]:
        """Create strength training entry fields."""
        entries = [
            self._entry_row(lbl, width=w, font_size=18) for lbl, w in _STRENGTH_FIELDS
        ]
        (
            self.exercises_entry,
            self.sets_entry,
            self.reps_entry,
            self.weights_entry,
            self.total_weight_entry,
        ) = entries
        return entries

    def ask_strength_details(self) -> None:
        """Display strength training input form."""
        self.clear_container()
        self.workout_data["type"] = "strength"
        self._label("Strength Training Details", pady=20)
        entries = self._create_strength_entries()
        self._setup_form_controls(
            entries,
            self.verify_strength_data,
            self.ask_workout_type,
        )

    def _parse_reps(self, reps_raw: list[str]) -> list[list[int]]:
        """Parse reps input - can be single number or variable reps like '12+11+12'."""
        reps: list[list[int]] = []
        for r in reps_raw:
            if "+" in r:
                reps.append([int(x.strip()) for x in r.split("+")])
            else:
                reps.append([int(r)])
        return reps

    def _validate_strength_inputs(
        self,
        exercises: list[str],
        sets: list[int],
        reps: list[list[int]],
        weights: list[float],
    ) -> str | None:
        """Validate strength workout inputs. Returns error message or None if valid."""
        if not (len(exercises) == len(sets) == len(reps) == len(weights)):
            return "Number of exercises, sets, reps, and weights must match"
        if any(len(ex) < MIN_EXERCISE_NAME_LEN for ex in exercises):
            return "Exercise names too short - be specific"
        if any(s < 1 or s > MAX_SETS for s in sets):
            return f"Sets should be between 1-{MAX_SETS}"
        if any(w < 0 or w > MAX_WEIGHT_KG for w in weights):
            return f"Weights should be between 0-{MAX_WEIGHT_KG} kg"
        return self._validate_reps(exercises, sets, reps)

    def _validate_reps(
        self,
        exercises: list[str],
        sets: list[int],
        reps: list[list[int]],
    ) -> str | None:
        """Validate reps data. Returns error message or None if valid."""
        for i, rep_list in enumerate(reps):
            if any(r < 1 or r > MAX_REPS for r in rep_list):
                return f"Reps should be between 1-{MAX_REPS}"
            if len(rep_list) > 1 and len(rep_list) != sets[i]:
                return (
                    f"For {exercises[i]!r}: variable reps count "
                    f"({len(rep_list)}) doesn't match sets ({sets[i]})"
                )
        return None

    def _calculate_expected_total(
        self,
        sets: list[int],
        reps: list[list[int]],
        weights: list[float],
    ) -> float:
        """Calculate expected total weight lifted."""
        expected_total = 0.0
        for i, rep_list in enumerate(reps):
            if len(rep_list) == 1:
                expected_total += sets[i] * rep_list[0] * weights[i]
            else:
                expected_total += sum(rep_list) * weights[i]
        return expected_total

    def _parse_strength_entries(
        self,
    ) -> tuple[list[str], list[int], list[list[int]], list[float], float]:
        """Parse raw strength training input from entry widgets."""
        exercises = [e.strip() for e in self.exercises_entry.get().split(",")]
        sets = [int(s.strip()) for s in self.sets_entry.get().split(",")]
        reps_raw = [r.strip() for r in self.reps_entry.get().split(",")]
        reps = self._parse_reps(reps_raw)
        weights = [float(w.strip()) for w in self.weights_entry.get().split(",")]
        total_weight = float(self.total_weight_entry.get())
        return exercises, sets, reps, weights, total_weight

    def _check_total_weight(
        self,
        sets: list[int],
        reps: list[list[int]],
        weights: list[float],
        total_weight: float,
    ) -> str | None:
        """Verify total weight matches individual exercise calculations."""
        expected = self._calculate_expected_total(sets, reps, weights)
        tolerance = expected * 0.15  # 15% tolerance
        if abs(total_weight - expected) > tolerance:
            return (
                f"Total weight doesn't match! "
                f"Expected ~{expected:.1f} kg, got {total_weight:.1f}"
            )
        return None

    def _store_strength_data(
        self,
        exercises: list[str],
        sets: list[int],
        reps: list[list[int]],
        weights: list[float],
        total_weight: float,
    ) -> None:
        """Store validated strength workout data."""
        self.workout_data["exercises"] = exercises
        self.workout_data["sets"] = [str(s) for s in sets]
        self.workout_data["reps"] = [
            "+".join(str(r) for r in rep_list) for rep_list in reps
        ]
        self.workout_data["weights_kg"] = [str(w) for w in weights]
        self.workout_data["total_weight_kg"] = str(total_weight)

    def verify_strength_data(self) -> None:
        """Validate strength workout data and unlock if valid."""
        try:
            self._verify_strength_data_inner()
        except ValueError:
            self.show_error("Please enter valid data in correct format")

    def _verify_strength_data_inner(self) -> None:
        """Parse, validate, and store strength data."""
        data = self._parse_strength_entries()
        exercises, sets, reps, weights, total_weight = data
        error = self._validate_strength_inputs(exercises, sets, reps, weights)
        if error:
            self.show_error(error)
            return
        total_err = self._check_total_weight(sets, reps, weights, total_weight)
        if total_err:
            self.show_error(total_err)
            return
        self._store_strength_data(exercises, sets, reps, weights, total_weight)
        self._attempt_unlock()

    # ------------------------------------------------------------------
    # Phone workout verification via ADB + StrongLifts DB
    # ------------------------------------------------------------------

    def _run_adb(self, args: list[str]) -> tuple[bool, str]:
        """Run an ADB command and return success flag and stdout."""
        adb = shutil.which("adb") or "adb"
        # When multiple devices are connected (e.g. USB + wireless), pin to
        # the wireless device's serial to avoid "more than one device" errors.
        _discovery_cmds = {"devices", "connect", "disconnect", "kill-server"}
        serial = (
            self._get_wireless_serial()
            if args and args[0] not in _discovery_cmds
            else None
        )
        serial_args = ["-s", serial] if serial else []
        try:
            result = subprocess.run(
                [adb, *serial_args, *args],
                capture_output=True,
                text=True,
                timeout=ADB_TIMEOUT,
                check=False,
            )
        except (FileNotFoundError, OSError) as exc:
            _logger.warning("ADB not available: %s", exc)
            return False, ""
        except subprocess.TimeoutExpired:
            _logger.warning("ADB command timed out: %s", args)
            return False, ""
        return result.returncode == 0, result.stdout

    def _adb_shell(
        self,
        command: str,
        *,
        root: bool = False,
    ) -> tuple[bool, str]:
        """Run a shell command on the connected Android device."""
        if root:
            return self._run_adb(["shell", "su", "-c", command])
        return self._run_adb(["shell", command])

    def _get_wireless_serial(self) -> str | None:
        """Return the serial (ip:port) of the first connected wireless ADB device.

        Used to pin ADB commands to the wireless device when multiple devices
        (e.g. USB cable + wireless debugging) are simultaneously connected.
        """
        success, output = self._run_adb(["devices"])
        if not success:
            return None
        for line in output.strip().split("\n")[1:]:
            parts = line.split()
            if parts and ":" in parts[0] and "device" in line and "offline" not in line:
                return parts[0]
        return None

    def _has_adb_device(self) -> bool:
        """Return True if adb devices shows at least one connected device."""
        success, output = self._run_adb(["devices"])
        if not success:
            return False
        lines = output.strip().split("\n")[1:]
        return any("device" in line and "offline" not in line for line in lines)

    def _try_adb_connect(self, address: str) -> bool:
        """Run adb connect to address. Returns True on success."""
        _, output = self._run_adb(["connect", address])
        lower = output.lower()
        return "connected" in lower and "unable" not in lower and "failed" not in lower

    def _get_local_subnet_prefix(self) -> str | None:
        """Detect the local /24 network prefix (e.g. '192.168.1')."""
        with (
            contextlib.suppress(OSError),
            socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock,
        ):
            sock.connect(("8.8.8.8", 80))
            return ".".join(sock.getsockname()[0].split(".")[:3])
        return None

    def _try_wireless_reconnect(self) -> bool:
        """Scan local /24 subnet on port 5555 and attempt ADB connect to phone."""
        prefix = self._get_local_subnet_prefix()
        if prefix is None:
            _logger.info("Could not determine local subnet for wireless scan")
            return False

        def probe(i: int) -> bool:
            ip = f"{prefix}.{i}"
            with (
                contextlib.suppress(OSError),
                socket.create_connection((ip, 5555), timeout=0.5),
            ):
                if self._try_adb_connect(f"{ip}:5555"):
                    return self._has_adb_device()
            return False

        _logger.info("Scanning %s.1-254:5555 for phone...", prefix)
        with ThreadPoolExecutor(max_workers=64) as executor:
            for future in as_completed(
                executor.submit(probe, i) for i in range(1, 255)
            ):
                if future.result():
                    return True
        return False

    def _is_phone_connected(self) -> bool:
        """Check if an Android device is connected via ADB.

        If no device is visible, attempts wireless reconnection using the
        stored phone IP/port config. USB-connected devices are detected
        automatically by adb devices without any extra steps.
        """
        if self._has_adb_device():
            return True
        _logger.info("No ADB device detected — attempting wireless reconnect...")
        return self._try_wireless_reconnect()

    def _pull_stronglifts_db(self) -> Path | None:
        """Pull StrongLifts database from phone to a local temp file.

        Returns:
            Path to the local copy, or None on failure.
        """
        tmp = Path(tempfile.gettempdir()) / "stronglifts_check.db"
        success, _ = self._adb_shell(
            f"cat '{STRONGLIFTS_DB_REMOTE}' > /sdcard/_sl_tmp.db",
            root=True,
        )
        if not success:
            return None
        ok, _ = self._run_adb(["pull", "/sdcard/_sl_tmp.db", str(tmp)])
        if not ok:
            return None
        return tmp

    def _count_today_workouts(self, db_path: Path) -> int:
        """Count today's workouts in a local copy of StrongLifts DB.

        Args:
            db_path: Path to the locally-pulled StrongLifts database.

        Returns:
            Number of workouts started today (local time).
        """
        try:
            conn = sqlite3.connect(str(db_path))
            try:
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM workouts "
                    "WHERE date(start / 1000, 'unixepoch', 'localtime') "
                    "= date('now', 'localtime')",
                )
                row = cursor.fetchone()
                return int(row[0]) if row else 0
            finally:
                conn.close()
        except (sqlite3.Error, ValueError, TypeError):
            _logger.warning("Failed to query StrongLifts database")
            return 0

    def _verify_phone_workout(self) -> tuple[str, str]:
        """Verify workout was recorded in StrongLifts on the phone.

        Returns:
            Tuple of (status, message) where status is one of:
            - "verified": Workout confirmed on phone.
            - "not_verified": Phone connected but no workout found.
            - "no_phone": No phone connected via ADB.
            - "error": Could not access StrongLifts database.
        """
        if not self._is_phone_connected():
            return "no_phone", "No phone connected via ADB"
        local_db = self._pull_stronglifts_db()
        if local_db is None:
            return "error", "StrongLifts database not found on phone"
        count = self._count_today_workouts(local_db)
        if count > 0:
            return (
                "verified",
                f"Workout verified! ({count} session(s) found on phone)",
            )
        return "not_verified", "No workout found on phone today"

    def _attempt_unlock(self) -> None:
        """Unlock screen after workout form submission."""
        self.unlock_screen()

    def _show_phone_penalty(
        self, message: str, *, on_done: Callable[[], None] | None = None
    ) -> None:
        """Show penalty countdown when phone verification is unavailable."""
        self.clear_container()
        self._phone_penalty_done_fn: Callable[[], None] = (
            on_done if on_done is not None else self.unlock_screen
        )
        delay = (
            PHONE_PENALTY_DELAY_DEMO
            if self.demo_mode
            else PHONE_PENALTY_DELAY_PRODUCTION
        )
        self._label(
            "Cannot Verify Workout",
            font_size=36,
            color="#ff8800",
            pady=20,
        )
        self._text(message, color="#ffaa00")
        self._text(
            "Connect phone via ADB to skip this wait,\n"
            "or wait for the penalty timer.\n\n"
            "Note: Phone must be rooted and StrongLifts installed.",
            font_size=18,
        )
        self.phone_penalty_remaining = delay
        self.phone_penalty_label = self._label(
            str(delay),
            font_size=80,
            pady=20,
        )
        self._update_phone_penalty()

    def _update_phone_penalty(self) -> None:
        """Update phone penalty countdown."""
        if self.phone_penalty_remaining > 0:
            self.phone_penalty_label.config(
                text=str(self.phone_penalty_remaining),
            )
            self.phone_penalty_remaining -= 1
            self.root.after(1000, self._update_phone_penalty)
        else:
            self._phone_penalty_done_fn()

    # ------------------------------------------------------------------
    # Submit timer and entry checking
    # ------------------------------------------------------------------

    def _tick_submit_timer(self) -> None:
        """Decrement submit timer and schedule next tick."""
        self.timer_label.config(
            text=f"Submit available in {self.submit_unlock_time} seconds...",
        )
        self.submit_unlock_time -= 1
        self.root.after(1000, self.update_submit_timer)

    def _try_enable_submit(self) -> None:
        """Enable submit button if all entries are filled."""
        all_filled = all(entry.get().strip() for entry in self.entries_to_check)
        if all_filled:
            self.submit_btn.config(
                text="SUBMIT",
                state="normal",
                bg="#00aa00",
                command=self.submit_command,
            )
            self.timer_label.config(text="You can now submit!")
        else:
            self.timer_label.config(text="Fill all fields to enable submit")
            self.root.after(1000, self.check_entries_filled)

    def update_submit_timer(self) -> None:
        """Update countdown timer and check if submit can be enabled."""
        with contextlib.suppress(tk.TclError):
            if self.submit_unlock_time > 0:
                self._tick_submit_timer()
            else:
                self._try_enable_submit()

    def check_entries_filled(self) -> None:
        """Continuously check if entries are filled after timer expires."""
        with contextlib.suppress(tk.TclError):
            self._try_enable_submit()

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
