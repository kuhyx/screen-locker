"""Tests for the pure, read-only predicates in _compliance_state.py."""

from __future__ import annotations

from screen_locker._compliance_state import (
    AutoUpgradeOpportunity,
    describe_auto_upgrade_opportunity,
)


class TestDescribeAutoUpgradeOpportunity:
    """The 2 possible outcomes: expired early-bird, or none."""

    def test_expired_early_bird(self) -> None:
        """Expired early bird."""
        result = describe_auto_upgrade_opportunity(
            early_bird_pending=True, early_bird_window_open=False
        )
        assert result == AutoUpgradeOpportunity(
            would_attempt=True, via="early_bird_expired", reason=result.reason
        )

    def test_pending_inside_open_window_is_no_upgrade(self) -> None:
        """pending+open is not expired, and a sick day never upgrades."""
        result = describe_auto_upgrade_opportunity(
            early_bird_pending=True, early_bird_window_open=True
        )
        assert result.via == "none"

    def test_none(self) -> None:
        """None."""
        result = describe_auto_upgrade_opportunity(
            early_bird_pending=False, early_bird_window_open=False
        )
        assert result.would_attempt is False
        assert result.via == "none"
