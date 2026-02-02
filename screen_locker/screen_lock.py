#!/usr/bin/env python3
"""Screen locker with workout verification for Arch Linux / i3wm.

Requires user to log their workout to unlock the screen.
"""

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import subprocess
import sys
import tkinter as tk

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
SHUTDOWN_CONFIG_FILE = Path("/etc/shutdown-schedule.conf")
# Table tennis minimum requirements (harder to fake)
MIN_TABLE_TENNIS_SETS = 15
MIN_POINTS_PER_SET = 11  # Standard table tennis minimum points to win a set
TABLE_TENNIS_SUBMIT_DELAY = 60  # 60 seconds delay for table tennis
# Helper script path (relative to this file)
ADJUST_SHUTDOWN_SCRIPT = Path(__file__).resolve().parent / "adjust_shutdown_schedule.sh"
# State file to track sick day usage and original config values
SICK_DAY_STATE_FILE = Path(__file__).resolve().parent / "sick_day_state.json"


class ScreenLocker:
    """Screen locker that requires workout logging to unlock."""

    def __init__(self, *, demo_mode: bool = True) -> None:
        """Initialize screen locker with optional demo mode."""
        # Set up log file path
        script_dir = Path(__file__).resolve().parent
        self.log_file = script_dir / "workout_log.json"

        # Check if already logged today
        if self.has_logged_today():
            _logger.info("Workout already logged today. Skipping screen lock.")
            sys.exit(0)

        self.root = tk.Tk()
        self.root.title("Workout Locker" + (" [DEMO MODE]" if demo_mode else ""))
        self.demo_mode = demo_mode
        self.lockout_time = (
            10 if demo_mode else 1800
        )  # 10 seconds for demo, 30 minutes for production
        self.workout_data: dict[str, str] = {}

        # Get total screen dimensions across all monitors
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()

        # Override redirect to bypass window manager (needed for multi-monitor spanning)
        self.root.overrideredirect(True)

        # Position window at 0,0 and span all monitors
        self.root.geometry(f"{screen_width}x{screen_height}+0+0")

        # Make window fullscreen and on top
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#1a1a1a", cursor="arrow")

        if demo_mode:
            # Demo mode: only close button allowed
            # Add close button in top-left corner
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

        # Create main container
        self.container = tk.Frame(self.root, bg="#1a1a1a")
        self.container.place(relx=0.5, rely=0.5, anchor="center")

        # Start with initial question
        self.ask_workout_done()

        # Force window to update and grab input after everything is set up
        self.root.update_idletasks()
        self.root.focus_force()
        self.root.grab_set_global()

    def clear_container(self) -> None:
        """Remove all widgets from the main container."""
        for widget in self.container.winfo_children():
            widget.destroy()

    def ask_workout_done(self) -> None:
        """Display the initial workout question dialog."""
        self.clear_container()

        question = tk.Label(
            self.container,
            text="Did you work out today?",
            font=("Arial", 36, "bold"),
            fg="white",
            bg="#1a1a1a",
        )
        question.pack(pady=30)

        button_frame = tk.Frame(self.container, bg="#1a1a1a")
        button_frame.pack(pady=20)

        yes_btn = tk.Button(
            button_frame,
            text="YES",
            font=("Arial", 24, "bold"),
            bg="#00aa00",
            fg="white",
            width=10,
            command=self.ask_workout_type,
            cursor="hand2" if self.demo_mode else "",
        )
        yes_btn.pack(side="left", padx=20)

        no_btn = tk.Button(
            button_frame,
            text="NO",
            font=("Arial", 24, "bold"),
            bg="#aa0000",
            fg="white",
            width=10,
            command=self.ask_if_sick,
            cursor="hand2" if self.demo_mode else "",
        )
        no_btn.pack(side="left", padx=20)

    def ask_if_sick(self) -> None:
        """Display sick day question dialog."""
        self.clear_container()

        question = tk.Label(
            self.container,
            text="Are you sick?",
            font=("Arial", 36, "bold"),
            fg="white",
            bg="#1a1a1a",
        )
        question.pack(pady=30)

        info_label = tk.Label(
            self.container,
            text="If yes, shutdown time will be moved 1.5 hours earlier",
            font=("Arial", 18),
            fg="#ffaa00",
            bg="#1a1a1a",
        )
        info_label.pack(pady=10)

        button_frame = tk.Frame(self.container, bg="#1a1a1a")
        button_frame.pack(pady=20)

        yes_btn = tk.Button(
            button_frame,
            text="YES (sick)",
            font=("Arial", 24, "bold"),
            bg="#cc6600",
            fg="white",
            width=12,
            command=self.handle_sick_day,
            cursor="hand2" if self.demo_mode else "",
        )
        yes_btn.pack(side="left", padx=20)

        no_btn = tk.Button(
            button_frame,
            text="NO",
            font=("Arial", 24, "bold"),
            bg="#aa0000",
            fg="white",
            width=12,
            command=self.lockout,
            cursor="hand2" if self.demo_mode else "",
        )
        no_btn.pack(side="left", padx=20)

    def handle_sick_day(self) -> None:
        """Handle sick day: adjust shutdown time and start 2-minute wait."""
        self.clear_container()

        # Check if sick mode was already used today (time already adjusted)
        already_adjusted_today = self._sick_mode_used_today()

        if already_adjusted_today:
            # Already adjusted today, just show status and proceed to wait
            status_text = "Shutdown time already adjusted today"
            status_color = "#ffaa00"
        else:
            # First sick mode use today - adjust the shutdown time
            adjustment_success = self._adjust_shutdown_time_earlier()

            if adjustment_success:
                status_text = (
                    "Shutdown time moved 1.5 hours earlier ✓\n(Will revert tomorrow)"
                )
                status_color = "#00aa00"
            else:
                status_text = "Could not adjust shutdown time (check permissions)"
            status_color = "#ff4444"

        title = tk.Label(
            self.container,
            text="Sick Day Mode",
            font=("Arial", 36, "bold"),
            fg="#cc6600",
            bg="#1a1a1a",
        )
        title.pack(pady=20)

        status_label = tk.Label(
            self.container,
            text=status_text,
            font=("Arial", 18),
            fg=status_color,
            bg="#1a1a1a",
        )
        status_label.pack(pady=10)

        wait_label = tk.Label(
            self.container,
            text="Please wait 2 minutes before unlocking...",
            font=("Arial", 24),
            fg="white",
            bg="#1a1a1a",
        )
        wait_label.pack(pady=20)

        self.sick_countdown_label = tk.Label(
            self.container,
            text=str(SICK_LOCKOUT_SECONDS),
            font=("Arial", 80, "bold"),
            fg="white",
            bg="#1a1a1a",
        )
        self.sick_countdown_label.pack(pady=30)

        self.sick_remaining_time = SICK_LOCKOUT_SECONDS
        self._update_sick_countdown()

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

    def _adjust_shutdown_time_earlier(self) -> bool:
        """Adjust shutdown schedule 1.5 hours earlier (stricter).

        This can only be used once per day. Original values are saved and
        automatically restored when checked the next day.

        Returns True if successful, False otherwise.
        """
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

        # Restore original values if there's a state from a previous day
        self._restore_original_config_if_needed()

        # Check if sick mode was already used today (after potential restore)
        if self._sick_mode_used_today():
            _logger.warning("Sick mode already used today")
            return False

        try:
            # Read current config
            config_values = self._read_shutdown_config()
            if config_values is None:
                return False

            mon_wed_hour, thu_sun_hour, morning_end_hour = config_values

            # Save original values FIRST before any modification
            if not self._save_sick_day_state(today, mon_wed_hour, thu_sun_hour):
                _logger.error("Failed to save state - aborting adjustment")
                return False

            # Move shutdown times 1 hour earlier
            new_mon_wed = mon_wed_hour - 1
            new_thu_sun = thu_sun_hour - 1

            # Ensure we don't go below reasonable hours (e.g., not before 18:00)
            new_mon_wed = max(18, new_mon_wed)
            new_thu_sun = max(18, new_thu_sun)

            # Write new config
            return self._write_shutdown_config(
                new_mon_wed, new_thu_sun, morning_end_hour
            )

        except (OSError, ValueError) as e:
            _logger.warning("Failed to adjust shutdown time: %s", e)
            return False

    def _adjust_shutdown_time_later(self) -> bool:
        """Adjust shutdown schedule 1.5 hours later as workout reward.

        This moves the shutdown time later regardless of the initial time,
        so working out even at 21:00 still makes sense.

        Returns True if successful, False otherwise.
        """
        try:
            # Read current config
            config_values = self._read_shutdown_config()
            if config_values is None:
                return False

            mon_wed_hour, thu_sun_hour, morning_end_hour = config_values

            # Move shutdown times 1.5 hours (rounded to 2 hours) later
            new_mon_wed = mon_wed_hour + 2
            new_thu_sun = thu_sun_hour + 2

            # Cap at 23 (11 PM) to avoid going past midnight
            new_mon_wed = min(23, new_mon_wed)
            new_thu_sun = min(23, new_thu_sun)

            # Write new config with restore flag to allow later times
            return self._write_shutdown_config(
                new_mon_wed, new_thu_sun, morning_end_hour, restore=True
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
        self, date: str, orig_mon_wed: int, orig_thu_sun: int
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

    def _restore_original_config_if_needed(self) -> None:
        """Restore original config values if sick day state is from a previous day."""
        if not SICK_DAY_STATE_FILE.exists():
            return

        try:
            with SICK_DAY_STATE_FILE.open() as f:
                state = json.load(f)

            state_date = state.get("date")
            today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

            # Only restore if state is from a previous day
            if state_date and state_date != today:
                orig_mon_wed = state.get("original_mon_wed_hour")
                orig_thu_sun = state.get("original_thu_sun_hour")

                if orig_mon_wed is not None and orig_thu_sun is not None:
                    # Read current morning end hour
                    config_values = self._read_shutdown_config()
                    if config_values:
                        _, _, morning_end_hour = config_values
                        _logger.info(
                            "Restoring original shutdown config from %s", state_date
                        )
                        self._write_shutdown_config(
                            orig_mon_wed, orig_thu_sun, morning_end_hour, restore=True
                        )

                # Remove stale state file
                SICK_DAY_STATE_FILE.unlink()
                _logger.info("Removed stale sick day state from %s", state_date)

        except (OSError, json.JSONDecodeError) as e:
            _logger.warning("Error checking sick day state: %s", e)

    def _read_shutdown_config(self) -> tuple[int, int, int] | None:
        """Read current shutdown config values.

        Returns tuple of (mon_wed_hour, thu_sun_hour, morning_end_hour) or None.
        """
        if not SHUTDOWN_CONFIG_FILE.exists():
            _logger.warning("Shutdown config file not found: %s", SHUTDOWN_CONFIG_FILE)
            return None

        mon_wed_hour = None
        thu_sun_hour = None
        morning_end_hour = None

        with SHUTDOWN_CONFIG_FILE.open() as f:
            for config_line in f:
                stripped_line = config_line.strip()
                if stripped_line.startswith("MON_WED_HOUR="):
                    mon_wed_hour = int(stripped_line.split("=")[1])
                elif stripped_line.startswith("THU_SUN_HOUR="):
                    thu_sun_hour = int(stripped_line.split("=")[1])
                elif stripped_line.startswith("MORNING_END_HOUR="):
                    morning_end_hour = int(stripped_line.split("=")[1])

        if mon_wed_hour is None or thu_sun_hour is None or morning_end_hour is None:
            _logger.warning("Shutdown config missing required values")
            return None

        return (mon_wed_hour, thu_sun_hour, morning_end_hour)

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
            restore: If True, allows restoring to later times (for reverting sick day).

        Returns True if successful, False otherwise.
        """
        if not ADJUST_SHUTDOWN_SCRIPT.exists():
            _logger.warning(
                "Adjust shutdown script not found: %s", ADJUST_SHUTDOWN_SCRIPT
            )
            return False

        cmd = ["/usr/bin/sudo", str(ADJUST_SHUTDOWN_SCRIPT)]
        if restore:
            cmd.append("--restore")
        cmd.extend([str(mon_wed_hour), str(thu_sun_hour), str(morning_end_hour)])

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
            "Adjusted shutdown hours: Mon-Wed=%d, Thu-Sun=%d. Output: %s",
            mon_wed_hour,
            thu_sun_hour,
            result.stdout.strip(),
        )
        return True
        return True

    def lockout(self) -> None:
        """Display lockout screen with countdown timer."""
        self.clear_container()

        self.lockout_label = tk.Label(
            self.container,
            text=f"Go work out!\nLocked for {self.lockout_time} seconds",
            font=("Arial", 48, "bold"),
            fg="#ff4444",
            bg="#1a1a1a",
        )
        self.lockout_label.pack(pady=30)

        self.countdown_label = tk.Label(
            self.container,
            text=str(self.lockout_time),
            font=("Arial", 120, "bold"),
            fg="white",
            bg="#1a1a1a",
        )
        self.countdown_label.pack(pady=30)

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

    def ask_workout_type(self) -> None:
        """Display workout type selection dialog."""
        self.clear_container()

        question = tk.Label(
            self.container,
            text="What type of workout?",
            font=("Arial", 36, "bold"),
            fg="white",
            bg="#1a1a1a",
        )
        question.pack(pady=30)

        button_frame = tk.Frame(self.container, bg="#1a1a1a")
        button_frame.pack(pady=20)

        # Running option removed - too easy to fake

        strength_btn = tk.Button(
            button_frame,
            text="STRENGTH",
            font=("Arial", 24, "bold"),
            bg="#cc6600",
            fg="white",
            width=12,
            command=self.ask_strength_details,
            cursor="hand2" if self.demo_mode else "",
        )
        strength_btn.pack(side="left", padx=20)

        table_tennis_btn = tk.Button(
            button_frame,
            text="TABLE TENNIS",
            font=("Arial", 20, "bold"),
            bg="#00cc66",
            fg="white",
            width=12,
            command=self.ask_table_tennis_details,
            cursor="hand2" if self.demo_mode else "",
        )
        table_tennis_btn.pack(side="left", padx=20)

    def ask_running_details(self) -> None:
        """Display running workout input form."""
        self.clear_container()
        self.workout_data["type"] = "running"

        title = tk.Label(
            self.container,
            text="Running Details",
            font=("Arial", 36, "bold"),
            fg="white",
            bg="#1a1a1a",
        )
        title.pack(pady=20)

        # Distance
        dist_frame = tk.Frame(self.container, bg="#1a1a1a")
        dist_frame.pack(pady=10)
        tk.Label(
            dist_frame,
            text="Distance (km):",
            font=("Arial", 20),
            fg="white",
            bg="#1a1a1a",
        ).pack(side="left", padx=10)
        self.distance_entry = tk.Entry(dist_frame, font=("Arial", 20), width=10)
        self.distance_entry.pack(side="left", padx=10)

        # Time
        time_frame = tk.Frame(self.container, bg="#1a1a1a")
        time_frame.pack(pady=10)
        tk.Label(
            time_frame,
            text="Time (minutes):",
            font=("Arial", 20),
            fg="white",
            bg="#1a1a1a",
        ).pack(side="left", padx=10)
        self.time_entry = tk.Entry(time_frame, font=("Arial", 20), width=10)
        self.time_entry.pack(side="left", padx=10)

        # Pace
        pace_frame = tk.Frame(self.container, bg="#1a1a1a")
        pace_frame.pack(pady=10)
        tk.Label(
            pace_frame,
            text="Pace (min/km):",
            font=("Arial", 20),
            fg="white",
            bg="#1a1a1a",
        ).pack(side="left", padx=10)
        self.pace_entry = tk.Entry(pace_frame, font=("Arial", 20), width=10)
        self.pace_entry.pack(side="left", padx=10)

        # Timer countdown label
        self.timer_label = tk.Label(
            self.container, text="", font=("Arial", 16), fg="#ffaa00", bg="#1a1a1a"
        )
        self.timer_label.pack(pady=10)

        self.submit_btn = tk.Button(
            self.container,
            text="SUBMIT (locked)",
            font=("Arial", 24, "bold"),
            bg="#666666",
            fg="white",
            width=15,
            state="disabled",
            cursor="hand2" if self.demo_mode else "",
        )
        self.submit_btn.pack(pady=10)

        # Back button
        back_btn = tk.Button(
            self.container,
            text="← BACK",
            font=("Arial", 18),
            bg="#666666",
            fg="white",
            width=15,
            command=self.ask_workout_type,
            cursor="hand2" if self.demo_mode else "",
        )
        back_btn.pack(pady=10)

        # Start 30 second timer
        self.submit_unlock_time = 30
        self.entries_to_check = [self.distance_entry, self.time_entry, self.pace_entry]
        self.submit_command = self.verify_running_data
        self.update_submit_timer()

    def verify_running_data(self) -> None:
        """Validate running workout data and unlock if valid."""
        try:
            distance = float(self.distance_entry.get())
            time_mins = float(self.time_entry.get())
            pace = float(self.pace_entry.get())

            # Sanity checks
            if distance <= 0 or distance > MAX_DISTANCE_KM:
                self.show_error(f"Distance seems unrealistic (0-{MAX_DISTANCE_KM} km)")
                return

            if time_mins <= 0 or time_mins > MAX_TIME_MINUTES:
                self.show_error(
                    f"Time seems unrealistic (0-{MAX_TIME_MINUTES} minutes)"
                )
                return

            if pace <= 0 or pace > MAX_PACE_MIN_PER_KM:
                self.show_error(
                    f"Pace seems unrealistic (0-{MAX_PACE_MIN_PER_KM} min/km)"
                )
                return

            # Calculate expected pace and check if close enough
            expected_pace = time_mins / distance
            pace_diff = abs(pace - expected_pace)
            tolerance = expected_pace * 0.15  # 15% tolerance

            if pace_diff > tolerance:
                self.show_error(
                    f"Pace doesn't match! "
                    f"Expected ~{expected_pace:.2f} min/km, got {pace:.2f}"
                )
                return

            # Data looks good - store full data
            self.workout_data["distance_km"] = str(distance)
            self.workout_data["time_minutes"] = str(time_mins)
            self.workout_data["pace_min_per_km"] = str(pace)
            self.unlock_screen()

        except ValueError:
            self.show_error("Please enter valid numbers")

    def ask_strength_details(self) -> None:
        """Display strength training input form."""
        self.clear_container()
        self.workout_data["type"] = "strength"

        title = tk.Label(
            self.container,
            text="Strength Training Details",
            font=("Arial", 36, "bold"),
            fg="white",
            bg="#1a1a1a",
        )
        title.pack(pady=20)

        # Exercises
        ex_frame = tk.Frame(self.container, bg="#1a1a1a")
        ex_frame.pack(pady=10)
        tk.Label(
            ex_frame,
            text="Exercises (comma-separated):",
            font=("Arial", 18),
            fg="white",
            bg="#1a1a1a",
        ).pack(side="left", padx=10)
        self.exercises_entry = tk.Entry(ex_frame, font=("Arial", 18), width=50)
        self.exercises_entry.pack(side="left", padx=10)

        # Sets per exercise
        sets_frame = tk.Frame(self.container, bg="#1a1a1a")
        sets_frame.pack(pady=10)
        tk.Label(
            sets_frame,
            text="Sets per exercise (comma-separated):",
            font=("Arial", 18),
            fg="white",
            bg="#1a1a1a",
        ).pack(side="left", padx=10)
        self.sets_entry = tk.Entry(sets_frame, font=("Arial", 18), width=20)
        self.sets_entry.pack(side="left", padx=10)

        # Reps per set (can be variable, e.g., "12+12+11+11+12" for one exercise)
        reps_frame = tk.Frame(self.container, bg="#1a1a1a")
        reps_frame.pack(pady=10)
        tk.Label(
            reps_frame,
            text="Reps (comma-sep, use + for variable: 12+11+12):",
            font=("Arial", 18),
            fg="white",
            bg="#1a1a1a",
        ).pack(side="left", padx=10)
        self.reps_entry = tk.Entry(reps_frame, font=("Arial", 18), width=30)
        self.reps_entry.pack(side="left", padx=10)

        # Weights
        weights_frame = tk.Frame(self.container, bg="#1a1a1a")
        weights_frame.pack(pady=10)
        tk.Label(
            weights_frame,
            text="Weight per exercise in kg (comma-separated):",
            font=("Arial", 18),
            fg="white",
            bg="#1a1a1a",
        ).pack(side="left", padx=10)
        self.weights_entry = tk.Entry(weights_frame, font=("Arial", 18), width=20)
        self.weights_entry.pack(side="left", padx=10)

        # Total weight lifted
        total_frame = tk.Frame(self.container, bg="#1a1a1a")
        total_frame.pack(pady=10)
        tk.Label(
            total_frame,
            text="Total weight lifted (kg):",
            font=("Arial", 18),
            fg="white",
            bg="#1a1a1a",
        ).pack(side="left", padx=10)
        self.total_weight_entry = tk.Entry(total_frame, font=("Arial", 18), width=15)
        self.total_weight_entry.pack(side="left", padx=10)

        # Timer countdown label
        self.timer_label = tk.Label(
            self.container, text="", font=("Arial", 16), fg="#ffaa00", bg="#1a1a1a"
        )
        self.timer_label.pack(pady=10)

        self.submit_btn = tk.Button(
            self.container,
            text="SUBMIT (locked)",
            font=("Arial", 24, "bold"),
            bg="#666666",
            fg="white",
            width=15,
            state="disabled",
            cursor="hand2" if self.demo_mode else "",
        )
        self.submit_btn.pack(pady=10)

        # Back button
        back_btn = tk.Button(
            self.container,
            text="← BACK",
            font=("Arial", 18),
            bg="#666666",
            fg="white",
            width=15,
            command=self.ask_workout_type,
            cursor="hand2" if self.demo_mode else "",
        )
        back_btn.pack(pady=10)

        # Start 30 second timer
        self.submit_unlock_time = 30
        self.entries_to_check = [
            self.exercises_entry,
            self.sets_entry,
            self.reps_entry,
            self.weights_entry,
            self.total_weight_entry,
        ]
        self.submit_command = self.verify_strength_data
        self.update_submit_timer()

    def ask_table_tennis_details(self) -> None:
        """Display table tennis workout input form."""
        self.clear_container()
        self.workout_data["type"] = "table_tennis"

        title = tk.Label(
            self.container,
            text="Table Tennis Details",
            font=("Arial", 36, "bold"),
            fg="white",
            bg="#1a1a1a",
        )
        title.pack(pady=20)

        # Instructions/Requirements
        requirements = tk.Label(
            self.container,
            text=(
                f"Requirements: Minimum {MIN_TABLE_TENNIS_SETS} sets, "
                f"each set needs at least {MIN_POINTS_PER_SET} total points"
            ),
            font=("Arial", 14),
            fg="#aaaaaa",
            bg="#1a1a1a",
        )
        requirements.pack(pady=5)

        # Duration
        duration_frame = tk.Frame(self.container, bg="#1a1a1a")
        duration_frame.pack(pady=10)
        tk.Label(
            duration_frame,
            text="Duration (minutes):",
            font=("Arial", 20),
            fg="white",
            bg="#1a1a1a",
        ).pack(side="left", padx=10)
        self.tt_duration_entry = tk.Entry(duration_frame, font=("Arial", 20), width=10)
        self.tt_duration_entry.pack(side="left", padx=10)

        # Sets played
        sets_frame = tk.Frame(self.container, bg="#1a1a1a")
        sets_frame.pack(pady=10)
        tk.Label(
            sets_frame,
            text="Sets played:",
            font=("Arial", 20),
            fg="white",
            bg="#1a1a1a",
        ).pack(side="left", padx=10)
        self.tt_sets_entry = tk.Entry(sets_frame, font=("Arial", 20), width=10)
        self.tt_sets_entry.pack(side="left", padx=10)

        # Points won
        won_frame = tk.Frame(self.container, bg="#1a1a1a")
        won_frame.pack(pady=10)
        tk.Label(
            won_frame,
            text="Points won:",
            font=("Arial", 20),
            fg="white",
            bg="#1a1a1a",
        ).pack(side="left", padx=10)
        self.tt_won_entry = tk.Entry(won_frame, font=("Arial", 20), width=10)
        self.tt_won_entry.pack(side="left", padx=10)

        # Points lost
        lost_frame = tk.Frame(self.container, bg="#1a1a1a")
        lost_frame.pack(pady=10)
        tk.Label(
            lost_frame,
            text="Points lost:",
            font=("Arial", 20),
            fg="white",
            bg="#1a1a1a",
        ).pack(side="left", padx=10)
        self.tt_lost_entry = tk.Entry(lost_frame, font=("Arial", 20), width=10)
        self.tt_lost_entry.pack(side="left", padx=10)

        # Timer countdown label
        self.timer_label = tk.Label(
            self.container, text="", font=("Arial", 16), fg="#ffaa00", bg="#1a1a1a"
        )
        self.timer_label.pack(pady=10)

        self.submit_btn = tk.Button(
            self.container,
            text="SUBMIT (locked)",
            font=("Arial", 24, "bold"),
            bg="#666666",
            fg="white",
            width=15,
            state="disabled",
            cursor="hand2" if self.demo_mode else "",
        )
        self.submit_btn.pack(pady=10)

        # Back button
        back_btn = tk.Button(
            self.container,
            text="← BACK",
            font=("Arial", 18),
            bg="#666666",
            fg="white",
            width=15,
            command=self.ask_workout_type,
            cursor="hand2" if self.demo_mode else "",
        )
        back_btn.pack(pady=10)

        # Start 60 second timer (increased from 30)
        self.submit_unlock_time = TABLE_TENNIS_SUBMIT_DELAY
        self.entries_to_check = [
            self.tt_duration_entry,
            self.tt_sets_entry,
            self.tt_won_entry,
            self.tt_lost_entry,
        ]
        self.submit_command = self.verify_table_tennis_data
        self.update_submit_timer()

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
        self, exercises: list[str], sets: list[int], reps: list[list[int]]
    ) -> str | None:
        """Validate reps data. Returns error message or None if valid."""
        for i, rep_list in enumerate(reps):
            if any(r < 1 or r > MAX_REPS for r in rep_list):
                return f"Reps should be between 1-{MAX_REPS}"
            if len(rep_list) > 1 and len(rep_list) != sets[i]:
                return (
                    f"For '{exercises[i]}': variable reps count ({len(rep_list)}) "
                    f"doesn't match sets ({sets[i]})"
                )
        return None

    def _calculate_expected_total(
        self, sets: list[int], reps: list[list[int]], weights: list[float]
    ) -> float:
        """Calculate expected total weight lifted."""
        expected_total = 0.0
        for i, rep_list in enumerate(reps):
            if len(rep_list) == 1:
                expected_total += sets[i] * rep_list[0] * weights[i]
            else:
                expected_total += sum(rep_list) * weights[i]
        return expected_total

    def verify_strength_data(self) -> None:
        """Validate strength workout data and unlock if valid."""
        try:
            exercises = [e.strip() for e in self.exercises_entry.get().split(",")]
            sets = [int(s.strip()) for s in self.sets_entry.get().split(",")]
            reps_raw = [r.strip() for r in self.reps_entry.get().split(",")]
            reps = self._parse_reps(reps_raw)
            weights = [float(w.strip()) for w in self.weights_entry.get().split(",")]
            total_weight = float(self.total_weight_entry.get())

            error = self._validate_strength_inputs(exercises, sets, reps, weights)
            if error:
                self.show_error(error)
                return

            expected_total = self._calculate_expected_total(sets, reps, weights)
            weight_diff = abs(total_weight - expected_total)
            tolerance = expected_total * 0.15  # 15% tolerance

            if weight_diff > tolerance:
                self.show_error(
                    f"Total weight doesn't match! "
                    f"Expected ~{expected_total:.1f} kg, got {total_weight:.1f}"
                )
                return

            # Data looks good - store full data
            self.workout_data["exercises"] = exercises
            self.workout_data["sets"] = [str(s) for s in sets]
            self.workout_data["reps"] = [
                "+".join(str(r) for r in rep_list) for rep_list in reps
            ]
            self.workout_data["weights_kg"] = [str(w) for w in weights]
            self.workout_data["total_weight_kg"] = str(total_weight)
            self.unlock_screen()

        except ValueError:
            self.show_error("Please enter valid data in correct format")

    def verify_table_tennis_data(self) -> None:
        """Validate table tennis workout data and unlock if valid."""
        try:
            duration = float(self.tt_duration_entry.get())
            sets_played = int(self.tt_sets_entry.get())
            points_won = int(self.tt_won_entry.get())
            points_lost = int(self.tt_lost_entry.get())

            # Basic validation
            if duration <= 0:
                self.show_error("Duration must be greater than 0 minutes")
                return
            if sets_played <= 0:
                self.show_error("Sets played must be greater than 0")
                return
            if points_won < 0 or points_lost < 0:
                self.show_error("Points cannot be negative")
                return
            if points_won + points_lost == 0:
                self.show_error("You must have played some points")
                return

            # Stricter validation - minimum sets requirement
            if sets_played < MIN_TABLE_TENNIS_SETS:
                self.show_error(
                    f"Minimum {MIN_TABLE_TENNIS_SETS} sets required for a valid workout"
                )
                return

            # Mathematical cross-check: total_points >= sets_played * MIN_POINTS_PER_SET
            total_points = points_won + points_lost
            min_expected_points = sets_played * MIN_POINTS_PER_SET
            if total_points < min_expected_points:
                self.show_error(
                    f"Invalid data: {sets_played} sets needs "
                    f"at least {min_expected_points} total points "
                    f"(min {MIN_POINTS_PER_SET} per set). "
                    f"You entered {total_points}."
                )
                return

            # Reasonable duration check: at least 2 minutes per set
            min_expected_duration = sets_played * 2
            if duration < min_expected_duration:
                self.show_error(
                    f"Duration too short: {sets_played} sets should "
                    f"take at least {min_expected_duration} minutes"
                )
                return

            # Ask verification question about the data
            self.ask_table_tennis_verification(
                duration, sets_played, points_won, points_lost
            )

        except ValueError:
            self.show_error("Please enter valid numbers")

    def ask_table_tennis_verification(
        self, duration: float, sets_played: int, points_won: int, points_lost: int
    ) -> None:
        """Ask a math verification question about the entered data."""
        import random

        self.clear_container()

        # Store data for later submission
        self._pending_tt_data = {
            "duration": duration,
            "sets_played": sets_played,
            "points_won": points_won,
            "points_lost": points_lost,
        }

        # Generate a random verification question based on their data
        total_points = points_won + points_lost
        question_types = [
            (
                "total_points",
                "What is the TOTAL number of points played? (won + lost)",
                total_points,
            ),
            (
                "avg_per_set",
                "Rounded DOWN: what is the average points per set? (total ÷ sets)",
                total_points // sets_played,
            ),
            (
                "point_diff",
                "What is the difference between won and lost points? (won - lost)",
                abs(points_won - points_lost),
            ),
        ]

        question_type, question_text, expected_answer = random.choice(question_types)
        self._tt_expected_answer = expected_answer
        self._tt_question_type = question_type

        title = tk.Label(
            self.container,
            text="🔢 Verification Question",
            font=("Arial", 30, "bold"),
            fg="white",
            bg="#1a1a1a",
        )
        title.pack(pady=20)

        info = tk.Label(
            self.container,
            text=(
                f"Based on your data: {sets_played} sets, "
                f"{points_won} won, {points_lost} lost"
            ),
            font=("Arial", 16),
            fg="#aaaaaa",
            bg="#1a1a1a",
        )
        info.pack(pady=10)

        question = tk.Label(
            self.container,
            text=question_text,
            font=("Arial", 20, "bold"),
            fg="#ffaa00",
            bg="#1a1a1a",
        )
        question.pack(pady=20)

        answer_frame = tk.Frame(self.container, bg="#1a1a1a")
        answer_frame.pack(pady=10)
        tk.Label(
            answer_frame,
            text="Your answer:",
            font=("Arial", 20),
            fg="white",
            bg="#1a1a1a",
        ).pack(side="left", padx=10)
        self.tt_verify_entry = tk.Entry(answer_frame, font=("Arial", 20), width=10)
        self.tt_verify_entry.pack(side="left", padx=10)
        self.tt_verify_entry.focus_set()

        submit_btn = tk.Button(
            self.container,
            text="VERIFY & SUBMIT",
            font=("Arial", 24, "bold"),
            bg="#00aa00",
            fg="white",
            width=15,
            command=self.verify_table_tennis_answer,
            cursor="hand2" if self.demo_mode else "",
        )
        submit_btn.pack(pady=20)

        # Back button
        back_btn = tk.Button(
            self.container,
            text="← BACK",
            font=("Arial", 18),
            bg="#666666",
            fg="white",
            width=15,
            command=self.ask_table_tennis_details,
            cursor="hand2" if self.demo_mode else "",
        )
        back_btn.pack(pady=10)

    def verify_table_tennis_answer(self) -> None:
        """Check the verification answer and unlock if correct."""
        try:
            user_answer = int(self.tt_verify_entry.get())
            if user_answer != self._tt_expected_answer:
                self.show_error(
                    f"Incorrect! The answer was {self._tt_expected_answer}. "
                    "Did you enter accurate data?"
                )
                # Go back to input form
                self.root.after(2000, self.ask_table_tennis_details)
                return

            # Answer correct - store data and unlock
            data = self._pending_tt_data
            self.workout_data["duration_minutes"] = str(data["duration"])
            self.workout_data["sets_played"] = str(data["sets_played"])
            self.workout_data["points_won"] = str(data["points_won"])
            self.workout_data["points_lost"] = str(data["points_lost"])
            self.unlock_screen()

        except ValueError:
            self.show_error("Please enter a valid number")

    def update_submit_timer(self) -> None:
        """Update countdown timer and check if submit can be enabled."""
        # Check if widgets still exist (user might have clicked back)
        try:
            if self.submit_unlock_time > 0:
                self.timer_label.config(
                    text=f"Submit available in {self.submit_unlock_time} seconds..."
                )
                self.submit_unlock_time -= 1
                self.root.after(1000, self.update_submit_timer)
            else:
                # Timer finished, check if all entries have data
                all_filled = all(entry.get().strip() for entry in self.entries_to_check)

                if all_filled:
                    # Enable submit button
                    self.submit_btn.config(
                        text="SUBMIT",
                        state="normal",
                        bg="#00aa00",
                        command=self.submit_command,
                    )
                    self.timer_label.config(text="You can now submit!")
                else:
                    # Check again in 1 second
                    self.timer_label.config(text="Fill all fields to enable submit")
                    self.root.after(1000, self.check_entries_filled)
        except tk.TclError:
            # Widgets were destroyed (user clicked back), stop the timer
            pass

    def check_entries_filled(self) -> None:
        """Continuously check if entries are filled after timer expires."""
        try:
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
        except tk.TclError:
            # Widgets were destroyed (user clicked back), stop checking
            pass

    def show_error(self, message: str) -> None:
        """Display error message with retry option."""
        self.clear_container()

        error_label = tk.Label(
            self.container,
            text="ERROR",
            font=("Arial", 48, "bold"),
            fg="#ff4444",
            bg="#1a1a1a",
        )
        error_label.pack(pady=20)

        msg_label = tk.Label(
            self.container,
            text=message,
            font=("Arial", 24),
            fg="white",
            bg="#1a1a1a",
            wraplength=800,
        )
        msg_label.pack(pady=20)

        retry_btn = tk.Button(
            self.container,
            text="TRY AGAIN",
            font=("Arial", 24, "bold"),
            bg="#0066cc",
            fg="white",
            width=15,
            command=self.ask_workout_done,
            cursor="hand2" if self.demo_mode else "",
        )
        retry_btn.pack(pady=30)

    def unlock_screen(self) -> None:
        """Save workout log and display success message."""
        # Save workout data to log
        self.save_workout_log()

        # Adjust shutdown time later for actual workouts (not sick days)
        shutdown_adjusted = False
        workout_type = self.workout_data.get("type", "")
        if workout_type in ("running", "strength", "table_tennis"):
            shutdown_adjusted = self._adjust_shutdown_time_later()
            if shutdown_adjusted:
                _logger.info("Shutdown time moved 1.5 hours later as workout reward")

        self.clear_container()

        success_label = tk.Label(
            self.container,
            text="Great job! 💪",
            font=("Arial", 48, "bold"),
            fg="#00ff00",
            bg="#1a1a1a",
        )
        success_label.pack(pady=30)

        # Show shutdown adjustment status
        if shutdown_adjusted:
            bonus_label = tk.Label(
                self.container,
                text="Shutdown time +1.5h later! 🎁",
                font=("Arial", 24),
                fg="#ffaa00",
                bg="#1a1a1a",
            )
            bonus_label.pack(pady=10)

        unlock_label = tk.Label(
            self.container,
            text="Screen Unlocked!",
            font=("Arial", 36),
            fg="white",
            bg="#1a1a1a",
        )
        unlock_label.pack(pady=20)

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

    def save_workout_log(self) -> None:
        """Save workout data to log file."""
        # Load existing logs
        logs = {}
        if self.log_file.exists():
            try:
                with self.log_file.open() as f:
                    logs = json.load(f)
            except (OSError, json.JSONDecodeError):
                logs = {}

        # Add today's workout
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        logs[today] = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "workout_data": self.workout_data,
        }

        # Save updated logs
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
