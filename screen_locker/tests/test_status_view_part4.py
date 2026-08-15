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

    def test_fill_at_or_below_minimum_earns_no_bonus(self) -> None:
        """Filling up to (not past) the weekly minimum earns no shutdown push."""
        verifier = MagicMock()
        verifier._scan_and_fill_week_runnerup.return_value = 1
        verifier._try_fill_stronglifts_for_week.return_value = 0

        with patch(
            "screen_locker._status_view_verify.count_weekly_workouts",
            side_effect=[3, 4],
        ):
            message = _backfill_week_and_apply_bonus(verifier)

        assert message == "Auto-filled 1 workout from earlier this week."
        verifier._adjust_shutdown_time_by.assert_not_called()

    def test_fill_past_minimum_applies_bonus(self) -> None:
        """Fill past minimum applies bonus."""
        verifier = MagicMock()
        verifier._scan_and_fill_week_runnerup.return_value = 1
        verifier._try_fill_stronglifts_for_week.return_value = 1

        with patch(
            "screen_locker._status_view_verify.count_weekly_workouts",
            side_effect=[4, 7],
        ):
            message = _backfill_week_and_apply_bonus(verifier)

        assert message == (
            "Auto-filled 2 workouts from earlier this week. +2h shutdown time."
        )
        verifier._adjust_shutdown_time_by.assert_called_once_with(2)
