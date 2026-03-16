"""Workout form methods mixin for the screen locker."""

from __future__ import annotations

from typing import TYPE_CHECKING

from python_pkg.screen_locker._constants import (
    MAX_DISTANCE_KM,
    MAX_PACE_MIN_PER_KM,
    MAX_REPS,
    MAX_SETS,
    MAX_TIME_MINUTES,
    MAX_WEIGHT_KG,
    MIN_EXERCISE_NAME_LEN,
    STRENGTH_FIELDS,
)

if TYPE_CHECKING:
    import tkinter as tk


class WorkoutFormsMixin:
    """Mixin providing workout form creation and validation."""

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
            self._entry_row(lbl, width=w, font_size=18) for lbl, w in STRENGTH_FIELDS
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
        """Parse reps input - single number or variable reps like '12+11+12'."""
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
        """Validate strength workout inputs. Returns error message or None."""
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
