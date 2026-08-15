"""Lockout countdown and phone-penalty flows for the locked screen.

Split out of :mod:`screen_locker._ui_flows` to keep every file under the
250-line cap. Composed back into ``UIFlowsMixin`` there, so the set of mixins
``ScreenLocker`` inherits is unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from screen_locker._constants import (
    NO_PHONE_EXTRA_LOCKOUT_SECONDS,
    PHONE_PENALTY_DELAY_DEMO,
    PHONE_PENALTY_DELAY_PRODUCTION,
)

if TYPE_CHECKING:
    from collections.abc import Callable


class LockoutFlowMixin:
    """Lockout countdown and the no-phone penalty timer."""

    # ------------------------------------------------------------------
    # Lockout flow
    # ------------------------------------------------------------------

    def lockout(self) -> None:
        """Display lockout screen with countdown timer."""
        self.clear_container()
        self.lockout_label = self._label(
            f"Go work out!\nLocked for {self.lockout_time} seconds",
            role="display",
            scale=1.5,
            color=self._colors.danger,
            pad="lg",
        )
        self.countdown_label = self._label(
            str(self.lockout_time),
            role="display",
            scale=3.75,
            pad="lg",
        )
        self.remaining_time = self.lockout_time
        self.update_lockout_countdown()

    def update_lockout_countdown(self) -> None:
        """Update the lockout countdown timer display."""
        if self.remaining_time > 0:
            self.countdown_label.config(text=str(self.remaining_time))
            self.remaining_time -= 1
            self.root.after(1000, self.update_lockout_countdown)
        else:
            self._start_phone_check()

    # ------------------------------------------------------------------
    # Phone penalty
    # ------------------------------------------------------------------

    def _show_phone_penalty(
        self, message: str, *, on_done: Callable[[], None] | None = None
    ) -> None:
        """Show penalty countdown when phone verification is unavailable."""
        self.clear_container()
        self._phone_penalty_done_fn: Callable[[], None] = (
            on_done
            if on_done is not None
            else lambda: self._show_retry_and_sick(message)
        )
        base_delay = (
            PHONE_PENALTY_DELAY_DEMO
            if self.demo_mode
            else PHONE_PENALTY_DELAY_PRODUCTION
        )
        # Disconnecting the phone shouldn't be a fast path into sick mode.
        delay = (
            base_delay
            if self.demo_mode
            else base_delay + NO_PHONE_EXTRA_LOCKOUT_SECONDS
        )
        self._label(
            "Cannot Verify Workout",
            role="display",
            color=self._colors.warning,
            pad="md",
        )
        self._text(message, color=self._colors.warning)
        self._text(
            "Connect phone via ADB to skip this wait,\n"
            "or wait for the penalty timer.\n\n"
            "Note: Phone must be rooted and StrongLifts installed.",
            role="body",
        )
        self.phone_penalty_remaining = delay
        self.phone_penalty_label = self._label(
            str(delay),
            role="display",
            scale=2.5,
            pad="md",
        )
        self._update_phone_penalty()

    def _update_phone_penalty(self) -> None:
        """Update phone penalty countdown."""
        if self.phone_penalty_remaining > 0:
            self.phone_penalty_label.config(
                text=str(self.phone_penalty_remaining),
            )
            self.phone_penalty_remaining -= 1
            self.root.after(1000, self._update_phone_penalty)
        else:
            self._phone_penalty_done_fn()
