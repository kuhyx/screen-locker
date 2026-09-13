#!/usr/bin/env python3
r"""Move one ``log.json`` entry to the day it was really logged on.

Until 2026-09-13 the PC filed workouts under the UTC day, so anything logged
between local midnight and 02:00 CEST landed on *yesterday*. The code now
keys on the local day (``screen_locker._day``); this script repairs an entry
that was filed under the wrong key before that fix.

The HMAC signs ``timestamp`` + ``workout_data`` + ``workout_id`` — never the
day key — so the entry moves verbatim and still verifies. Its ``workout_id``
is kept too: the write chokepoint dedups by id across all days, so the synced
copy (still stamped with the old day) is recognised rather than re-ingested.

Reads and writes ``log.json`` directly rather than importing ``screen_locker``,
like the other scripts here: recovery must work while the package is mid-edit.

Usage:
    python3 scripts/rekey_log_entry.py --workout-id manual:2026-09-12T14:30 \\
        --to 2026-09-13
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys

LOG_FILE = Path(__file__).resolve().parent.parent / "screen_locker" / "log.json"

_logger = logging.getLogger(__name__)


def _report(message: str) -> None:
    """Write one line to stdout (matches the other scripts in this directory)."""
    sys.stdout.write(f"{message}\n")


def rekey(log: dict, workout_id: str, to_day: str) -> str:
    """Move the entry carrying ``workout_id`` under ``to_day`` in place.

    Idempotent: an entry already under ``to_day`` is left alone. Raises
    ``LookupError`` when the id is not in the log at all — a silent no-op
    there would let a caller revoke a sick day against nothing.
    """
    for day, entries in log.items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if entry.get("workout_id") != workout_id:
                continue
            if day == to_day:
                return f"  {workout_id}: already under {to_day} — nothing to do"
            entries.remove(entry)
            if not entries:
                del log[day]
            log.setdefault(to_day, []).append(entry)
            return f"  {workout_id}: moved {day} -> {to_day}"
    msg = f"{workout_id} is not in the log"
    raise LookupError(msg)


def main() -> int:
    """Re-key one entry and rewrite the log, or exit non-zero having changed nothing."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workout-id", required=True, help="entry's workout_id")
    parser.add_argument("--to", required=True, help="YYYY-MM-DD to file it under")
    parser.add_argument("--log-file", default=str(LOG_FILE))
    args = parser.parse_args()

    log_path = Path(args.log_file)
    try:
        log = json.loads(log_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        _logger.exception("Cannot read %s", log_path)
        _report(f"ERROR: cannot read {log_path}: {exc}")
        return 1
    try:
        outcome = rekey(log, args.workout_id, args.to)
    except LookupError as exc:
        _logger.exception("Nothing changed")
        _report(f"ERROR: {exc} — nothing changed")
        return 1
    try:
        log_path.write_text(json.dumps(log, indent=2))
    except OSError as exc:
        _logger.exception("Could not write %s", log_path)
        _report(f"ERROR: could not write {log_path}: {exc}")
        return 1
    _report(outcome)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sys.exit(main())
