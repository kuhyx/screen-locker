"""The individual rendered sections of the status window.

Split out of :mod:`screen_locker.status_view` to keep every file under the
250-line cap. Composed into ``StatusWindow`` there, alongside the other view
mixins, so the class's public surface is unchanged.

Every method here is display-only: it reads the snapshot it is handed and
paints widgets. Nothing in this module writes to disk or reaches the network.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from screen_locker._sync_status import format_sync_line, gather_sync_status

if TYPE_CHECKING:
    import tkinter as tk

    from screen_locker._compliance_state import LockExplanation
    from screen_locker._status_data import (
        DayStatus,
        ManualWorkoutBudgetStatus,
        ShutdownProjection,
        SickBudgetStatus,
        WeeklySummary,
    )


class StatusSectionsMixin:
    """Renders each section of the status window from a snapshot."""

    def _section_today(self, parent: tk.Widget, day: DayStatus) -> None:
        """Render today's outcome."""
        del parent
        mark = "✓" if day.counted else ("😷" if day.is_sick_day else "—")
        entry_str = ", ".join(day.entry_types) or (
            "sick day" if day.is_sick_day else "no entry yet"
        )
        self._text(
            f"{mark} Today ({day.label}): {entry_str}",
            role="body",
            color=self._colors.success if day.counted else self._colors.warning,
        )
        if day.source:
            # Secondary provenance note on an already-shown entry -- a
            # deliberately caption-sized exception to the 16px floor.
            self._text(day.source, role="caption", color=self._colors.muted, pad="xs")

    def _section_week(self, parent: tk.Widget, week: WeeklySummary) -> None:
        """Render this ISO week's per-day breakdown and totals."""
        del parent
        self._label(
            f"This Week: {week.counted_count}/{week.minimum}", role="body", pad="sm"
        )
        for day in week.days:
            mark = "✓" if day.counted else ("😷" if day.is_sick_day else "·")
            entry_str = ", ".join(day.entry_types) or (
                "sick day" if day.is_sick_day else "no entry"
            )
            self._text(
                f"{mark} {day.label}: {entry_str}",
                role="body",
                color=self._colors.muted,
                pad="xs",
            )
        if week.remaining > 0:
            self._text(
                f"Need {week.remaining} more this week.",
                role="body",
                color=self._colors.warning,
            )
        elif week.extra > 0:
            self._text(
                f"{week.extra} above the weekly minimum!",
                role="body",
                color=self._colors.success,
            )

    def _section_lock_explanation(
        self, parent: tk.Widget, expl: LockExplanation
    ) -> None:
        """Render why the lock did/didn't fire today, plus its evaluation trace."""
        del parent
        self._label("Why the lock did/didn't fire", role="body", pad="sm")
        self._text(
            expl.reason,
            role="body",
            color=self._colors.danger if expl.fired else self._colors.success,
        )
        if expl.auto_upgrade.would_attempt:
            self._text(
                f"Pending auto-upgrade: {expl.auto_upgrade.reason}",
                role="label",
                color=self._colors.warning,
            )

    def _section_sick_budget(self, parent: tk.Widget, sick: SickBudgetStatus) -> None:
        """Render rolling sick-day budget usage."""
        del parent
        self._label("Sick Budget", role="body", pad="sm")
        self._text(
            f"{sick.used_7d}/{sick.budget_7d} week · {sick.used_30d}/{sick.budget_30d} "
            f"month · {sick.used_90d}/{sick.budget_90d} quarter · debt {sick.debt}",
            role="body",
            color=self._colors.danger if sick.exhausted else self._colors.muted,
        )

    def _section_manual_workout_budget(
        self, parent: tk.Widget, manual: ManualWorkoutBudgetStatus
    ) -> None:
        """Render rolling manual-workout budget usage."""
        del parent
        self._label("Manual Workout Budget", role="body", pad="sm")
        self._text(
            f"{manual.used_7d}/{manual.budget_7d} week · "
            f"{manual.used_30d}/{manual.budget_30d} month",
            role="body",
            color=self._colors.danger if manual.exhausted else self._colors.muted,
        )

    def _section_sync_backend(self, parent: tk.Widget) -> None:
        """Render which backend this machine syncs through.

        Read from local state only (see :mod:`screen_locker._sync_status`), so
        opening or refreshing the window never makes a network call. Coloured
        by ``healthy`` rather than by backend: "configured but never pushed"
        looks fine everywhere else and produces no data, which is exactly the
        state worth surfacing here.
        """
        del parent
        status = gather_sync_status()
        self._label("Sync backend", role="body", pad="sm")
        self._text(
            format_sync_line(status),
            role="body",
            color=self._colors.muted if status.healthy else self._colors.danger,
        )

    def _section_shutdown(
        self, parent: tk.Widget, shutdown: ShutdownProjection
    ) -> None:
        """Render tonight's live config, rest-of-week, and next-week preview."""
        del parent
        self._label("Shutdown Time", role="body", pad="sm")
        if shutdown.tonight is not None:
            mon_wed_hour, thu_sun_hour, _morning = shutdown.tonight
            self._text(
                f"Live config — Mon-Wed {mon_wed_hour:02d}:00, "
                f"Thu-Sun {thu_sun_hour:02d}:00",
                role="body",
            )
        else:
            self._text(
                "Live shutdown config unavailable.",
                role="body",
                color=self._colors.warning,
            )
        # Rest-of-week/next-week/explanation are speculative annotations, not
        # the section's primary content -- a deliberate caption-sized
        # exception to the 16px floor, all sharing one muted tone instead of
        # three unrelated ad hoc grays.
        rest_line = ", ".join(
            f"{d.label} {d.hour:02d}:00" for d in shutdown.rest_of_week
        )
        self._text(
            f"Rest of week: {rest_line}", role="caption", color=self._colors.muted
        )
        next_line = ", ".join(
            f"{d.label} {d.hour:02d}:00" for d in shutdown.next_week_preview
        )
        self._text(
            f"Next week (speculative): {next_line}",
            role="caption",
            color=self._colors.muted,
        )
        self._text(shutdown.explanation, role="caption", color=self._colors.muted)
