"""Mixin: workout log persistence (read/write log.json)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
from typing import TYPE_CHECKING

from gatelock.log_integrity import compute_entry_hmac

from screen_locker import _compliance_state
from screen_locker._constants import SCHEDULED_SKIPS_FILE
from screen_locker._log_io import load_workout_log
from screen_locker._manual_workout import MANUAL_WORKOUT_TYPE, manual_sync_record_id

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RecordResult:
    """Outcome of appending a workout entry to the day-keyed log.

    ``appended`` is ``False`` when an entry with the same ``workout_id`` was
    already present for that day — the append was a no-op, so the caller must
    apply NO new credit (re-verifying the same workout is idempotent).
    ``prior_entries`` is the day's entries *before* this append, which the
    credit path uses to tell a first-of-day workout from an additional one.
    """

    appended: bool
    prior_entries: list[dict] = field(default_factory=list)


def _derive_workout_id(date: str, workout_data: Mapping[str, object]) -> str | None:
    """Return a stable dedup id for ``workout_data`` on ``date``.

    An explicit ``workout_id`` in ``workout_data`` wins (used by manual-sync
    ingestion, which carries the wire record id). Otherwise a manual workout
    reuses :func:`manual_sync_record_id` so a locally-logged manual and the
    same one synced back share an id; every other type keys on
    ``"{type}:{date}"`` — idempotent per day, which matches the "one verified
    check per day" reality of the live phone/RunnerUp verifiers.
    """
    explicit = workout_data.get("workout_id")
    if explicit:
        return str(explicit)
    wtype = workout_data.get("type")
    if not wtype:
        return None
    if wtype == MANUAL_WORKOUT_TYPE:
        start = str(workout_data.get("start_time", "")).strip()
        if start:
            return manual_sync_record_id(date, start)
    return f"{wtype}:{date}"


def _entry_workout_id(date: str, entry: Mapping[str, object]) -> str | None:
    """Return an already-logged entry's dedup id, deriving it if it has none.

    Entries written before ``workout_id`` existed carry no id. Comparing only
    the stored field would treat them as un-matchable, so the SAME workout
    syncing back from another device would append a duplicate — which is
    exactly what happened to a pre-migration manual workout once the PC began
    publishing its history. Deriving the id the same way the writer would have
    makes a legacy entry match its own synced copy.
    """
    stored = entry.get("workout_id")
    if stored:
        return str(stored)
    workout_data = entry.get("workout_data", {})
    if not isinstance(workout_data, dict):
        return None
    return _derive_workout_id(date, workout_data)


def write_signed_entry(
    log_file: Path, date: str, workout_data: Mapping[str, object]
) -> RecordResult:
    """Append one HMAC-signed workout entry for ``date``, deduped by workout_id.

    The single write chokepoint. Shared by the live save path (today's
    workout) and manual-sync ingestion, which files a synced workout under its
    OWN date so the weekly count places it in the right ISO week. The log is
    day-keyed but now holds MULTIPLE entries per day: this APPENDS rather than
    overwrites. If an entry with the same ``workout_id`` already exists for the
    day, it is a no-op — the log itself is the idempotency store, so
    re-verifying the same workout never double-records. Every write normalizes
    the whole file to the list shape, progressively migrating legacy entries.

    Returns a :class:`RecordResult` so the credit path can tell an appended
    workout from a duplicate and a first-of-day workout from an additional one.
    """
    logs = load_workout_log(log_file)
    entries = logs.setdefault(date, [])
    prior = list(entries)

    workout_id = _derive_workout_id(date, workout_data)
    if workout_id is not None and any(
        _entry_workout_id(date, e) == workout_id for e in entries
    ):
        return RecordResult(appended=False, prior_entries=prior)

    entry: dict[str, object] = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "workout_data": workout_data,
    }
    if workout_id is not None:
        entry["workout_id"] = workout_id
    signature = compute_entry_hmac(entry)
    if signature is not None:
        entry["hmac"] = signature
    else:
        _logger.warning("HMAC key unavailable — saving unsigned entry")
    entries.append(entry)
    try:
        with log_file.open("w") as f:
            json.dump(logs, f, indent=2)
    except OSError as e:
        _logger.warning("Could not save workout log: %s", e)
    return RecordResult(appended=True, prior_entries=prior)


class LogMixin:
    """Handles reading and writing log.json for the ScreenLocker.

    ``log_file``/``workout_data`` are declared here (not assigned) so mypy
    knows their types on any composing class without needing
    ``type: ignore[attr-defined]`` on every access — the real values are set
    by ``ScreenLocker.__init__``.
    """

    log_file: Path
    workout_data: Mapping[str, object]

    def has_logged_today(self) -> bool:
        """Check if workout has been logged today with valid HMAC."""
        return _compliance_state.has_logged_today(self.log_file)

    def _is_scheduled_skip_today(self) -> bool:
        """Return True if today's date is listed in the scheduled skips file."""
        return _compliance_state.is_scheduled_skip_today(SCHEDULED_SKIPS_FILE)

    def save_workout_log(self) -> RecordResult:
        """Append today's workout to the log (HMAC-signed) and report the result.

        Returns the :class:`RecordResult` from the write chokepoint so callers
        (notably :meth:`WorkoutCreditMixin._apply_workout_credit`) can apply
        credit only for a genuinely new workout and scale it by whether today
        already had one.
        """
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        return write_signed_entry(self.log_file, today, self.workout_data)
