"""Rebuild a :class:`ManualWorkoutDraft` from a synced manual-workout payload.

Split out of :mod:`screen_locker._manual_sync` to keep every file under the
250-line cap; that module re-exports :func:`reconstruct_draft` and
:func:`is_empty_stub`, so callers and patch targets are unchanged.

Only the raw user inputs are read back — the derived fields (``source``,
``duration_minutes``, ``type``) are recomputed on the PC by ``build_entry``,
which is what keeps a phone from ever dictating what a workout is worth.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from screen_locker._manual_workout import SPORT_OTHER, ManualWorkoutDraft

if TYPE_CHECKING:
    from collections.abc import Mapping

_logger = logging.getLogger(__name__)

# The raw user inputs every real manual workout carries. A payload holding none
# of them is a metadata stub, not a damaged workout: there is nothing to
# recover and no amount of retrying will change that.
_SUBSTANTIVE_FIELDS = frozenset(
    {
        "sport",
        "start_time",
        "end_time",
        "location_name",
        "transport_method",
        "cost",
        "rpe",
        "went_well",
        "to_improve",
        "overall_feeling",
    }
)


def is_empty_stub(payload: Mapping[str, object]) -> bool:
    """True when ``payload`` carries no workout content at all.

    Observed in the wild as ``{"type", "kind", "date"}`` and nothing else --
    a record the phone created without ever attaching the workout. Every sync
    cycle re-reported it as malformed, so a permanent, unfixable condition
    produced an unbounded stream of identical warnings (four every 15 minutes),
    which is how the genuinely actionable lines got lost in the noise.
    """
    return not (_SUBSTANTIVE_FIELDS & set(payload))


def _coerce_int(value: object) -> int:
    """Coerce a JSON scalar to int; raise for a non-numeric (skips the record)."""
    if isinstance(value, (int, str)):
        return int(value)
    raise TypeError(value)


def reconstruct_draft(payload: Mapping[str, object]) -> ManualWorkoutDraft | None:
    """Rebuild a :class:`ManualWorkoutDraft` from a synced manual payload.

    Returns None if a required raw field is missing or mistyped, so a malformed
    record is skipped rather than crashing ingestion. Only the raw user inputs
    are read back — the derived fields (``source``, ``duration_minutes``,
    ``type``) are recomputed by :func:`build_entry` on the PC.
    """
    try:
        sport = str(payload["sport"])
        activity_type_other = (
            str(payload.get("activity_type", "")) if sport == SPORT_OTHER else ""
        )
        return ManualWorkoutDraft(
            sport=sport,
            start_time=str(payload["start_time"]),
            end_time=str(payload["end_time"]),
            location_name=str(payload["location_name"]),
            transport_method=str(payload["transport_method"]),
            cost=str(payload["cost"]),
            rpe=_coerce_int(payload["rpe"]),
            went_well=str(payload["went_well"]),
            to_improve=str(payload["to_improve"]),
            overall_feeling=str(payload["overall_feeling"]),
            reservation_phone=str(payload.get("reservation_phone", "")),
            techniques_practiced=str(payload.get("techniques_practiced", "")),
            warm_up_minutes=str(payload.get("warm_up_minutes", "")),
            pain_or_injury=str(payload.get("pain_or_injury", "none")),
            matches_won=_coerce_int(payload.get("matches_won", 0)),
            matches_lost=_coerce_int(payload.get("matches_lost", 0)),
            sets_won=_coerce_int(payload.get("sets_won", 0)),
            sets_lost=_coerce_int(payload.get("sets_lost", 0)),
            racket=str(payload.get("racket", "")),
            balls=str(payload.get("balls", "")),
            activity_type_other=activity_type_other,
            activity_details=str(payload.get("activity_details", "")),
            equipment=str(payload.get("equipment", "")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        _logger.warning(
            "Synced manual workout payload is malformed (%s: %s) — SKIPPING "
            "this record, so it will not be logged or counted on the PC",
            type(exc).__name__,
            exc,
        )
        return None


def _draft_or_report(
    record_id: str, payload: Mapping[str, object]
) -> ManualWorkoutDraft | None:
    """Rebuild the draft, or report why it cannot be rebuilt and return None.

    The two failure modes are deliberately reported at different levels, because
    only one of them is actionable:

    * an **empty stub** carries no workout at all (seen as ``{type, kind,
      date}``) -- nothing to recover, nothing to fix, so re-reporting it at
      ``warning`` on every 15-minute sync cycle only teaches the reader to
      ignore this logger;
    * a **malformed** payload has real workout fields that would not parse,
      which means genuine credit may be going missing -- that stays loud.
    """
    if is_empty_stub(payload):
        _logger.info(
            "Manual record %s is an empty stub (keys: %s) — no workout data to "
            "ingest; skipping permanently, no credit is being lost",
            record_id,
            sorted(payload),
        )
        return None
    draft = reconstruct_draft(payload)
    if draft is None:
        _logger.warning(
            "Manual record %s is malformed — it HAS workout fields but they "
            "could not be parsed, so real credit may be lost",
            record_id,
        )
    return draft
