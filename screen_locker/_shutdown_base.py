"""Daily shutdown-time base reset for the screen locker.

On each new calendar day the shutdown config is reset to the day's base so
that the day's bonuses always layer on top of a known floor rather than
accumulating indefinitely across days.

The base and every bonus come from the shared earner registry in force that
day (``earned_time``, see :mod:`screen_locker._earned`). Nothing here is
state: the file carries only stamps (``<name>_bonus_date`` for a flat
earner, ``<name>_bonus_units`` for a counted gate, :mod:`._gate_bonus`).

The reset re-derives what today has ALREADY earned and writes base plus that
in one go: the workout hours from today's log and every flat earner's hour
from its gate's ledger. Live credits are read-add-write against the config,
so a workout credited between local midnight and the first locker tick of the
day (a manual log at 00:02, say) had its hours wiped by the reset that
followed -- on 2026-09-13 that left the bar at 21:00 with a counted workout on
disk. Any bonus source that is not a term of this derivation has that bug;
registering it in ``earned_time`` makes it one.

The reset clears the sick-day state file, so sick-restore cannot overwrite
the fresh base later in the same startup.
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
    counted_gate_earners,
    earned_today,
    first_credits,
    first_minutes,
    flat_earners,
    hhmm,
    registry,
    span,
)
from screen_locker._gate_bonus import apply_counted_bonus, date_stamp, reset_stamps
from screen_locker._grace_floor import save_lift
from screen_locker._log_io import load_workout_log
from screen_locker._shutdown_target import gather
from screen_locker._weekly_check import count_day_credits

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)

# Morning end assumed when the live config cannot be read: 05:00.
_DEFAULT_MORNING_END = 5 * 60


def base_minutes(day: date | None = None) -> int:
    """The base shutdown for ``day`` (default today), in minutes after midnight.

    Every penalty in force is already taken off; from today on, a gate's not
    before it has paid out (:func:`~screen_locker._earned.first_credits`).
    """
    target = day or datetime.now().astimezone().date()
    earners = registry(target)
    starts = first_credits(earners, target)
    if starts is None:
        return earned_time.base_for(target, earners).shutdown_minutes
    return earned_time.base_for(target, earners, first_credits=starts).shutdown_minutes


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

    derived = gather(date.fromisoformat(today), log_file)
    day = derived.resolution
    target = derived.minutes

    # Preserve the morning end from the live config.
    config = mixin._read_shutdown_config()
    morning_end = config[2] if config else _DEFAULT_MORNING_END

    ok: bool = mixin._write_shutdown_config(target, target, morning_end, restore=True)
    if not ok:
        _logger.warning("Daily base reset: failed to write shutdown config.")
        return False

    _clear_sick_day_state(sick_day_state_file)
    # Later additions are paid out of the grace lift first (see _grace_floor).
    save_lift(derived.lift)

    # The bonuses the reset already included are stamped, so the live pass
    # does not add them a second time today.
    new_state: dict[str, Any] = {"last_reset_date": today}
    new_state.update(reset_stamps(day.terms, today))
    _save_state(state_file, new_state)

    earned = " + ".join(
        f"{span(t.shutdown_minutes)} {t.earner.label}" for t in day.terms
    )
    _logger.info(
        "Daily base reset: %s (base %s + %s already earned today%s%s).",
        hhmm(target),
        hhmm(day.base.shutdown_minutes),
        earned,
        "; rest day" if derived.rest_day else "",
        f"; grace floor {hhmm(derived.grace)}" if derived.grace is not None else "",
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
    stamp = date_stamp(earner)
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
    minutes = first_minutes(earner, date.fromisoformat(today))
    if not mixin._adjust_shutdown_time_by(minutes):
        _logger.warning("%s bonus: failed to write shutdown config.", earner.label)
        return False
    state[stamp] = today
    _save_state(state_file, state)
    _logger.info("%s bonus: +%s shutdown time today.", earner.label, span(minutes))
    return True


def apply_flat_bonuses_if_new(state_file: Path, mixin: object) -> None:
    """Every once-per-day flat bonus, in registry order (LeetCode, reading, ...).

    Then each counted gate's new units (:mod:`._gate_bonus`); the workout's
    live credit is ``WorkoutCreditMixin``'s.
    """
    with bonus_lock(state_file):
        for earner in flat_earners():
            _apply_flat_bonus(state_file, mixin, earner)
        adjust = mixin._adjust_shutdown_time_by
        for earner in counted_gate_earners():
            state = _load_state(state_file)
            if apply_counted_bonus(state, adjust, earner, today_str()):
                _save_state(state_file, state)
        # Last, so the floor compares against everything earned so far.
        mixin._apply_grace_floor(getattr(mixin, "log_file", None))
