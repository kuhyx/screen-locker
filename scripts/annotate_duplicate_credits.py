#!/usr/bin/env python3
"""Record which log entries are two recordings of one workout.

Written for the 2026-08-29 outage: a StrongLifts session reaches ``log.json``
twice -- once as ``phone_verified`` from the phone sync, once as
``pc_workout_verified`` from the PC session sync -- and both are genuine,
signed records of the same hour in the gym. ``_weekly_check`` now collapses
them onto one credit, so the *numbers* are right; this makes the *history* say
so rather than leaving a reader to notice two entries share a duration.

Annotates, never deletes, for two independent reasons. Deleting is
self-undoing: every re-ingest path dedups against ``log.json``'s own contents,
so ``_session_sync`` re-pulls a removed ``pc_workout_verified`` from the CRDT
store on the next 15-minute ``workout-sync.timer`` tick and re-applies its
shutdown credit. And it is the repo's stated position on signed data -- see
``scripts/revoke_sick_day.py``. No entry is modified, so no HMAC is touched.

The ledger is descriptive: nothing reads it to decide a lock. If it ever
disagrees with :func:`~screen_locker._weekly_check.count_day_credits` the
script fails rather than writing, because a ledger contradicting the rule it
documents is worse than no ledger.

Usage:
    python3 scripts/annotate_duplicate_credits.py            # show the diff
    python3 scripts/annotate_duplicate_credits.py --apply    # write it
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
import shutil
import sys
from typing import TypedDict

from screen_locker._log_io import load_workout_log
from screen_locker._weekly_check import count_day_credits, credit_key

_logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_FILE = REPO_ROOT / "screen_locker" / "log.json"
LEDGER_FILE = REPO_ROOT / "screen_locker" / "duplicate_credits.json"

# A credit is "shared" only once a second entry claims it; one entry per
# credit is the normal case and earns no ledger record.
_SHARED_BY = 2

_NOTE = (
    "Two ingestion paths recorded one workout. Both entries are genuine and "
    "stay in the log; they share a single credit."
)


class CreditRecord(TypedDict):
    """One credit that more than one log entry recorded.

    Typed rather than a bare dict so ``duplicate_of`` is known to be a list
    of strings at both use sites -- otherwise ``len()`` and ``join()`` on it
    need a typing suppression, which this repo bans outright.
    """

    credit: str
    counted: str
    duplicate_of: list[str]
    note: str


def _entry_id(entry: dict, date_str: str, index: int) -> str:
    """Return a stable identifier for a log entry.

    Args:
        entry: The log entry.
        date_str: The date key it is filed under.
        index: Its position in that date's list, used when the entry predates
            ``workout_id`` and so has nothing else to name it by.

    Returns:
        The entry's ``workout_id`` when it has one, else ``<date>#<index>``.
    """
    workout_id = entry.get("workout_id")
    return str(workout_id) if workout_id else f"{date_str}#{index}"


def _shared_credits(date_str: str, entries: list[dict]) -> list[CreditRecord]:
    """Return one record per credit that more than one entry shares.

    Args:
        date_str: The date key the entries are filed under.
        entries: That date's log entries.

    Returns:
        A list of ledger records, empty when every entry earns its own credit.
    """
    groups: dict[tuple[str, str], list[tuple[int, dict]]] = defaultdict(list)
    for index, entry in enumerate(entries):
        key = credit_key(date_str, index, entry)
        if key is not None:
            groups[key].append((index, entry))

    records: list[CreditRecord] = []
    for key, members in sorted(groups.items()):
        if len(members) < _SHARED_BY:
            continue
        # Earliest timestamp first: the canonical entry is the one that landed
        # when the workout actually happened, not the copy a later sync filed.
        ordered = sorted(members, key=lambda m: str(m[1].get("timestamp", "")))
        records.append(
            {
                "credit": key[0],
                "counted": _entry_id(ordered[0][1], date_str, ordered[0][0]),
                "duplicate_of": [
                    _entry_id(entry, date_str, index) for index, entry in ordered[1:]
                ],
                "note": _NOTE,
            }
        )
    return records


def build_ledger(logs: dict[str, list[dict]]) -> dict[str, list[CreditRecord]]:
    """Build the full ledger from a loaded workout log.

    Args:
        logs: The normalised ``{date: [entry, ...]}`` log.

    Returns:
        A date-keyed ledger holding only the days with a shared credit.
    """
    return {
        date_str: records
        for date_str, entries in sorted(logs.items())
        if (records := _shared_credits(date_str, entries))
    }


def check_ledger_agrees(
    logs: dict[str, list[dict]],
    ledger: dict[str, list[CreditRecord]],
) -> None:
    """Exit unless the ledger's arithmetic matches the canonical credit rule.

    For every day, the entries that earn a credit minus the ones the ledger
    calls duplicates must equal ``count_day_credits``. If those disagree, the
    ledger is describing a rule the locker does not use.

    Args:
        logs: The normalised workout log.
        ledger: The ledger built from it.
    """
    for date_str, entries in logs.items():
        earning = sum(
            1
            for index, entry in enumerate(entries)
            if credit_key(date_str, index, entry) is not None
        )
        duplicates = sum(
            len(record["duplicate_of"]) for record in ledger.get(date_str, [])
        )
        expected = count_day_credits(date_str, entries)
        if earning - duplicates != expected:
            sys.exit(
                f"Ledger disagrees with count_day_credits on {date_str}: "
                f"{earning} earning - {duplicates} duplicate != {expected}. "
                "Refusing to write a ledger that contradicts the credit rule."
            )


def _describe(ledger: dict[str, list[CreditRecord]]) -> str:
    """Render the ledger as a human-readable summary.

    Args:
        ledger: The ledger to describe.

    Returns:
        One line per shared credit, or a single line saying there are none.
    """
    if not ledger:
        return "No shared credits found — every entry records its own workout."
    lines = [f"{sum(len(v) for v in ledger.values())} shared credit(s):"]
    lines.extend(
        f"  {date_str}  {record['counted']}  absorbs  "
        f"{', '.join(record['duplicate_of'])}"
        for date_str, records in ledger.items()
        for record in records
    )
    return "\n".join(lines)


def _write(ledger: dict[str, list[CreditRecord]]) -> None:
    """Back up any existing ledger and write the new one.

    Args:
        ledger: The ledger to persist.
    """
    if LEDGER_FILE.exists():
        stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
        backup = LEDGER_FILE.with_suffix(f".json.bak-{stamp}")
        shutil.copy2(LEDGER_FILE, backup)
        _logger.info("Backed up existing ledger to %s", backup)
    # indent=2 matches write_signed_entry, so both files diff the same way.
    LEDGER_FILE.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    _logger.info("Wrote %s", LEDGER_FILE)


def main() -> int:
    """Show, and optionally write, the duplicate-credit ledger.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="write the ledger (default: dry run)"
    )
    args = parser.parse_args()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])

    logs = load_workout_log(LOG_FILE)
    if not logs:
        sys.exit(f"No workout log to annotate at {LOG_FILE}")

    ledger = build_ledger(logs)
    check_ledger_agrees(logs, ledger)
    _logger.info("%s", _describe(ledger))

    existing = (
        json.loads(LEDGER_FILE.read_text(encoding="utf-8"))
        if LEDGER_FILE.exists()
        else None
    )
    if existing == ledger:
        _logger.info("Ledger is already up to date; nothing to do.")
        return 0
    if not args.apply:
        _logger.info("Dry run — re-run with --apply to write %s", LEDGER_FILE)
        return 0
    _write(ledger)
    return 0


if __name__ == "__main__":
    sys.exit(main())
