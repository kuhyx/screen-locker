"""Pure, read-only leaf predicates for the lock-decision chain.

Split out of :mod:`screen_locker._compliance_state` to keep every file under
the 250-line cap. That module re-exports everything here, so existing
importers are unaffected.

Nothing in this module touches ADB, sudo, subprocess, or the network, and
nothing writes to disk.

Note for tests: the ``gatelock.log_integrity`` helpers are imported *here*
now, so patch them at ``screen_locker._compliance_predicates.verify_entry_hmac``
rather than at the old ``_compliance_state`` path.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from typing import TYPE_CHECKING

from gatelock.log_integrity import compute_entry_hmac, verify_entry_hmac

from screen_locker._constants import (
    EARLY_BIRD_END_HOUR,
    EARLY_BIRD_END_MINUTE,
    EARLY_BIRD_START_HOUR,
)
from screen_locker._log_io import load_workout_log
from screen_locker._sick_tracker import is_sick_day as _is_sick_day

if TYPE_CHECKING:
    from pathlib import Path

    from screen_locker._sick_tracker import SickHistory

_logger = logging.getLogger(__name__)


def _today_str() -> str:
    """Return today's date as ``YYYY-MM-DD`` in UTC."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


def is_scheduled_skip_today(
    scheduled_skips_file: Path, *, today: str | None = None
) -> bool:
    """Return True if *today* is listed in *scheduled_skips_file*."""
    if not scheduled_skips_file.exists():
        return False
    try:
        with scheduled_skips_file.open() as f:
            skips = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        _logger.warning(
            "Could not read scheduled skips from %s: %s — treating today as NOT "
            "a scheduled skip (the lock chain continues)",
            scheduled_skips_file,
            exc,
        )
        return False
    return (today or _today_str()) in skips


def has_logged_today(log_file: Path, *, today: str | None = None) -> bool:
    """Return True if a validly-signed workout is logged for *today*.

    The day may hold multiple workouts; return True if ANY of today's entries
    verifies (or is acceptably unsigned when no HMAC key is configured).
    """
    entries = load_workout_log(log_file).get(today or _today_str(), [])
    if not entries:
        return False
    key_unavailable = compute_entry_hmac({"_probe": True}) is None
    for entry in entries:
        if verify_entry_hmac(entry):
            return True
        if key_unavailable and "hmac" not in entry:
            _logger.info("HMAC key unavailable — accepting unsigned entry")
            return True
    _logger.warning("HMAC verification failed for today's log entries")
    return False


def is_early_bird_pending(pending_file: Path, *, today: str | None = None) -> bool:
    """Return True if today has an unresolved early-bird pending marker."""
    if not pending_file.exists():
        return False
    try:
        with pending_file.open() as f:
            state = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        _logger.warning(
            "Could not read the early-bird pending marker at %s: %s — treating "
            "it as not pending, so the lock chain proceeds as if no early bird "
            "was claimed today",
            pending_file,
            exc,
        )
        return False
    if not isinstance(state, dict) or state.get("date") != (today or _today_str()):
        return False
    if verify_entry_hmac(state):
        return True
    if compute_entry_hmac({"_probe": True}) is None and "hmac" not in state:
        _logger.info("HMAC key unavailable — accepting unsigned pending marker")
        return True
    _logger.warning("HMAC verification failed for early-bird pending marker")
    return False


def is_sick_day_today(history: SickHistory, *, today: str | None = None) -> bool:
    """Return True if today is recorded as a sick day.

    Thin wrapper around ``_sick_tracker.is_sick_day`` kept here so callers of
    the status layer have one predicate module to import from.
    """
    return _is_sick_day(history, today=today)


def _early_bird_window_open(*, extended: bool, local_minutes: int) -> bool:
    """Deliberate, independent reimplementation of ``_is_early_bird_time``.

    Not shared with ``EarlyBirdMixin._is_early_bird_time`` because too many
    existing tests are pinned to its ``_get_local_time_minutes`` patch point.
    Kept here as a small, separate, pure re-implementation for the status
    layer only — see the module docstring in ``_early_bird.py``.
    """
    start = EARLY_BIRD_START_HOUR * 60
    end = 9 * 60 if extended else EARLY_BIRD_END_HOUR * 60 + EARLY_BIRD_END_MINUTE
    return start <= local_minutes < end
