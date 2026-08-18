#!/usr/bin/env python3
"""One-off correction: re-file the 2026-07-26 walk as sport "other".

On 2026-07-26 the manual-workout sport selector could not be changed while the
screen was locked (``_manual_workout_dialog._mw_sport_row`` has the mechanism),
so an hour-long walk had to be logged through the table-tennis form. The
workout is genuine and its credit is correct; only its *shape* is wrong.

This rebuilds that one entry through the same ``ManualWorkoutDraft`` ->
``validate_manual_workout`` -> ``build_entry`` path the form itself uses, so
the result is the entry the form would have produced, not an approximation of
it, and re-signs it with the writer's own HMAC key.

``start_time`` and the date are deliberately untouched: ``workout_id`` is
derived from them, so keeping it stable means the phone-side CRDT copy
converges on the corrected record rather than gaining a duplicate.

The walk's own details are NOT hardcoded here -- they are read from the entry
and from ``--details`` -- because this file is tracked and the log is not.

Kept in the repo after its single run as the audit trail for the edit; it is
idempotent, so re-running it reports that there is nothing to do.

Usage (needs the root-owned key at /etc/workout-locker/hmac.key):
    sudo python3 scripts/fix_2026_07_26_sport.py            # show the diff
    sudo python3 scripts/fix_2026_07_26_sport.py --apply    # write it
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import shutil
import sys

from gatelock.log_integrity import compute_entry_hmac, verify_entry_hmac

from screen_locker import _manual_workout
from screen_locker._log_io import read_raw_log

# ``print`` is banned repo-wide, so the diff this script exists to show goes
# through a logger wired to stdout in main().
_logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_FILE = REPO_ROOT / "screen_locker" / "log.json"
TARGET_DATE = "2026-07-26"
TARGET_START = "03:30"
TARGET_WORKOUT_ID = _manual_workout.manual_sync_record_id(TARGET_DATE, TARGET_START)

ACTIVITY_LABEL = "walking"
DEFAULT_DETAILS = (
    "Pure walking: walked for ~an hour and did ~5 km in total at my regular "
    "walking pace, on the route in the location field."
)


def corrected_workout_data(old: dict, details: str) -> dict[str, object]:
    """Rebuild ``old`` as the ``sport: "other"`` entry the form would produce.

    Goes through the real draft/validate/build path rather than editing keys,
    so the result carries exactly the writer's key set -- no table-tennis
    leftovers, no fields a hand-written dict would forget.
    """
    draft = _manual_workout.ManualWorkoutDraft(
        sport=_manual_workout.SPORT_OTHER,
        start_time=str(old["start_time"]),
        end_time=str(old["end_time"]),
        location_name=str(old["location_name"]),
        transport_method=str(old["transport_method"]),
        cost=str(old["cost"]),
        rpe=int(old["rpe"]),
        went_well=str(old["went_well"]),
        to_improve=str(old["to_improve"]),
        overall_feeling=str(old["overall_feeling"]),
        reservation_phone=str(old.get("reservation_phone", "")),
        pain_or_injury=str(old.get("pain_or_injury", "none")),
        # "this was pure walking" was a placeholder the table-tennis form
        # forced into these; they are not technique or warm-up values.
        techniques_practiced="",
        warm_up_minutes="",
        activity_type_other=ACTIVITY_LABEL,
        activity_details=details,
        equipment="",
    )
    error = _manual_workout.validate_manual_workout(draft)
    if error is not None:
        sys.exit(f"The corrected entry would not pass the form's own rules: {error}")
    return _manual_workout.build_entry(draft)


def find_target(logs: dict) -> dict:
    """Return the one entry to correct, or exit with a reason."""
    entries = logs.get(TARGET_DATE)
    if not isinstance(entries, list):
        sys.exit(f"No list of entries for {TARGET_DATE} in {LOG_FILE}")
    matches = [
        e
        for e in entries
        if isinstance(e, dict) and e.get("workout_id") == TARGET_WORKOUT_ID
    ]
    if len(matches) != 1:
        sys.exit(
            f"Expected exactly one entry with workout_id {TARGET_WORKOUT_ID} "
            f"on {TARGET_DATE}, found {len(matches)}"
        )
    return matches[0]


def main() -> int:
    """Show, and optionally apply, the correction."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="write the change (default: dry run)"
    )
    parser.add_argument(
        "--details",
        default=DEFAULT_DETAILS,
        help="what the activity actually was (goes in activity_details)",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)

    logs = read_raw_log(LOG_FILE)
    entry = find_target(logs)

    if not verify_entry_hmac(entry):
        sys.exit(
            "Refusing to touch an entry whose existing HMAC does not verify "
            "(bad signature, or the key at /etc/workout-locker/hmac.key is "
            "unreadable -- run under sudo)."
        )

    old_data = entry["workout_data"]
    if not isinstance(old_data, dict):
        sys.exit("workout_data is not an object")

    new_data = corrected_workout_data(old_data, args.details)
    if new_data == old_data:
        _logger.info("Already corrected; nothing to do.")
        return 0

    for key in sorted(set(old_data) | set(new_data)):
        before, after = old_data.get(key, "<absent>"), new_data.get(key, "<absent>")
        if before != after:
            _logger.info("  %s:\n    - %r\n    + %r", key, before, after)

    if not args.apply:
        _logger.info("\nDry run. Re-run with --apply to write.")
        return 0

    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = LOG_FILE.with_suffix(f".json.bak-{stamp}")
    shutil.copy2(LOG_FILE, backup)
    _logger.info("\nBacked up to %s", backup)

    entry["workout_data"] = new_data
    entry.pop("hmac", None)
    signature = compute_entry_hmac(entry)
    if signature is None:
        sys.exit("Could not sign the corrected entry; log left untouched.")
    entry["hmac"] = signature
    # Match write_signed_entry's serialization exactly, so the next real
    # workout does not produce a spurious whitespace diff.
    with LOG_FILE.open("w") as handle:
        json.dump(logs, handle, indent=2)

    reread = find_target(read_raw_log(LOG_FILE))
    if not verify_entry_hmac(reread):
        sys.exit("Written entry does not verify! Restore from the backup above.")
    _logger.info("Corrected entry written and its HMAC verifies.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
