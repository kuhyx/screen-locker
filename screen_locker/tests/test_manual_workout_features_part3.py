"""The manual-workout budget constants must match across Python and Dart.

Split out of test_manual_workout_features_part2.py for the 250-line cap.
"""

from __future__ import annotations

import pathlib
import re

from screen_locker._constants import (
    MANUAL_WORKOUT_BUDGET_PER_7_DAYS,
    MANUAL_WORKOUT_BUDGET_PER_30_DAYS,
)

# The Dart mirror of the budget caps; read at test time so drift on
# EITHER side fails, not just a local edit to the Python constants.
DART_MANUAL_WORKOUT = (
    pathlib.Path(__file__).resolve().parents[2]
    / "stronglift_replacement"
    / "workout_app"
    / "lib"
    / "models"
    / "manual_workout.dart"
)


class TestCrossLanguageBudgetConstants:
    """Pins the budget caps against the Dart phone app's own source file.

    The wire-format fixture in test_manual_workout.py pins payload key NAMES,
    but the caps never travel on the wire, so it cannot catch them drifting —
    and they did: 298daf0 raised Python 5 -> 10 while touching zero Dart files,
    leaving the phone at 5 for weeks. The stricter side silently blocks a
    workout the other accepts.

    So this READS THE DART FILE rather than asserting a hardcoded literal on
    each side. A test that compares a Python constant to a Python literal is
    only a guard against a local edit; it stays green when the other language
    drifts, which is the failure that actually happened. One test, either
    direction.
    """

    @staticmethod
    def _dart_const(name: str) -> int:
        """Return the int assigned to `const int <name>` in the Dart model."""
        source = DART_MANUAL_WORKOUT.read_text(encoding="utf-8")
        match = re.search(rf"const int {name} = (\d+);", source)
        assert match is not None, (
            f"{name} not found in {DART_MANUAL_WORKOUT} — it was renamed or "
            "removed; update this guard so the caps stay pinned."
        )
        return int(match.group(1))

    def test_dart_model_file_exists(self) -> None:
        """A moved/renamed Dart model must fail loudly, not skip the guard."""
        assert DART_MANUAL_WORKOUT.is_file(), (
            f"{DART_MANUAL_WORKOUT} is missing; the budget caps are no longer "
            "pinned across languages."
        )

    def test_per_7_days_matches_dart_mirror(self) -> None:
        """The 7-day cap must equal kManualWorkoutBudgetPer7Days."""
        assert (
            self._dart_const("kManualWorkoutBudgetPer7Days")
            == MANUAL_WORKOUT_BUDGET_PER_7_DAYS
        )

    def test_per_30_days_matches_dart_mirror(self) -> None:
        """The 30-day cap must equal kManualWorkoutBudgetPer30Days."""
        assert (
            self._dart_const("kManualWorkoutBudgetPer30Days")
            == MANUAL_WORKOUT_BUDGET_PER_30_DAYS
        )
