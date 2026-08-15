"""Cross-language fixture test for the unified workout-duration gate.

The Dart app mirrors these constants in ``lib/models/manual_workout.dart``.
Each language's own round-trip test passes happily while the two sides
disagree, so the only thing that catches a drift is a shared literal both
read -- ``fixtures/duration_threshold.json``. The Dart twin of this file is
``test/models/duration_threshold_fixture_test.dart``; they must stay in step.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from screen_locker._constants import (
    MIN_WORKOUT_DURATION_MINUTES,
    WORKOUT_DURATION_ACCEPT_MINUTES,
    WORKOUT_DURATION_LEEWAY_MINUTES,
)
from screen_locker._manual_workout import ManualWorkoutDraft, validate_manual_workout

FIXTURE = Path(__file__).parent / "fixtures" / "duration_threshold.json"


def _fixture() -> dict[str, object]:
    """Load the shared cross-language threshold fixture."""
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _draft(duration_minutes: int) -> ManualWorkoutDraft:
    """Build an otherwise-valid draft of exactly ``duration_minutes``."""
    end_h, end_m = divmod(12 * 60 + duration_minutes, 60)
    return ManualWorkoutDraft(
        sport="other",
        start_time="12:00",
        end_time=f"{end_h:02d}:{end_m:02d}",
        location_name="Home",
        transport_method="From bed",
        cost="0",
        rpe=3,
        went_well="Everything went smoothly today, no issues at all",
        to_improve="Dumbbell bench press needs assistance exercises",
        overall_feeling="Felt strong throughout the whole session today",
        reservation_phone="none",
        techniques_practiced="FBW",
        warm_up_minutes="none",
        pain_or_injury="none",
        activity_type_other="Weightlifting",
        activity_details="Dumbbell Lunge, Press, Row and Dumbbell Curl at home",
        equipment="Dumbbells",
    )


def test_constants_match_shared_fixture() -> None:
    """The Python constants equal the shared literal the Dart side also reads."""
    data = _fixture()
    assert data["advertised_minutes"] == MIN_WORKOUT_DURATION_MINUTES
    assert data["leeway_minutes"] == WORKOUT_DURATION_LEEWAY_MINUTES
    assert data["accept_minutes"] == WORKOUT_DURATION_ACCEPT_MINUTES


def test_accept_bar_is_derived_not_hardcoded() -> None:
    """The two bars cannot drift: the accept bar is advertised minus leeway."""
    assert (
        WORKOUT_DURATION_ACCEPT_MINUTES
        == MIN_WORKOUT_DURATION_MINUTES - WORKOUT_DURATION_LEEWAY_MINUTES
    )


@pytest.mark.parametrize("case", _fixture()["cases"])
def test_boundary_cases_from_fixture(case: dict[str, object]) -> None:
    """Every shared boundary case decides the same way on the Python side."""
    error = validate_manual_workout(_draft(int(case["duration_minutes"])))
    assert (error is None) is case["accepted"], (
        f"{case['duration_minutes']} min should be "
        f"{'accepted' if case['accepted'] else 'rejected'}, got {error!r}"
    )


def test_rejection_message_advertises_40_never_the_real_cutoff() -> None:
    """The hidden accept bar must never reach the user's eyes."""
    error = validate_manual_workout(_draft(10))
    assert error is not None
    assert str(MIN_WORKOUT_DURATION_MINUTES) in error
    assert str(WORKOUT_DURATION_ACCEPT_MINUTES) not in error
