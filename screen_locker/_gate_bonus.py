"""Live shutdown credit for counted gate earners: paid per unit, as it lands.

A flat earner (LeetCode, reading) pays once a day, stamped
``<name>_bonus_date``. A counted gate earner -- the Automation tutor, one
signed ledger row per verified 15-minute block -- pays per unit, so its stamp
is ``<name>_bonus_units``: the day, and how many units the config already
holds. The live pass pays only the difference, priced by
``Earner.shutdown_for`` so the rung's per-unit split (15 per tutor block) and the
``max_units`` cap come from the registry, never from here.

The workout is counted too, but screen-locker owns its log and
``WorkoutCreditMixin`` applies it; it is never in this pass.

State I/O stays in :mod:`screen_locker._shutdown_base`; these functions read
and update the state dict it hands over.
"""

from __future__ import annotations

from datetime import date
import logging
from typing import TYPE_CHECKING, Any

from screen_locker._earned import earned_units, is_gate, span

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    import earned_time

_logger = logging.getLogger(__name__)


def date_stamp(earner: earned_time.Earner) -> str:
    """The once-per-day key of a flat earner's live pass in the state file."""
    return f"{earner.name}_bonus_date"


def units_stamp(earner: earned_time.Earner) -> str:
    """The per-day key of ``earner``'s applied units in the state file."""
    return f"{earner.name}_bonus_units"


def applied_units(state: dict[str, Any], earner: earned_time.Earner, today: str) -> int:
    """Units of ``earner`` the config already holds today (0 if none stamped)."""
    raw = state.get(units_stamp(earner))
    if not isinstance(raw, dict) or raw.get("date") != today:
        return 0
    units = raw.get("units")
    return units if isinstance(units, int) and units > 0 else 0


def reset_stamps(terms: Iterable[earned_time.Term], today: str) -> dict[str, object]:
    """The stamps for what a daily reset already wrote into the config.

    A flat earner that paid is stamped with the date, a counted gate with
    its units, so the live pass does not add either a second time today.
    """
    stamps: dict[str, object] = {}
    for t in terms:
        if t.earner.kind == "flat" and t.shutdown_minutes:
            stamps[date_stamp(t.earner)] = today
        elif t.earner.kind == "counted" and is_gate(t.earner) and t.answer:
            stamps[units_stamp(t.earner)] = {"date": today, "units": t.answer}
    return stamps


def apply_counted_bonus(
    state: dict[str, Any],
    adjust: Callable[[int], bool],
    earner: earned_time.Earner,
    today: str,
) -> bool:
    """Push shutdown later by ``earner``'s units credited since the last pass.

    ``adjust`` is the mixin's ``_adjust_shutdown_time_by``. Updates ``state``
    (the caller saves it) and returns True when it changed. An unreadable
    ledger or key earns nothing and is logged.
    """
    day = date.fromisoformat(today)
    units = earned_units(earner, day)
    if units is None:
        _logger.warning(
            "%s state could not be checked; no shutdown time for it", earner.label
        )
        return False
    done = applied_units(state, earner, today)
    if units <= done:
        return False
    minutes = earner.shutdown_for(units, day) - earner.shutdown_for(done, day)
    if minutes > 0 and not adjust(minutes):
        _logger.warning("%s bonus: failed to write shutdown config.", earner.label)
        return False
    state[units_stamp(earner)] = {"date": today, "units": units}
    _logger.info(
        "%s bonus: %d unit(s) today, +%s shutdown time.",
        earner.label,
        units,
        span(minutes),
    )
    return True
