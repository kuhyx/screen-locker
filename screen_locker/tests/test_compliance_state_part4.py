"""Tests for the pure, read-only predicates in _compliance_state.py."""

from __future__ import annotations

from screen_locker import _compliance_state


class TestEarlyBirdWindowOpen:
    """The early-bird window's start/end boundaries, including the extension."""

    """Direct tests for the module-private, deliberately independent reimplementation."""

    def test_before_window(self) -> None:
        """Before the start hour the window is shut."""
        assert (
            _compliance_state._early_bird_window_open(extended=False, local_minutes=299)
            is False
        )

    def test_at_start(self) -> None:
        """The start minute itself is inside the window."""
        assert (
            _compliance_state._early_bird_window_open(extended=False, local_minutes=300)
            is True
        )

    def test_before_end(self) -> None:
        """A minute before the end is still inside the window."""
        assert (
            _compliance_state._early_bird_window_open(extended=False, local_minutes=509)
            is True
        )

    def test_at_end_exclusive(self) -> None:
        """The end minute is exclusive: the window is already shut."""
        assert (
            _compliance_state._early_bird_window_open(extended=False, local_minutes=510)
            is False
        )

    def test_extended_before_end(self) -> None:
        """With the extension earned, the window runs later."""
        assert (
            _compliance_state._early_bird_window_open(extended=True, local_minutes=539)
            is True
        )

    def test_extended_at_end_exclusive(self) -> None:
        """The extended end is exclusive too."""
        assert (
            _compliance_state._early_bird_window_open(extended=True, local_minutes=540)
            is False
        )
