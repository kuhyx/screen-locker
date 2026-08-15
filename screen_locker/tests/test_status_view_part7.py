"""Tests for status_view.py: phone-check flow, buttons, main() CLI entry point."""

from __future__ import annotations

from screen_locker.status_view import (
    _compliance_state_word,
)
from screen_locker.tests._status_view_helpers import (
    _lock_explanation,
    _snapshot,
    _week,
)


class TestComplianceStateWord:
    """ComplianceStateWord."""

    def test_lock_when_fired(self) -> None:
        """Lock when fired."""
        snap = _snapshot(lock_explanation=_lock_explanation(fired=True))
        assert _compliance_state_word(snap) == "lock"

    def test_warn_when_not_fired_but_remaining(self) -> None:
        """Warn when not fired but remaining."""
        snap = _snapshot(
            lock_explanation=_lock_explanation(fired=False),
            week=_week(remaining=2),
        )
        assert _compliance_state_word(snap) == "warn"

    def test_ok_when_not_fired_and_minimum_met(self) -> None:
        """Ok when not fired and minimum met."""
        snap = _snapshot(
            lock_explanation=_lock_explanation(fired=False),
            week=_week(remaining=0),
        )
        assert _compliance_state_word(snap) == "ok"
