"""Shared StatusSnapshot-building test helpers for test_status_view*.py.

Not a test module itself (no test_/\u200b*_test naming) — pytest's collector
(``python_files`` in pyproject.toml) never picks this up as a test file.
"""

from __future__ import annotations

import dataclasses
from unittest.mock import MagicMock

from screen_locker._compliance_state import (
    AutoUpgradeOpportunity,
    LockExplanation,
    PredicateResult,
)
from screen_locker._status_data import (
    DayStatus,
    ManualWorkoutBudgetStatus,
    ShutdownProjection,
    ShutdownProjectionDay,
    SickBudgetStatus,
    StatusSnapshot,
    WeeklySummary,
)
from screen_locker._temperature import TemperatureCheck
from screen_locker.status_view import StatusWindow

_WEEKDAY_LABELS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _day(
    *,
    date: str = "2024-01-05",
    label: str = "Fri Jan 05",
    entry_type: str | None = None,
    source: str = "",
    counted: bool = False,
    is_sick_day: bool = False,
) -> DayStatus:
    return DayStatus(
        date=date,
        label=label,
        entry_type=entry_type,
        source=source,
        counted=counted,
        is_sick_day=is_sick_day,
    )


def _week(
    *,
    days: tuple[DayStatus, ...] | None = None,
    counted_count: int = 0,
    minimum: int = 4,
    remaining: int = 4,
    extra: int = 0,
) -> WeeklySummary:
    return WeeklySummary(
        days=days or (_day(),),
        counted_count=counted_count,
        minimum=minimum,
        remaining=remaining,
        extra=extra,
    )


def _lock_explanation(
    *,
    fired: bool = False,
    stage: str = "already_logged",
    reason: str = "Workout already logged today — lock skipped.",
    auto_upgrade: AutoUpgradeOpportunity | None = None,
    heat_skip_evaluated: bool = False,
) -> LockExplanation:
    return LockExplanation(
        fired=fired,
        stage=stage,
        reason=reason,
        trace=(PredicateResult("already_logged", not fired, reason),),
        auto_upgrade=auto_upgrade
        or AutoUpgradeOpportunity(would_attempt=False, via="none", reason="none"),
        heat_skip_evaluated=heat_skip_evaluated,
    )


def _sick_budget(*, used_7d: int = 0, exhausted: bool = False) -> SickBudgetStatus:
    return SickBudgetStatus(
        used_7d=used_7d,
        budget_7d=1,
        used_30d=0,
        budget_30d=3,
        used_90d=0,
        budget_90d=10,
        debt=0,
        exhausted=exhausted,
    )


def _manual_workout_budget(
    *, used_7d: int = 0, exhausted: bool = False
) -> ManualWorkoutBudgetStatus:
    return ManualWorkoutBudgetStatus(
        used_7d=used_7d,
        budget_7d=2,
        used_30d=0,
        budget_30d=5,
        exhausted=exhausted,
    )


def _shutdown(
    *, tonight: tuple[int, int, int] | None = (21, 21, 5)
) -> ShutdownProjection:
    rest = tuple(
        ShutdownProjectionDay(label=lbl, hour=21, speculative=False)
        for lbl in _WEEKDAY_LABELS
    )
    preview = tuple(
        ShutdownProjectionDay(label=lbl, hour=21, speculative=True)
        for lbl in _WEEKDAY_LABELS
    )
    return ShutdownProjection(
        tonight=tonight,
        rest_of_week=rest,
        next_week_preview=preview,
        explanation="two separate systems",
    )


def _snapshot(**overrides: object) -> StatusSnapshot:
    default = StatusSnapshot(
        today=_day(),
        week=_week(),
        bonus_hours_this_week=0,
        streak=0,
        early_bird_extended=False,
        shutdown=_shutdown(),
        lock_explanation=_lock_explanation(),
        sick_budget=_sick_budget(),
        manual_workout_budget=_manual_workout_budget(),
        generated_at="2024-01-05T12:00:00+00:00",
    )
    return dataclasses.replace(default, **overrides)


def _texts(mock_tk: MagicMock) -> list[str]:
    """All text/label strings passed to any tk.Label call, in call order."""
    return [c.kwargs.get("text", "") for c in mock_tk.Label.call_args_list]


def _button_texts(mock_tk: MagicMock) -> set[str]:
    return {c.kwargs.get("text") for c in mock_tk.Button.call_args_list}


def _temp_check(
    *, temp_celsius: float | None = 20.0, timed_out: bool = False
) -> TemperatureCheck:
    return TemperatureCheck(temp_celsius=temp_celsius, timed_out=timed_out)


def _make_window(
    mock_tk: MagicMock, snapshot: StatusSnapshot, **kwargs: object
) -> StatusWindow:
    """Build a StatusWindow with an instant, non-hot, non-network temperature
    fetcher by default, so unrelated tests never trigger real network I/O —
    tests exercising temperature behavior pass their own ``temperature_fetcher``.
    """
    root = MagicMock()
    kwargs.setdefault("temperature_fetcher", lambda _city: _temp_check())
    return StatusWindow(
        root, snapshot, on_refresh=kwargs.pop("on_refresh", MagicMock()), **kwargs
    )
