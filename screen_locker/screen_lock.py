#!/usr/bin/env python3
"""Screen locker with workout verification for Arch Linux / i3wm.

Requires user to log their workout to unlock the screen.
"""

from datetime import datetime, timezone
import json
import logging
import os
import sys
import tkinter as tk

logging.basicConfig(level=logging.INFO)

# Validation limits for workout data
MAX_DISTANCE_KM = 100
MAX_TIME_MINUTES = 600
MAX_PACE_MIN_PER_KM = 20
MIN_EXERCISE_NAME_LEN = 3
MAX_SETS = 20
MAX_REPS = 100
MAX_WEIGHT_KG = 500


class ScreenLocker:
    """Screen locker that requires workout logging to unlock."""

    def __init__(self, *, demo_mode: bool = True) -> None:
        """Initialize screen locker with optional demo mode."""
        # Set up log file path
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.log_file = os.path.join(script_dir, "workout_log.json")

        # Check if already logged today
        if self.has_logged_today():
            logging.info("Workout already logged today. Skipping screen lock.")
            sys.exit(0)

        self.root = tk.Tk()
        self.root.title("Workout Locker" + (" [DEMO MODE]" if demo_mode else ""))
        self.demo_mode = demo_mode
        self.lockout_time = (
            10 if demo_mode else 1800
        )  # 10 seconds for demo, 30 minutes for production
        self.workout_data = {}

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
            command=self.lockout,
            cursor="hand2" if self.demo_mode else "",
        )
        no_btn.pack(side="left", padx=20)

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

        running_btn = tk.Button(
            button_frame,
            text="RUNNING",
            font=("Arial", 24, "bold"),
            bg="#0066cc",
            fg="white",
            width=15,
            command=self.ask_running_details,
            cursor="hand2" if self.demo_mode else "",
        )
        running_btn.pack(side="left", padx=20)

        strength_btn = tk.Button(
            button_frame,
            text="STRENGTH",
            font=("Arial", 24, "bold"),
            bg="#cc6600",
            fg="white",
            width=15,
            command=self.ask_strength_details,
            cursor="hand2" if self.demo_mode else "",
        )
        strength_btn.pack(side="left", padx=20)

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

            # Data looks good
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
        self.exercises_entry = tk.Entry(ex_frame, font=("Arial", 18), width=30)
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

        # Reps per set
        reps_frame = tk.Frame(self.container, bg="#1a1a1a")
        reps_frame.pack(pady=10)
        tk.Label(
            reps_frame,
            text="Reps per set (comma-separated):",
            font=("Arial", 18),
            fg="white",
            bg="#1a1a1a",
        ).pack(side="left", padx=10)
        self.reps_entry = tk.Entry(reps_frame, font=("Arial", 18), width=20)
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

    def verify_strength_data(self) -> None:
        """Validate strength workout data and unlock if valid."""
        try:
            exercises = [e.strip() for e in self.exercises_entry.get().split(",")]
            sets = [int(s.strip()) for s in self.sets_entry.get().split(",")]
            reps = [int(r.strip()) for r in self.reps_entry.get().split(",")]
            weights = [float(w.strip()) for w in self.weights_entry.get().split(",")]
            total_weight = float(self.total_weight_entry.get())

            # Check all lists have same length
            if not (len(exercises) == len(sets) == len(reps) == len(weights)):
                self.show_error(
                    "Number of exercises, sets, reps, and weights must match"
                )
                return

            # Check for empty or lazy entries
            if any(len(ex) < MIN_EXERCISE_NAME_LEN for ex in exercises):
                self.show_error("Exercise names too short - be specific")
                return

            # Sanity checks
            if any(s < 1 or s > MAX_SETS for s in sets):
                self.show_error(f"Sets should be between 1-{MAX_SETS}")
                return

            if any(r < 1 or r > MAX_REPS for r in reps):
                self.show_error(f"Reps should be between 1-{MAX_REPS}")
                return

            if any(w < 0 or w > MAX_WEIGHT_KG for w in weights):
                self.show_error(f"Weights should be between 0-{MAX_WEIGHT_KG} kg")
                return

            # Calculate expected total weight
            expected_total = sum(
                sets[i] * reps[i] * weights[i] for i in range(len(exercises))
            )
            weight_diff = abs(total_weight - expected_total)
            tolerance = expected_total * 0.15  # 15% tolerance

            if weight_diff > tolerance:
                self.show_error(
                    f"Total weight doesn't match! "
                    f"Expected ~{expected_total:.1f} kg, got {total_weight:.1f}"
                )
                return

            # Data looks good
            self.unlock_screen()

        except ValueError:
            self.show_error("Please enter valid data in correct format")

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

        self.clear_container()

        success_label = tk.Label(
            self.container,
            text="Great job! 💪",
            font=("Arial", 48, "bold"),
            fg="#00ff00",
            bg="#1a1a1a",
        )
        success_label.pack(pady=30)

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
        if not os.path.exists(self.log_file):
            return False

        try:
            with open(self.log_file) as f:
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
        if os.path.exists(self.log_file):
            try:
                with open(self.log_file) as f:
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
            with open(self.log_file, "w") as f:
                json.dump(logs, f, indent=2)
        except OSError as e:
            logging.warning(f"Could not save workout log: {e}")

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
