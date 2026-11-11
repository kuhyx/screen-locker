"""The individual rendered sections of the status window.

Split out of :mod:`screen_locker.status_view` to keep every file under the
250-line cap. Composed into ``StatusWindow`` there, alongside the other view
mixins, so the class's public surface is unchanged.

Every method here is display-only: it reads the snapshot it is handed and
paints widgets. Nothing in this module writes to disk or reaches the network.

textgate: no section has a heading or a sentence any more. Each is one or
two lines of glyphs (``_glyphs``) and numbers, coloured by state. Weekdays
are positions in a Mon..Sun row, not names.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from screen_locker import _glyphs as g
from screen_locker._earned import hhmm
from screen_locker._sync_status import gather_sync_status

if TYPE_CHECKING:
    import tkinter as tk

    from screen_locker._compliance_state import LockExplanation
    from screen_locker._status_data import (
        DayStatus,
        ManualWorkoutBudgetStatus,
        ShutdownProjection,
        WeeklySummary,
    )


class StatusSectionsMixin:
    """Renders each section of the status window from a snapshot."""

    def _day_cell(self, day: DayStatus) -> str:
        """One day as a glyph: its entries, sick, or an empty circle."""
        if day.entry_types:
            return g.entry_glyphs(day.entry_types)
        return g.WEEK_SICK if day.is_sick_day else g.WEEK_EMPTY

    def _section_today(self, parent: tk.Widget, day: DayStatus) -> None:
        """Render today's outcome (was "✓ Today (Wed Nov 11): phone_verified")."""
        del parent
        mark = g.OK if day.counted else (g.SICK if day.is_sick_day else g.FAIL)
        self._label(
            f"{mark} {self._day_cell(day)}",
            role="title",
            color=self._colors.palette.success
            if day.counted
            else self._colors.palette.warning,
        )

    def _section_week(self, parent: tk.Widget, week: WeeklySummary) -> None:
        """Render this ISO week: dots + count, then one cell per day.

        Was "This Week: 2/4", a "Mon Nov 09: no entry" line per day and "Need
        2 more this week." / "1 above the weekly minimum!".
        """
        del parent
        enough = week.remaining <= 0
        self._text(
            g.dots(week.counted_count, week.minimum),
            role="title",
            color=self._colors.palette.success
            if enough
            else self._colors.palette.warning,
            pad="sm",
        )
        self._text(
            "  ".join(self._day_cell(day) for day in week.days),
            role="body",
            color=self._colors.palette.muted,
            pad="xs",
        )

    def _section_streak(
        self, parent: tk.Widget, streak: int, week_rewards: tuple[str, ...] = ()
    ) -> None:
        """Render the consecutive 5+-workout-week streak and this week's reward.

        Display only, and exactly the stored values (``extra_benefits_state``):
        a streak of 0 is shown as 0, never padded or rounded up. Nothing here
        grants time or relaxes a lock. Was "🔥 N-week streak (5+ workouts a
        week)" / "No streak yet: ..." and the reward sentences.
        """
        del parent
        self._text(
            f"{g.STREAK * min(streak, 10)} {streak}" if streak else f"{g.STREAK} 0",
            role="body",
            color=self._colors.palette.success
            if streak
            else self._colors.palette.muted,
        )
        for message in week_rewards:
            # A reset is news, not a celebration: it must not be painted green.
            lost = message.startswith("Streak reset")
            self._text(
                f"{g.STREAK}{g.FAIL}" if lost else f"{g.STREAK}{g.GIFT}",
                role="body",
                color=self._colors.palette.warning
                if lost
                else self._colors.palette.success,
            )

    def _section_lock_explanation(
        self, parent: tk.Widget, expl: LockExplanation
    ) -> None:
        """Render whether the lock fired today and the stage that decided it.

        Was "Why the lock did/didn't fire" over the stage's sentence.
        """
        del parent
        square = g.LOCK if expl.fired else g.UNLOCK
        self._text(
            f"{square} {g.STAGE_GLYPH.get(expl.stage, '')}".rstrip(),
            role="title",
            color=self._colors.palette.danger
            if expl.fired
            else self._colors.palette.success,
        )
        if expl.auto_upgrade.would_attempt:
            self._text(g.RETRY, role="label", color=self._colors.palette.warning)

    def _section_manual_workout_budget(
        self, parent: tk.Widget, manual: ManualWorkoutBudgetStatus
    ) -> None:
        """Render rolling manual-workout budget usage (7-day, then 30-day)."""
        del parent
        self._text(
            f"{g.FORM} {manual.used_7d}/{manual.budget_7d} · "
            f"{manual.used_30d}/{manual.budget_30d}",
            role="body",
            color=self._colors.palette.danger
            if manual.exhausted
            else self._colors.palette.muted,
        )

    def _section_sync_backend(self, parent: tk.Widget) -> None:
        """Render whether this machine's sync is healthy, and its peer count.

        Read from local state only (see :mod:`screen_locker._sync_status`), so
        opening or refreshing the window never makes a network call. Coloured
        by ``healthy`` rather than by backend: "configured but never pushed"
        looks fine everywhere else and produces no data, which is exactly the
        state worth surfacing here.
        """
        del parent
        status = gather_sync_status()
        self._text(
            f"{g.SYNC} {g.OK if status.healthy else g.FAIL} {status.peer_count}",
            role="body",
            color=self._colors.palette.muted
            if status.healthy
            else self._colors.palette.danger,
        )

    def _section_shutdown(
        self, parent: tk.Widget, shutdown: ShutdownProjection
    ) -> None:
        """Render tonight's live config, rest-of-week, and next-week preview.

        Was "Live config — Mon-Wed 21:00, Thu-Sun 22:00", "Rest of week: Mon
        21:00, ...", "Next week (speculative): ..." and an explanation. Now
        the times only, in day order: live config bold, the rest muted.
        """
        del parent
        if shutdown.tonight is not None:
            mon_wed, thu_sun, _morning = shutdown.tonight
            self._text(f"{g.SHUTDOWN} {hhmm(mon_wed)} · {hhmm(thu_sun)}", role="title")
        else:
            self._text(
                f"{g.SHUTDOWN} {g.FAIL}",
                role="title",
                color=self._colors.palette.warning,
            )
        for days in (shutdown.rest_of_week, shutdown.next_week_preview):
            self._text(
                "  ".join(hhmm(d.minutes) for d in days),
                role="caption",
                color=self._colors.palette.muted,
            )
