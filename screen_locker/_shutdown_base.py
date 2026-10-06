"""Daily shutdown-time base reset for the screen locker.

On each new calendar day the shutdown config is reset to the day's base so
that the day's bonuses always layer on top of a known floor rather than
accumulating indefinitely across days.

The base and every bonus come from the shared earner registry
(``earned_time``, see :mod:`screen_locker._earned`): 20:00 before any penalty,
minus each earner's cut once its ``penalty_from`` day arrives (book-guard's
reading hour, from 2026-10-01). Nothing here is state. The base used to be
persisted in the state file and read back on every reset, which made the
code's default dead; the file now carries only date stamps.

The reset re-derives what today has ALREADY earned and writes base plus that
in one go: the workout hours from today's log and every flat earner's hour
from its gate's ledger. Live credits are read-add-write against the config,
so a workout credited between local midnight and the first locker tick of the
day (a manual log at 00:02, say) had its hours wiped by the reset that
followed -- on 2026-09-13 that left the bar at 21:00 with a counted workout on
disk. Any bonus source that is not a term of this derivation has that bug;
registering it in ``earned_time`` makes it one.

The sick-day state file is cleared on reset so the sick-restore path cannot
overwrite the fresh base when it runs later in the same startup.
"""

from __future__ import annotations

from datetime import date, datetime
import json
import logging
from typing import TYPE_CHECKING, Any

import earned_time

from screen_locker._bonus_lock import bonus_lock
from screen_locker._day import today_str
from screen_locker._earned import (
    earned_today,
    flat_answers,
    flat_earners,
    hhmm,
    span,
)
from screen_locker._log_io import load_workout_log
from screen_locker._weekly_check import count_day_credits

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)

# Morning end assumed when the live config cannot be read: 05:00.
_DEFAULT_MORNING_END = 5 * 60


def base_minutes(day: date | None = None) -> int:
    """The base shutdown for ``day`` (default today), in minutes after midnight.

    Every penalty in force is already taken off.
    """
    target = day or datetime.now().astimezone().date()
    return earned_time.base_for(target, earned_time.EARNERS).shutdown_minutes


def _stamp(earner: earned_time.Earner) -> str:
    """The once-per-day key of ``earner``'s live pass in the state file."""
    return f"{earner.name}_bonus_date"


def today_credit_count(log_file: Path, today: str) -> int:
    """Return how many distinct workouts today's log counts.

    Counted with the same :func:`~screen_locker._weekly_check.count_day_credits`
    rule as the weekly total, so a workout recorded twice earns once.
    """
    entries = load_workout_log(log_file).get(today, [])
    return count_day_credits(today, [e for e in entries if isinstance(e, dict)])


def _load_state(state_file: Path) -> dict[str, Any]:
    """Return the reset state, or an empty dict when it is missing or corrupt.

    A corrupt file is logged and treated as "nothing stamped": the reset then
    runs again, which is idempotent, and a flat hour is re-applied at worst
    once, capped by the ceiling.
    """
    if not state_file.exists():
        return {}
    try:
        with state_file.open() as f:
            state: dict[str, Any] = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        _logger.warning(
            "Could not read shutdown reset state from %s: %s -- treating today "
            "as not yet reset",
            state_file,
            exc,
        )
        return {}
    return state


def _save_state(state_file: Path, state: dict[str, Any]) -> None:
    """Write the reset state, logging rather than raising on failure."""
    try:
        with state_file.open("w") as f:
            json.dump(state, f, indent=2)
    except OSError as exc:
        _logger.warning("Failed to write shutdown reset state: %s", exc)


def _clear_sick_day_state(sick_day_state_file: Path | None) -> None:
    """Remove stale sick-day state so it does not override the base reset."""
    if sick_day_state_file is None or not sick_day_state_file.exists():
        return
    try:
        sick_day_state_file.unlink()
        _logger.info("Daily base reset: cleared stale sick-day state.")
    except OSError as exc:
        _logger.warning("Daily base reset: could not remove sick-day state: %s", exc)


