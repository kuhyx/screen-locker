"""Headless manual-workout logging: same evidence rules, no UI.

The phone form was the only way to log a manual workout, which made logging
one depend on the phone's foreground: another app stealing focus mid-entry
could interleave or drop a field. That is a bad property for a record that
consumes budget, so this offers the same thing as a command.

What it deliberately is NOT: a way to log a workout without evidence. Every
field the form demands is demanded here, checked by the SAME
``validate_manual_workout``, and a missing or too-short field refuses the
whole run and writes nothing. ``log_manual_workout.py`` was deleted because
it bypassed those checks; this routes through the ordinary sync-ingest path
(``ingest_manual_records``), so validation, the rolling budget, HMAC signing
and workout_id dedup are the shared implementation rather than a second copy
that can drift.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import logging
from typing import TYPE_CHECKING

from screen_locker._manual_sync import ingest_manual_records
from screen_locker._manual_workout import (
    SPORT_CHOICES,
    SPORT_OTHER,
    ManualWorkoutDraft,
    build_sync_payload,
    manual_sync_record_id,
    validate_manual_workout,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

_logger = logging.getLogger(__name__)

__all__ = ["add_manual_arguments", "run_manual_log"]

# (flag, payload key, default). Defaults mirror ManualWorkoutDraft's own, so
# "not supplied" means the same thing headlessly as it does on the form --
# pain_or_injury is "none" (an answer) rather than "" (never asked).
_OPTIONAL_TEXT = (
    ("reservation_phone", "reservation_phone", ""),
    ("techniques", "techniques_practiced", ""),
    ("warm_up", "warm_up_minutes", ""),
    ("pain_or_injury", "pain_or_injury", "none"),
    ("racket", "racket", ""),
    ("balls", "balls", ""),
    ("equipment", "equipment", ""),
)
_OPTIONAL_INT = (
    ("matches_won", "matches_won"),
    ("matches_lost", "matches_lost"),
    ("sets_won", "sets_won"),
    ("sets_lost", "sets_lost"),
)


def add_manual_arguments(parser: argparse.ArgumentParser) -> None:
    """Register every manual-workout field as a flag on ``parser``.

    No flag carries a substantive default: the point is that the caller
    supplies the evidence, so an omitted field must fail validation rather
    than be quietly filled in with something plausible.
    """
    parser.add_argument("--sport", choices=sorted(SPORT_CHOICES), required=True)
    parser.add_argument(
        "--activity",
        default="",
        help=f"what the activity was; required when --sport {SPORT_OTHER}",
    )
    parser.add_argument("--date", default="", help="ISO date; defaults to today")
    parser.add_argument("--start", required=True, help="HH:MM")
    parser.add_argument("--end", required=True, help="HH:MM")
    parser.add_argument("--location", required=True)
    parser.add_argument("--transport", required=True, help="how you got there")
    parser.add_argument("--cost", required=True, help='e.g. "60 PLN" or "none"')
    parser.add_argument("--rpe", required=True, type=int, help="1-10")
    parser.add_argument("--details", required=True, help="what was done")
    parser.add_argument("--went-well", required=True)
    parser.add_argument("--to-improve", required=True)
    parser.add_argument("--feeling", required=True, help="overall feeling")
    for flag, _key, default in _OPTIONAL_TEXT:
        parser.add_argument(f"--{flag.replace('_', '-')}", default=default)
    for flag, _key in _OPTIONAL_INT:
        parser.add_argument(f"--{flag.replace('_', '-')}", default=0, type=int)


def _draft(args: argparse.Namespace) -> ManualWorkoutDraft:
    """Build the draft from parsed flags, with no substantive defaults.

    Optional fields fall back to the dataclass's own defaults so the headless
    path and the form agree on what "not supplied" means.
    """
    return ManualWorkoutDraft(
        sport=args.sport,
        start_time=args.start,
        end_time=args.end,
        location_name=args.location,
        transport_method=args.transport,
        cost=args.cost,
        rpe=args.rpe,
        went_well=args.went_well,
        to_improve=args.to_improve,
        overall_feeling=args.feeling,
        activity_type_other=args.activity if args.sport == SPORT_OTHER else "",
        activity_details=args.details,
        **{key: getattr(args, flag) for flag, key, _default in _OPTIONAL_TEXT},
        **{key: getattr(args, flag) for flag, key in _OPTIONAL_INT},
    )


def run_manual_log(log_file: Path, argv: Sequence[str]) -> int:
    """Log one manual workout headlessly. Returns a process exit code.

    Non-zero means nothing was written: ``ingest_manual_records`` refuses a
    draft that fails validation or that the rolling budget has no room for,
    and it already logs the concrete reason, so a caller never has to guess
    between "rejected" and "already logged".
    """
    parser = argparse.ArgumentParser(
        prog="screen-locker --log-manual-workout",
        description="Log a manual workout without opening any app.",
    )
    add_manual_arguments(parser)
    args = parser.parse_args(list(argv))

    # UTC, matching how the budget windows compute "today" -- a local date
    # near midnight would file the workout in a different window than the one
    # it is then counted in.
    date = args.date or datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    draft = _draft(args)
    # Validated here as well as inside the ingest, purely so a person running
    # this by hand gets the concrete field error on stderr and a non-zero exit
    # instead of only a log line. The ingest re-checks it regardless.
    error = validate_manual_workout(draft)
    if error is not None:
        _logger.error("Manual workout REFUSED — %s. Nothing was written.", error)
        return 1

    record_id = manual_sync_record_id(date, args.start)
    payload = build_sync_payload(draft, date)

    ingested = ingest_manual_records(log_file, [(record_id, payload)], today=date)
    if not ingested:
        _logger.error(
            "Manual workout %s was NOT logged — see the reason logged above "
            "(invalid field, exhausted budget, or already logged)",
            record_id,
        )
        return 1
    _logger.info(
        "Logged manual workout %s. It publishes to the other devices on the "
        "next sync pass (workout-sync.timer, every 15 minutes); run "
        "--sync-only to push it now.",
        record_id,
    )
    return 0
