"""Sick-day flow for the screen locker's locked screen.

Split out of :mod:`screen_locker._ui_flows` to keep every file under the
250-line cap. Composed back into ``UIFlowsMixin`` there, so the set of mixins
``ScreenLocker`` inherits is unchanged.
"""

from __future__ import annotations

from screen_locker import _sick_tracker


class SickDayFlowMixin:
    """Sick-day justification, countdown and debt bookkeeping."""

    def ask_if_sick(self) -> None:
        """Display the structured sick-day justification dialog."""
        self._show_sick_justification()

    def _get_sick_day_status(self) -> tuple[str, str]:
        """Determine sick day status text and color."""
        if self._sick_mode_used_today():
            return "Shutdown time already adjusted today", self._colors.warning
        if self._adjust_shutdown_time_earlier():
            return (
                "Shutdown time moved 1.5 hours earlier ✓\n(Will revert tomorrow)"
            ), self._colors.success
        return (
            "Could not adjust shutdown time (check permissions)",
            self._colors.danger,
        )

    def _proceed_to_sick_countdown(self) -> None:
        """Start the (escalated) sick day countdown after justification."""
        history = getattr(
            self,
            "_sick_history_cache",
            None,
        )
        if history is None:
            history = _sick_tracker.load_history()
            self._sick_history_cache = history
        countdown = _sick_tracker.compute_lockout_seconds(history)
        self.clear_container()
        status_text, status_color = self._get_sick_day_status()
        self._show_sick_day_ui(status_text, status_color, countdown)
        self.sick_remaining_time = countdown
        self._update_sick_countdown()

    def _show_sick_day_ui(
        self,
        status_text: str,
        status_color: str,
        countdown: int,
    ) -> None:
        """Display sick day UI labels and countdown."""
        self._label("Sick Day Mode", color=self._colors.warning, pad="md")
        self._text(status_text, color=status_color)
        minutes = countdown // 60
        self._text(
            f"Please wait ~{minutes} min before unlocking...",
            role="title",
            pad="md",
        )
        self.sick_countdown_label = self._label(
            str(countdown),
            role="display",
            scale=2.5,
            pad="lg",
        )

    def _update_sick_countdown(self) -> None:
        """Update the sick day countdown timer."""
        if self.sick_remaining_time > 0:
            self.sick_countdown_label.config(text=str(self.sick_remaining_time))
            self.sick_remaining_time -= 1
            self.root.after(1000, self._update_sick_countdown)
        else:
            self._finalize_sick_day()

    def _finalize_sick_day(self) -> None:
        """Persist sick-day history and unlock the screen."""
        history = getattr(self, "_sick_history_cache", None)
        if history is None:
            history = _sick_tracker.load_history()
        if _sick_tracker.had_commitment_for_today(history):
            _sick_tracker.mark_commitment_broken(history)
            self.workout_data["broke_commitment"] = "true"
        new_debt = _sick_tracker.add_sick_day(history)
        _sick_tracker.save_history(history)
        self.workout_data["type"] = "sick_day"
        self.workout_data["note"] = "Sick day - shutdown moved earlier"
        self.workout_data["debt"] = str(new_debt)
        self.unlock_screen()