def reset_to_base_if_new_day(
    state_file: Path,
    mixin: object,
    sick_day_state_file: Path | None = None,
    log_file: Path | None = None,
) -> bool:
    """Reset the shutdown config to the base if a new calendar day began.

    Writes the base plus whatever today has already earned -- the workout
    time in *log_file* (see :func:`today_credit_count`) and every flat
    earner's time -- via *mixin*._write_shutdown_config (with restore=True so
    the script allows moving the time earlier), stamps ``last_reset_date`` in
    *state_file*, and removes *sick_day_state_file* if it exists so the
    sick-restore path does not fight with the fresh base on the same startup.

    Returns True if a reset was performed, False if today was already reset.
    """
    with bonus_lock(state_file):
        return _reset(state_file, mixin, sick_day_state_file, log_file)


def _reset(
    state_file: Path,
    mixin: object,
    sick_day_state_file: Path | None,
    log_file: Path | None,
) -> bool:
    """:func:`reset_to_base_if_new_day`'s body; the caller holds the lock."""
    today = today_str()
    if _load_state(state_file).get("last_reset_date") == today:
        return False

    answers: dict[str, int | bool | None] = dict(flat_answers())
    answers[earned_time.WORKOUT.name] = (
        today_credit_count(log_file, today) if log_file is not None else 0
    )
    # The registry is passed explicitly: flat_answers iterated this same
    # tuple, so the earners asked and the earners summed can never differ.
    day = earned_time.resolve(
        answers, datetime.now().astimezone().date(), earned_time.EARNERS
    )
    target = day.shutdown_minutes

    # Preserve the morning end from the live config.
    config = mixin._read_shutdown_config()
    morning_end = config[2] if config else _DEFAULT_MORNING_END

    ok: bool = mixin._write_shutdown_config(target, target, morning_end, restore=True)
    if not ok:
        _logger.warning("Daily base reset: failed to write shutdown config.")
        return False

    _clear_sick_day_state(sick_day_state_file)

    # The flat bonuses are stamped here too: the reset already included them,
    # so the live pass below must not add them a second time today.
    new_state: dict[str, Any] = {"last_reset_date": today}
    for term in day.terms:
        if term.earner.kind == "flat" and term.shutdown_minutes:
            new_state[_stamp(term.earner)] = today
    _save_state(state_file, new_state)

    earned = " + ".join(
        f"{span(t.shutdown_minutes)} {t.earner.label}" for t in day.terms
    )
    _logger.info(
        "Daily base reset: %s (base %s + %s already earned today).",
        hhmm(target),
        hhmm(day.base.shutdown_minutes),
        earned,
    )
    return True


def _apply_flat_bonus(
    state_file: Path,
    mixin: object,
    earner: earned_time.Earner,
) -> bool:
    """Push shutdown later by one earner's once-per-day time, if it is earned.

    The daily reset only sees a bonus earned before it ran; this is the live
    counterpart for the usual case, where the solve or the reading lands
    hours later and is picked up by the next timer tick. Idempotent through
    the earner's stamp in *state_file*, which the reset sets as well when it
    already included the bonus.

    Returns True if the bonus was applied on this call.
    """
    today = today_str()
    state = _load_state(state_file)
    stamp = _stamp(earner)
    if state.get(stamp) == today:
        return False
    answer = earned_today(earner)
    if answer is None:
        _logger.warning(
            "%s state could not be checked; no shutdown time for it", earner.label
        )
        return False
    if not answer:
        return False
    minutes = earner.shutdown_minutes
    if not mixin._adjust_shutdown_time_by(minutes):
        _logger.warning("%s bonus: failed to write shutdown config.", earner.label)
        return False
    state[stamp] = today
    _save_state(state_file, state)
    _logger.info("%s bonus: +%s shutdown time today.", earner.label, span(minutes))
    return True


def apply_flat_bonuses_if_new(state_file: Path, mixin: object) -> None:
    """Every once-per-day flat bonus, in registry order (LeetCode, reading, ...).

    The workout is not among them: it is counted, and its live credit is
    applied by :class:`~screen_locker._workout_credit.WorkoutCreditMixin`.
    """
    with bonus_lock(state_file):
        for earner in flat_earners():
            _apply_flat_bonus(state_file, mixin, earner)
