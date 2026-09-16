"""Tests for the read-only Tkinter status window's rendering (StatusWindow.render)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from screen_locker._status_view_verify import (
    _backfill_week_and_apply_bonus,
)


class TestBackfillWeekAndApplyBonus:
    """The week-scan fallback: backfill unlogged days, apply the earned bonus."""

    def test_nothing_filled_returns_none(self) -> None:
        """Nothing filled returns none."""
        verifier = MagicMock()
        verifier._scan_and_fill_week_runnerup.return_value = 0
        verifier._try_fill_stronglifts_for_week.return_value = 0

        with patch(
            "screen_locker._status_view_verify.count_weekly_workouts",
            return_value=2,
        ):
            assert _backfill_week_and_apply_bonus(verifier) is None
        verifier._adjust_shutdown_time_by.assert_not_called()

    def test_runnerup_fill_is_credited_through_the_shared_callback(self) -> None:
        """A RunnerUp fill earns its day-scaled reward via ``on_ingested``.

        The weekly-surplus rule used to apply here too, which is 0 for most
        of the week: on 2026-09-16 a run synced at 20:25 left the shutdown
        hour at 20:00. The scan now receives the same credit callback as
        every other ingestion source, and this path adds no bonus of its own.
        """
        verifier = MagicMock()
        verifier._scan_and_fill_week_runnerup.return_value = 1
        verifier._try_fill_stronglifts_for_week.return_value = 0

        with patch(
            "screen_locker._status_view_verify.count_weekly_workouts",
            return_value=3,
        ):
            message = _backfill_week_and_apply_bonus(verifier)

        assert message == "Auto-filled 1 workout from earlier this week."
        verifier._scan_and_fill_week_runnerup.assert_called_once_with(
            verifier.log_file, on_ingested=verifier._credit_ingested_workout
        )
        verifier._adjust_shutdown_time_by.assert_not_called()

    def test_stronglifts_fill_past_minimum_applies_surplus_bonus(self) -> None:
        """The StrongLifts fill keeps the weekly-surplus rule, net of RunnerUp fills."""
        verifier = MagicMock()
        verifier._scan_and_fill_week_runnerup.return_value = 1
        verifier._try_fill_stronglifts_for_week.return_value = 1

        with patch(
            "screen_locker._status_view_verify.count_weekly_workouts",
            side_effect=[4, 7],
        ):
            message = _backfill_week_and_apply_bonus(verifier)

        # prev 4 + 1 RunnerUp fill already credited = 5; 7 - 5 = 2 surplus.
        assert message == (
            "Auto-filled 2 workouts from earlier this week. +2h shutdown time."
        )
        verifier._adjust_shutdown_time_by.assert_called_once_with(2)

    def test_stronglifts_fill_below_minimum_earns_no_surplus(self) -> None:
        """A StrongLifts fill that leaves the week under the minimum adds nothing."""
        verifier = MagicMock()
        verifier._scan_and_fill_week_runnerup.return_value = 0
        verifier._try_fill_stronglifts_for_week.return_value = 1

        with patch(
            "screen_locker._status_view_verify.count_weekly_workouts",
            side_effect=[2, 3],
        ):
            message = _backfill_week_and_apply_bonus(verifier)

        assert message == "Auto-filled 1 workout from earlier this week."
        verifier._adjust_shutdown_time_by.assert_not_called()
