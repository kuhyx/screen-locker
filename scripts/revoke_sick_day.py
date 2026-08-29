#!/usr/bin/env python3
"""Revoke a sick day that a later-verified workout disproves.

On 2026-06-12 and 2026-08-24 a real workout was completed and the locker could
not see it, so a sick day was spent to get the screen back. Once the workout is
recovered, the penalty has to come off: the date leaves ``sick_days`` and the
debt it incurred is returned.

What this deliberately does NOT do is edit the justification entry. Those are
HMAC-signed over the whole entry (``gatelock.log_integrity.compute_entry_hmac``),
so mutating one to add a ``revoked`` flag would make it fail verification and
read as tampering -- the opposite of the intent. Instead the revocation is
recorded in a sibling ``revocations`` list, keyed by date, naming the workout
that disproved it. The signed history stays verifiable; the correction sits
beside it, which is how an audit trail is supposed to work.

Usage:
    python3 scripts/revoke_sick_day.py --date 2026-08-24
    python3 scripts/revoke_sick_day.py --date 2026-08-24 --date 2026-06-12
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
SICK_HISTORY_FILE = REPO_ROOT / "screen_locker" / "sick_history.json"
LOG_FILE = REPO_ROOT / "screen_locker" / "log.json"

# Failures are logged as well as printed: this script rewrites sick-day
# history, so a read/write error that only reaches stdout can leave the
# revocation half-applied while the surrounding script reports success.
_logger = logging.getLogger(__name__)


def _report(message: str) -> None:
    """Write one line to stdout (matches the other scripts in this directory)."""
    sys.stdout.write(f"{message}\n")


def _workout_id_for(log: dict, date: str) -> str | None:
    """Return the id of a counted workout on ``date``, if one exists."""
    for entry in log.get(date) or []:
        workout_id = entry.get("workout_id")
        if workout_id:
            return str(workout_id)
    return None


def revoke(history: dict, log: dict, date: str) -> str:
    """Apply one revocation to ``history`` in place; return a status line.

    Idempotent: re-running never double-refunds the debt, because the date is
    checked against the existing revocations first.
    """
    revocations = history.setdefault("revocations", [])
    if any(entry.get("date") == date for entry in revocations):
        return f"  {date}: already revoked — nothing to do"

    was_sick_day = date in history.get("sick_days", [])
    workout_id = _workout_id_for(log, date)

    if not was_sick_day and workout_id is None:
        # 2026-06-12 is exactly this case: a justification exists but the date
        # never made it into sick_days, and the log no longer reaches back that
        # far. Record the correction anyway -- the justification is the thing
        # being annotated, and silence would leave it looking uncontested.
        revocations.append(
            {
                "date": date,
                "revoked_at": datetime.now(tz=UTC).isoformat(),
                "reason": (
                    "workout was completed but the locker could not read it; "
                    "no local log entry survives for this date"
                ),
                "workout_id": None,
            }
        )
        return f"  {date}: annotated (no sick_days entry, no surviving log record)"

    if was_sick_day:
        history["sick_days"] = [d for d in history["sick_days"] if d != date]
        # The debt was incurred by taking the sick day; taking it back returns
        # the debt with it. Floor at zero so a double-run cannot go negative.
        history["debt"] = max(0, int(history.get("debt", 0)) - 1)

    revocations.append(
        {
            "date": date,
            "revoked_at": datetime.now(tz=UTC).isoformat(),
            "reason": (
                "workout verified after the fact; the sick day was spent only "
                "because the locker could not read the synced workout"
            ),
            "workout_id": workout_id,
        }
    )
    detail = f"workout_id={workout_id}" if workout_id else "no log record found"
    return f"  {date}: revoked ({detail}), debt now {history['debt']}"


def main() -> int:
    """Revoke every ``--date`` given, preserving the signed justifications."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date", action="append", required=True, help="YYYY-MM-DD (repeatable)"
    )
    parser.add_argument("--history-file", default=str(SICK_HISTORY_FILE))
    parser.add_argument("--log-file", default=str(LOG_FILE))
    args = parser.parse_args()

    history_path = Path(args.history_file)
    try:
        history = json.loads(history_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        _logger.exception("Could not read %s — no sick day was revoked", history_path)
        _report(f"FAIL: could not read {history_path}: {exc}")
        return 1

    log_path = Path(args.log_file)
    try:
        log = json.loads(log_path.read_text()) if log_path.is_file() else {}
    except (OSError, json.JSONDecodeError) as exc:
        _logger.exception(
            "Could not read %s — cannot cite a workout id, so nothing was revoked",
            log_path,
        )
        _report(f"FAIL: could not read {log_path}: {exc}")
        return 1

    before = int(history.get("debt", 0))
    _report(f"Sick days before: {history.get('sick_days')} (debt {before})")
    for date in args.date:
        _report(revoke(history, log, date))

    # Written with json.dump rather than _sick_tracker.save_history because
    # that helper rebuilds the payload from a fixed field list and would drop
    # the revocations key on the next save.
    try:
        history_path.write_text(json.dumps(history, indent=2) + "\n")
    except OSError as exc:
        _logger.exception(
            "Could not write %s — the revocation was NOT persisted",
            history_path,
        )
        _report(f"FAIL: could not write {history_path}: {exc}")
        return 1

    _report(f"Sick days after:  {history.get('sick_days')} (debt {history['debt']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
