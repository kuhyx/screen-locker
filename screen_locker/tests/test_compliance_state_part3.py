"""Tests for the pure, read-only predicates in _compliance_state.py."""

from __future__ import annotations

from screen_locker._compliance_state import (
    AutoUpgradeOpportunity,
    describe_auto_upgrade_opportunity,
)


class TestDescribeAutoUpgradeOpportunity:
    """The 3 possible outcomes: expired early-bird, sick day, or none."""

    def test_expired_early_bird(self) -> None:
        """Expired early bird."""
        result = describe_auto_upgrade_opportunity(
            early_bird_pending=True, early_bird_window_open=False, is_sick_day=False
        )
        assert result == AutoUpgradeOpportunity(
            would_attempt=True, via="early_bird_expired", reason=result.reason
        )

    def test_sick_day(self) -> None:
        """Sick day."""
        result = describe_auto_upgrade_opportunity(
            early_bird_pending=False, early_bird_window_open=False, is_sick_day=True
        )
        assert result.would_attempt is True
        assert result.via == "sick_day"

    def test_sick_day_takes_second_priority_when_pending_still_open(self) -> None:
        """pending+open doesn't count as expired, so sick_day is still checked."""
        result = describe_auto_upgrade_opportunity(
            early_bird_pending=True, early_bird_window_open=True, is_sick_day=True
        )
        assert result.via == "sick_day"

    def test_none(self) -> None:
        """None."""
        result = describe_auto_upgrade_opportunity(
            early_bird_pending=False, early_bird_window_open=False, is_sick_day=False
        )
        assert result.would_attempt is False
        assert result.via == "none"
