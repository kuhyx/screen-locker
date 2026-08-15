"""Tests for the read-only Tkinter status window's rendering (StatusWindow.render)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from screen_locker._status_view_verify import (
    PhoneCheckOutcome,
    _verify_phone_then_runnerup,
)


class TestVerifyPhoneThenRunnerup:
    """The "Check Phone" worker: StrongLifts first, then RunnerUp as fallback."""

    def test_stronglifts_verified_short_circuits(self) -> None:
        """A verified phone workout wins and RunnerUp is never consulted."""
        verifier = MagicMock()
        verifier._verify_phone_workout.return_value = ("verified", "5x5 done")

        result = _verify_phone_then_runnerup(verifier)

        assert result == PhoneCheckOutcome(
            "phone_verified", "verified", "5x5 done", None
        )
        verifier._verify_runnerup_workout.assert_not_called()

    def test_falls_back_to_runnerup_when_phone_not_verified(self) -> None:
        """StrongLifts miss → a verified run credits as runnerup_verified."""
        verifier = MagicMock()
        verifier._verify_phone_workout.return_value = ("not_verified", "stale")
        verifier._verify_runnerup_workout.return_value = ("verified", "9.8 km")

        result = _verify_phone_then_runnerup(verifier)

        assert result == PhoneCheckOutcome(
            "runnerup_verified", "verified", "stale", "9.8 km"
        )

    def test_neither_source_verified_nor_backfilled(self) -> None:
        """Neither verified today, nothing to backfill → no credit, no fill message."""
        verifier = MagicMock()
        verifier._verify_phone_workout.return_value = ("not_verified", "stale")
        verifier._verify_runnerup_workout.return_value = ("too_short", "3 km")
        verifier._scan_and_fill_week_runnerup.return_value = 0
        verifier._try_fill_stronglifts_for_week.return_value = 0

        with patch(
            "screen_locker._status_view_verify.count_weekly_workouts",
            return_value=2,
        ):
            result = _verify_phone_then_runnerup(verifier)

        assert result == PhoneCheckOutcome(None, "too_short", "stale", "3 km", None)

    def test_falls_back_to_week_scan_backfill(self) -> None:
        """Neither verified today, but the week-scan finds something → fill message."""
        verifier = MagicMock()
        verifier._verify_phone_workout.return_value = ("not_verified", "stale")
        verifier._verify_runnerup_workout.return_value = ("not_verified", "no run")
        verifier._scan_and_fill_week_runnerup.return_value = 1
        verifier._try_fill_stronglifts_for_week.return_value = 0

        with patch(
            "screen_locker._status_view_verify.count_weekly_workouts",
            side_effect=[2, 3],
        ):
            result = _verify_phone_then_runnerup(verifier)

        assert result.credited_type is None
        assert (
            result.week_fill_message == "Auto-filled 1 workout from earlier this week."
        )
        verifier._adjust_shutdown_time_by.assert_not_called()
