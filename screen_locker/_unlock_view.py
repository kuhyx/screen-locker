"""The success screen shown once a workout has been credited.

Split out of ``screen_lock`` so that module stays inside the repo's 400-line
cap; this is pure view code (paint the credit, then close), which is exactly
the kind of thing the other ``_ui_*`` mixins already own.
"""

from __future__ import annotations

from screen_locker._constants import EXTRA_BENEFITS_FILE
from screen_locker._earned import span
from screen_locker._extra_benefits import current_streak

_UNLOCK_DELAY_MS = 1500


class UnlockViewMixin:
    """Paints the unlock screen, then closes it."""

    def unlock_screen(self) -> None:
        """Apply workout credit and display the success message."""
        credit = self._apply_workout_credit()

        self.clear_container()
        self._label(
            "Great job! 💪",
            role="display",
            scale=1.5,
            color=self._colors.palette.success,
            pad="lg",
        )
        if credit.shutdown_adjusted:
            self._text(
                "Shutdown time +2h later! 🎁",
                role="title",
                color=self._colors.palette.warning,
            )
        if credit.extra_bonus_delta > 0:
            self._text(
                f"Extra workout today! +{span(credit.extra_bonus_delta)} tonight",
                role="subtitle",
                color=self._colors.palette.warning,
            )
        streak = current_streak(EXTRA_BENEFITS_FILE)
        if streak >= 1:
            self._text(
                f"🔥 {streak}-week streak (5+ workouts each)",
                role="label",
                color=self._colors.palette.muted,
            )
        self._text("Screen Unlocked!", role="display", pad="md")
        self.root.after(_UNLOCK_DELAY_MS, self.close)
