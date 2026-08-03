"""The success screen shown once a workout has been credited.

Split out of ``screen_lock`` so that module stays inside the repo's 400-line
cap; this is pure view code (paint the credit, then hand off to the
commitment prompt or the close), which is exactly the kind of thing the other
``_ui_*`` mixins already own.
"""

from __future__ import annotations

from screen_locker._constants import EXTRA_BENEFITS_FILE
from screen_locker._extra_benefits import current_streak

_UNLOCK_DELAY_MS = 1500

# Workout kinds that carry a commitment prompt on the way out: they are the
# ones the user actually performed today, so "will you work out tomorrow?" is
# a question worth asking.
_COMMITTABLE = ("phone_verified", "runnerup_verified", "manual_workout")


class UnlockViewMixin:
    """Paints the unlock screen and routes to whatever follows it."""

    def unlock_screen(self) -> None:
        """Apply workout credit and display the success message."""
        credit = self._apply_workout_credit()

        self.clear_container()
        self._label(
            "Great job! 💪",
            role="display",
            scale=1.5,
            color=self._colors.success,
            pad="lg",
        )
        if credit.shutdown_adjusted:
            self._text(
                "Shutdown time +2h later! 🎁",
                role="title",
                color=self._colors.warning,
            )
        if credit.extra_bonus_delta > 0:
            self._text(
                f"Extra workout today! +{credit.extra_bonus_delta}h tonight",
                role="subtitle",
                color=self._colors.warning,
            )
        if credit.new_debt is not None:
            self._text(
                f"Workout debt: {credit.new_debt}",
                role="subtitle",
                color=self._colors.warning
                if credit.new_debt > 0
                else self._colors.muted,
            )
        streak = current_streak(EXTRA_BENEFITS_FILE)
        if streak >= 1:
            self._text(
                f"🔥 {streak}-week streak (5+ workouts each)",
                role="label",
                color=self._colors.muted,
            )
        self._text("Screen Unlocked!", role="display", pad="md")
        if self.workout_data.get("type") in _COMMITTABLE:
            self.root.after(
                _UNLOCK_DELAY_MS,
                lambda: self._show_commitment_prompt(on_done=self.close),
            )
        else:
            self.root.after(_UNLOCK_DELAY_MS, self.close)
