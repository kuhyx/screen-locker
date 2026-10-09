"""``--backfill-workout-ledger``: one-shot, idempotent ledger backfill.

    python -m screen_locker.screen_lock --backfill-workout-ledger --dry-run
    python -m screen_locker.screen_lock --backfill-workout-ledger
        --from 2026-10-01 --to 2026-10-09 [--dry-run]

Writes a signed row for every workout credit slot already in ``log.json`` for
the days (default: today) and for every declared rest day in that range --
the credits made before the ledger existed. Rows already present (same
``entry_id``) are skipped, so running it twice writes nothing the second
time. ``--dry-run`` prints the rows it would add, unsigned, with a count per
source, and writes nothing.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, timedelta
import json
import sys
from typing import TYPE_CHECKING, Any

from screen_locker._day import today_str
from screen_locker._log_io import load_workout_log
from screen_locker._rest_day import rest_day_declarations
from screen_locker._workout_ledger import (
    append_rows,
    credit_row,
    existing_rows,
    ledger_path,
    new_rows,
    rest_row,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path


def backfill_rows(log_file: Path, first: date, last: date) -> list[dict[str, Any]]:
    """Unsigned rows for every credit slot and rest day from ``first`` to ``last``."""
    logs = load_workout_log(log_file)
    declared = rest_day_declarations()
    rows: list[dict[str, Any]] = []
    day = first
    while day <= last:
        iso = day.isoformat()
        entries = [e for e in logs.get(iso, []) if isinstance(e, dict)]
        for index in range(len(entries)):
            row = credit_row(iso, entries, index)
            if row is not None and row["entry_id"] not in {r["entry_id"] for r in rows}:
                rows.append(row)
        if day in declared:
            rows.append(rest_row(day, declared[day]))
        day += timedelta(days=1)
    return rows


def run_backfill(log_file: Path, argv: Sequence[str]) -> int:
    """Backfill (or preview) the workout ledger. Returns a process exit code."""
    parser = argparse.ArgumentParser(prog="screen-locker --backfill-workout-ledger")
    parser.add_argument("--from", dest="first", default=None, help="YYYY-MM-DD")
    parser.add_argument("--to", dest="last", default=None, help="YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true", help="print, write nothing")
    args = parser.parse_args(list(argv))
    today = date.fromisoformat(today_str())
    first = date.fromisoformat(args.first) if args.first else today
    last = date.fromisoformat(args.last) if args.last else first
    rows = backfill_rows(log_file, first, last)
    path = ledger_path()
    if args.dry_run:
        existing = existing_rows(path)
        fresh = new_rows(rows, existing or [])
        for row in fresh:
            sys.stdout.write(json.dumps(row) + "\n")
        per_source = Counter(r["detail"]["source"] for r in fresh)
        sys.stdout.write(
            f"ledger {path} ({'present' if path.exists() else 'missing'}), "
            f"{first}..{last}: {len(rows)} candidate row(s), {len(fresh)} new; "
            f"per source: {dict(sorted(per_source.items()))}\n"
        )
        return 0
    added = append_rows(rows, path)
    sys.stdout.write(f"{added} new row(s) appended to {path}\n")
    return 0
