"""Field-level checks shared by ``validate_manual_workout``.

Split out of :mod:`screen_locker._manual_workout` to keep every file under the
250-line cap.
"""

from __future__ import annotations

from screen_locker._constants import MANUAL_WORKOUT_REFLECTION_MIN_CHARS
from screen_locker._manual_workout_types import SPORT_CHOICES, ManualWorkoutDraft


def validate_required(draft: ManualWorkoutDraft) -> str | None:
    """Return an error if the sport is unchosen or a required field is blank."""
    if draft.sport not in SPORT_CHOICES:
        return "Please choose a sport"

    required = {
        "Start time": draft.start_time,
        "End time": draft.end_time,
        "Location name": draft.location_name,
        "Transport method": draft.transport_method,
        "Cost": draft.cost,
    }
    for label, value in required.items():
        if not value.strip():
            return f"{label} is required"
    return None


def validate_reflections(draft: ManualWorkoutDraft) -> str | None:
    """Return an error if a reflection field is shorter than the minimum."""
    for label, value in (
        ("What went well", draft.went_well),
        ("What to improve", draft.to_improve),
        ("Overall feeling", draft.overall_feeling),
    ):
        if len(value.strip()) < MANUAL_WORKOUT_REFLECTION_MIN_CHARS:
            return (
                f"{label} must be at least {MANUAL_WORKOUT_REFLECTION_MIN_CHARS} "
                f"characters (currently {len(value.strip())})"
            )

    return None
