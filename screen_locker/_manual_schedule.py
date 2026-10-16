"""Log a manual workout for a FUTURE day from this PC (Tk dialog and CLI).

A future-dated entry never touches ``log.json`` or ``write_signed_entry`` and
earns nothing today. It is held in the pending ledger (``_manual_pending``),
published to this device's sync log so the phone sees it (budget, delete), and
ingested on its date by the ordinary sync pass, which pays exactly what a
workout logged that day would.

This module is the one place that decides whether such an entry may be logged:
the date window and the per-date budget, over the credits in ``log.json`` plus
every pending future entry -- this PC's ledger AND the merged Firebase manual
records (a phone-logged one holds a slot too).
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING

from screen_locker._device import device_identity
from screen_locker._manual_future import (
    budget_error_for_date,
    is_future_date,
    validate_workout_date,
)
from screen_locker._manual_pending import (
    add_pending,
    local_pending_records,
    pending_future_dates,
)
from screen_locker._manual_push import push_pc_workouts
from screen_locker._manual_workout import build_sync_payload, manual_sync_record_id
from screen_locker._workout_sync import pull_all_manual_records

if TYPE_CHECKING:
    from pathlib import Path

    from screen_locker._manual_workout import ManualWorkoutDraft

__all__ = ["ScheduleResult", "budget_error", "schedule_future_workout"]

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScheduleResult:
    """Outcome of :func:`schedule_future_workout`; ``reason`` is for a human."""

    scheduled: bool
    record_id: str
    reason: str


def budget_error(
    log_file: Path, workout_date: str, *, exclude_id: str | None = None
) -> str | None:
    """Why a manual workout on ``workout_date`` does not fit the budget, else None.

    Reads the pending future entries from this PC's ledger and from the merged
    Firebase pull. The pull is best-effort (``pull_all_manual_records`` warns
    and returns nothing when Firebase is unreachable), so offline this still
    sees the ledger -- only a phone-logged pending entry can be missed, and the
    ingest on that day re-checks.
    """
    records = [*pull_all_manual_records(), *local_pending_records()]
    pending = pending_future_dates(log_file, records)
    if exclude_id is not None:
        pending.pop(exclude_id, None)
    return budget_error_for_date(log_file, workout_date, pending.values())


def schedule_future_workout(
    log_file: Path, draft: ManualWorkoutDraft, workout_date: str
) -> ScheduleResult:
    """Hold a validated draft for ``workout_date`` and publish it.

    The caller has run ``validate_manual_workout`` on ``draft``. Refuses (and
    says why) a date outside today+1..today+7, an exhausted budget, or an
    entry already scheduled under the same id; otherwise stores it in the
    pending ledger and pushes immediately, so the phone sees it now rather
    than on the next 15-minute tick.
    """
    record_id = manual_sync_record_id(workout_date, draft.start_time)
    date_error = validate_workout_date(workout_date)
    if date_error is None and not is_future_date(workout_date):
        date_error = f"{workout_date} is today, not a future date"
    if date_error is not None:
        return ScheduleResult(scheduled=False, record_id=record_id, reason=date_error)
    over_budget = budget_error(log_file, workout_date)
    if over_budget is not None:
        return ScheduleResult(scheduled=False, record_id=record_id, reason=over_budget)
    payload = build_sync_payload(draft, workout_date)
    if not add_pending(record_id, payload, device_identity().device_id):
        return ScheduleResult(
            scheduled=False,
            record_id=record_id,
            reason=f"{record_id} is already scheduled",
        )
    pushed = push_pc_workouts(log_file)
    _logger.info(
        "Scheduled manual workout %s for %s (published=%s: %s)",
        record_id,
        workout_date,
        pushed.pushed,
        pushed.reason,
    )
    if pushed.pushed:
        reason = f"scheduled for {workout_date}; counts automatically that day"
    else:
        reason = (
            f"scheduled for {workout_date} on this PC (not yet published: "
            f"{pushed.reason}); it counts automatically that day"
        )
    return ScheduleResult(scheduled=True, record_id=record_id, reason=reason)
