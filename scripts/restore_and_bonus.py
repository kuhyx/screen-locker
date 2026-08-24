#!/usr/bin/env python3
"""Undo a sick day's shutdown penalty and grant the agreed bonus hours.

Two separate corrections, in this order:

1. **Restore the baseline.** Taking a sick day pulled the shutdown hours down
   to 21/21 and stashed the real values in ``sick_day_state.json`` as
   ``original_mon_wed_hour`` / ``original_thu_sun_hour`` (both 22). Restoring
   comes first, because otherwise a "bonus" merely returns you to baseline and
   the compensation is silently swallowed.

2. **Bank the bonus.** Written into ``extra_benefits_state.json`` under
   ``weekly_shutdown_bonus_hours[<ISO week>]`` -- the same key
   ``_extra_benefits.weekly_shutdown_bonus_hours()`` reads and
   ``_apply_weekly_shutdown_bonus`` applies every day of the week. This is the
   mechanism the locker already uses for streak rewards; nothing bespoke.

Two bonus hours by default: one for each day a completed workout was not
counted (2026-06-12 and 2026-08-24).

Usage:
    python3 scripts/restore_and_bonus.py --date 2026-08-24
    python3 scripts/restore_and_bonus.py --date 2026-08-24 --bonus-hours 3
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
SICK_DAY_STATE_FILE = REPO_ROOT / "screen_locker" / "sick_day_state.json"
EXTRA_BENEFITS_FILE = REPO_ROOT / "screen_locker" / "extra_benefits_state.json"

DEFAULT_BONUS_HOURS = 2


def _report(message: str) -> None:
    """Write one line to stdout (matches the other scripts in this directory)."""
    sys.stdout.write(f"{message}\n")


def _iso_week(date_str: str) -> str:
    """Return ``YYYY-Www`` for ``date_str``, matching ``_current_iso_week``."""
    parsed = datetime.strptime(date_str, "%Y-%m-%d").astimezone()
    year, week, _ = parsed.isocalendar()
    return f"{year}-W{week:02d}"


def _load(path: Path) -> dict:
    """Return ``path``'s JSON object, or an empty dict when absent."""
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        _report(f"WARN: could not read {path}: {exc} — treating as empty")
        return {}


def restore_hours(state: dict) -> tuple[int, int] | None:
    """Return the (mon_wed, thu_sun) hours the sick day displaced, if any."""
    mon_wed = state.get("original_mon_wed_hour")
    thu_sun = state.get("original_thu_sun_hour")
    if mon_wed is None or thu_sun is None:
        return None
    return int(mon_wed), int(thu_sun)


def main() -> int:
    """Restore the pre-sick-day shutdown hours and bank the bonus."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="the revoked sick day")
    parser.add_argument("--bonus-hours", type=int, default=DEFAULT_BONUS_HOURS)
    parser.add_argument("--sick-day-state", default=str(SICK_DAY_STATE_FILE))
    parser.add_argument("--benefits-file", default=str(EXTRA_BENEFITS_FILE))
    args = parser.parse_args()

    sick_state = _load(Path(args.sick_day_state))
    restored = restore_hours(sick_state)
    if restored is None:
        _report(
            "No original shutdown hours recorded — the baseline is already "
            "whatever the daily reset produces, so nothing to restore."
        )
    else:
        mon_wed, thu_sun = restored
        _report(
            f"Baseline to restore: Mon-Wed={mon_wed}:00, Thu-Sun={thu_sun}:00 "
            "(the daily reset re-applies this on the next run)"
        )

    benefits = _load(Path(args.benefits_file))
    week = _iso_week(args.date)
    bonus_map = dict(benefits.get("weekly_shutdown_bonus_hours", {}))
    existing = int(bonus_map.get(week, 0))

    # Idempotence guard. Banking is `existing + bonus`, so without a durable
    # record of which dates were already compensated a re-run silently grants
    # the hours a second time. The bonus map alone cannot answer that question:
    # a week's total mixes earned streak hours with these corrections, so no
    # arithmetic on it can tell "already applied" from "earned that much".
    granted = list(benefits.get("shutdown_bonus_granted_for", []))
    if args.date in granted:
        _report(
            f"Bonus for {args.date} was already banked into {week} "
            f"(currently {existing}h) — not granting it twice."
        )
        return 0

    granted.append(args.date)
    benefits["shutdown_bonus_granted_for"] = granted
    bonus_map[week] = existing + args.bonus_hours
    benefits["weekly_shutdown_bonus_hours"] = bonus_map

    try:
        Path(args.benefits_file).write_text(json.dumps(benefits, indent=2) + "\n")
    except OSError as exc:
        _report(f"FAIL: could not write {args.benefits_file}: {exc}")
        return 1

    _report(
        f"Banked +{args.bonus_hours}h shutdown bonus for {week} "
        f"(was {existing}h, now {bonus_map[week]}h) — applied every day of "
        "that week on top of the restored baseline."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
