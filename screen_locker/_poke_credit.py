"""Credit one poked StrongLifts session: the sync's ingest, minus the network.

The phone POSTs a finished session straight to the PC
(``docs/DOCS-workout-poke-contract.md``); this applies it through exactly the
path a synced session takes -- :func:`ingest_session_records`, which
re-validates and dedups under ``log.lock``, then the shared
:meth:`~screen_locker._workout_credit.WorkoutCreditMixin._apply_credit_for_written_entry`
(slot-based credit, shutdown push, debt, the "Workout credited" notification).
Nothing here computes a reward of its own.

Each call builds a FRESH headless locker, the same object
``--sync-only`` uses, so no state leaks from one request into the next.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import logging
from typing import TYPE_CHECKING, Final, cast

from screen_locker._cli import _headless_locker
from screen_locker._constants import (
    EXTRA_BENEFITS_FILE,
    SHUTDOWN_BASE_FILE,
    SHUTDOWN_CONFIG_FILE,
    SICK_DAY_STATE_FILE,
)
from screen_locker._credit_notify import gaming_minutes_today
from screen_locker._day import today_str
from screen_locker._earned import hhmm
from screen_locker._extra_benefits import process_week_transition
from screen_locker._grace_floor import tonight_minutes
from screen_locker._session_sync import ingest_session_records, validate_session
from screen_locker._shutdown import read_shutdown_config
from screen_locker._shutdown_base import reset_to_base_if_new_day
from screen_locker.screen_lock import ScreenLocker

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path

    from screen_locker._workout_credit import WorkoutCreditResult


__all__ = [
    "BatchOutcome",
    "PokeOutcome",
    "credit_session",
    "credit_sessions",
    "current_gaming_minutes",
    "current_shutdown",
]

_logger: Final = logging.getLogger(__name__)


@dataclass(frozen=True)
class PokeOutcome:
    """What crediting one poked session did; ``reason`` is for the phone's UI."""

    ok: bool
    credited: bool
    duplicate: bool
    reason: str


@dataclass(frozen=True)
class BatchOutcome:
    """What one batch did: newly logged ids, and how many of those earned time."""

    ingested: tuple[str, ...]
    credited: int


class PokeLocker(ScreenLocker):
    """The headless locker plus the two steps a poke needs, as public calls."""

    def start_the_day(self) -> None:
        """Run the new-day reset the locker's startup runs, in the same order.

        Mirrors ``StartupChecksMixin._check_non_verify_exits``, not
        ``sync_now`` (which never resets): the week transition (streak,
        early-bird window) first, then the daily reset.
        """
        for reward in process_week_transition(self.log_file, EXTRA_BENEFITS_FILE):
            _logger.info("Weekly reward: %s", reward)
        reset_to_base_if_new_day(
            SHUTDOWN_BASE_FILE,
            self,
            sick_day_state_file=SICK_DAY_STATE_FILE,
            log_file=self.log_file,
        )

    def credit_written(
        self, entry: dict[str, str], prior_entries: list[dict[str, object]]
    ) -> WorkoutCreditResult:
        """``SyncMixin._credit_ingested_workout``, keeping the result."""
        self.workout_data = entry
        return self._apply_credit_for_written_entry(prior_entries)


def fresh_locker() -> PokeLocker:
    """The ``--sync-only`` headless locker: no Tk, no window, no lock."""
    return cast("PokeLocker", _headless_locker(PokeLocker))


def current_shutdown() -> str | None:
    """Tonight's shutdown from ``/etc/shutdown-schedule.conf`` as ``HH:MM``."""
    config = read_shutdown_config(SHUTDOWN_CONFIG_FILE)
    if config is None:
        _logger.warning(
            "Workout poke: shutdown config unreadable, replying shutdown=null"
        )
        return None
    return hhmm(tonight_minutes(config, date.fromisoformat(today_str())))


def current_gaming_minutes(log_file: Path) -> int | None:
    """Today's gaming budget (``None`` and a warning when it cannot be summed)."""
    return gaming_minutes_today(log_file)


def _precheck(record_id: str, payload: Mapping[str, object]) -> str | None:
    """Why the session can never count, or ``None`` if it can.

    ``ingest_session_records`` applies the same rules but only returns what
    it ingested, so a rejection would be indistinguishable from a duplicate.
    """
    day = payload.get("date")
    if not isinstance(day, str) or not day:
        return f"session {record_id} has no usable date ({day!r}), so it cannot count"
    valid, detail = validate_session(payload)
    if not valid:
        return f"session {record_id} does not count: {detail}"
    return None


def credit_session(record_id: str, payload: Mapping[str, object]) -> PokeOutcome:
    """Reset the day if new, then ingest and credit one session.

    The caller serialises calls; the ingest also holds ``log.lock`` and the
    credit the shutdown-state lock, so a concurrent sync or locker pass is safe.
    """
    locker = fresh_locker()
    locker.start_the_day()
    problem = _precheck(record_id, payload)
    if problem is not None:
        _logger.warning("Workout poke not credited: %s", problem)
        return PokeOutcome(ok=False, credited=False, duplicate=False, reason=problem)

    results: list[WorkoutCreditResult] = []

    def on_ingested(
        entry: dict[str, str], prior_entries: list[dict[str, object]]
    ) -> None:
        results.append(locker.credit_written(entry, prior_entries))

    ingested = ingest_session_records(
        locker.log_file, [(record_id, payload)], on_ingested=on_ingested
    )
    if not ingested or not results:
        reason = (
            f"session {record_id} is already in the PC's log (the sync or an "
            "earlier poke got there first); nothing new to credit"
        )
        _logger.info("Workout poke duplicate: %s", reason)
        return PokeOutcome(ok=True, credited=False, duplicate=True, reason=reason)
    if results[0].already_counted_today:
        reason = (
            f"session {record_id} was logged, but today's slot for it was already "
            "paid by another copy of the same workout; no extra time"
        )
        _logger.warning("Workout poke not credited: %s", reason)
        return PokeOutcome(ok=True, credited=False, duplicate=False, reason=reason)
    _logger.info("Workout poke credited session %s", record_id)
    return PokeOutcome(
        ok=True, credited=True, duplicate=False, reason="workout credited"
    )


def credit_sessions(
    records: Iterable[tuple[str, Mapping[str, object]]],
) -> BatchOutcome:
    """Reset the day if new, then ingest and credit a batch of synced sessions.

    ``SyncMixin._ingest_synced_sessions`` with one fresh locker for the whole
    batch -- what the Firebase stream (:mod:`screen_locker._session_stream`)
    runs per event. Already-logged ids cost one ``log.json`` read and write
    nothing; invalid ones are warned about by the ingest itself.
    """
    locker = fresh_locker()
    locker.start_the_day()
    results: list[WorkoutCreditResult] = []

    def on_ingested(
        entry: dict[str, str], prior_entries: list[dict[str, object]]
    ) -> None:
        results.append(locker.credit_written(entry, prior_entries))

    ingested = ingest_session_records(locker.log_file, records, on_ingested=on_ingested)
    credited = sum(not result.already_counted_today for result in results)
    if len(results) > credited:
        _logger.warning(
            "%d streamed session(s) were logged but earned no time: today's slot "
            "was already paid by another copy of the same workout",
            len(results) - credited,
        )
    return BatchOutcome(ingested=tuple(ingested), credited=credited)
