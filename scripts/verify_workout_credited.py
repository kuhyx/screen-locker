#!/usr/bin/env python3
"""Fail unless a counted workout is on disk for a given date.

A gate, not a report. The 2026-08-24 recovery revokes a sick day and re-arms
enforcement on the strength of "the workout was ingested" -- so that claim has
to be checked by code before the irreversible steps run, not asserted by
whoever is watching the output scroll past.

Exits non-zero when the date has no counted workout, which stops the calling
script before it revokes anything.

Reads ``log.json`` directly rather than importing ``screen_locker``, matching
``add_scheduled_skip.py``: these scripts must keep working even when the
package itself is mid-edit.

Usage:
    python3 scripts/verify_workout_credited.py --date 2026-08-24
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys

LOG_FILE = Path(__file__).resolve().parent.parent / "screen_locker" / "log.json"

# Mirrors ``_weekly_check.COUNTED_WORKOUT_TYPES``. Duplicated deliberately: a
# gate that imports the code it is checking cannot fail independently of it.
COUNTED_WORKOUT_TYPES = frozenset(
    {
        "phone_verified",
        "runnerup_verified",
        "pc_workout_verified",
        "manual_workout",
    }
)


# This script is a gate: it decides whether the rest of the recovery may
# proceed. A read failure that only reaches stdout can be mistaken for a plain
# "not credited" verdict, so it is logged loudly as well.
_logger = logging.getLogger(__name__)


def _report(message: str) -> None:
    """Write one line to stdout (matches the other scripts in this directory)."""
    sys.stdout.write(f"{message}\n")


def main() -> int:
    """Report whether ``--date`` holds a counted workout; non-zero if not."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="YYYY-MM-DD to check")
    parser.add_argument("--log-file", default=str(LOG_FILE))
    args = parser.parse_args()

    log_path = Path(args.log_file)
    if not log_path.is_file():
        _report(f"FAIL: no workout log at {log_path}")
        return 1

    try:
        log = json.loads(log_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        _logger.exception(
            "Could not read %s — cannot tell whether the workout was "
            "credited, so this gate fails closed",
            log_path,
        )
        _report(f"FAIL: could not read {log_path}: {exc}")
        return 1

    entries = log.get(args.date) or []
    counted = [
        entry
        for entry in entries
        if (entry.get("workout_data") or {}).get("type") in COUNTED_WORKOUT_TYPES
    ]

    if not counted:
        _report(f"FAIL: no counted workout logged for {args.date}.")
        _report(f"      {len(entries)} entr(ies) exist for that date, none counted.")
        _report("      Nothing to revoke a sick day against — stopping here so")
        _report("      enforcement is not re-armed against a log that cannot see")
        _report("      the workout you actually did.")
        return 1

    for entry in counted:
        data = entry.get("workout_data") or {}
        _report(
            f"OK: {args.date} has {data.get('type')} "
            f"(id={entry.get('workout_id')}, source={data.get('source', 'n/a')})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
