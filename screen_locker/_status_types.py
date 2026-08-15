"""The frozen dataclasses describing a status snapshot.

Split out of :mod:`screen_locker._status_data` to keep every file under the
250-line cap. Re-exported from there, so ``status_view`` and every other
importer is unaffected.

These are plain value objects: building them from disk is ``_status_data``'s
job, rendering them is ``_status_sections``'.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from screen_locker._compliance_state import LockExplanation


@dataclass(frozen=True)
class DayStatus:
    """One day's workout outcome (a day may hold several workouts)."""

    date: str
    label: str
    entry_types: tuple[str, ...]
    source: str
    counted: bool
    day_count: int
    is_sick_day: bool


@dataclass(frozen=True)
class WeeklySummary:
    """This ISO week's workout compliance so far."""

    days: tuple[DayStatus, ...]
    counted_count: int
    minimum: int
    remaining: int
    extra: int


@dataclass(frozen=True)
class SickBudgetStatus:
    """Rolling sick-day budget usage."""

    used_7d: int
    budget_7d: int
    used_30d: int
    budget_30d: int
    used_90d: int
    budget_90d: int
    debt: int
    exhausted: bool


@dataclass(frozen=True)
class ManualWorkoutBudgetStatus:
    """Rolling manual-workout budget usage."""

    used_7d: int
    budget_7d: int
    used_30d: int
    budget_30d: int
    exhausted: bool


@dataclass(frozen=True)
class ShutdownProjectionDay:
    """One labeled row in a shutdown-time projection."""

    label: str
    hour: int
    speculative: bool


@dataclass(frozen=True)
class ShutdownProjection:
    """Tonight's live config plus deterministic/speculative week projections."""

    tonight: tuple[int, int, int] | None
    rest_of_week: tuple[ShutdownProjectionDay, ...]
    next_week_preview: tuple[ShutdownProjectionDay, ...]
    explanation: str


@dataclass(frozen=True)
class StatusSnapshot:
    """Everything the status view needs, gathered in one read-only pass."""

    today: DayStatus
    week: WeeklySummary
    bonus_hours_this_week: int
    streak: int
    early_bird_extended: bool
    shutdown: ShutdownProjection
    lock_explanation: LockExplanation
    sick_budget: SickBudgetStatus
    manual_workout_budget: ManualWorkoutBudgetStatus
    generated_at: str
