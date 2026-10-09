"""Rest days: declared AHEAD of time, at most two per ISO week, HMAC-signed.

A declared rest day earns the workout's first-unit shutdown bonus, so the day
resolves as if its workout were done. Two rules keep it from being an escape:

* **Ahead only.** A rest day must be declared on an earlier local day than
  the one it names -- never "today", so it cannot be reached for at the
  moment the shutdown bites. Checked when declaring AND again when reading
  (``declared_on < day``), so a row written by any other route still fails.
  The CLI refuses to run on a skewed clock (``check_clock_skew``), the one
  way to make tomorrow look like today.
* **Two per ISO week**, counted by the rest day's own week over the verified
  rows, oldest declaration first; a third row in a week is ignored on read.

Each declaration is mirrored as a ``rest_day`` credit row in the workout
ledger (:mod:`screen_locker._workout_ledger`), which ``earned_time`` reads.

Rows live in ``rest_days.json`` as ``{"entries": [...]}``, each signed with
``earned_time.entry_signature`` and the shared key, the same as every gate's
ledger: editing the file without the key breaks the row, and a broken row
earns nothing.

Unlike a sick day -- decided on the day, at the lock screen, behind a
countdown, rate-limited over 7/30/90 days, and paid back as workout debt -- a
rest day is planned, costs no debt, and only touches shutdown time. It does
not stand down the screen lock or the weekly minimum (``freedays`` does that).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
import json
import logging
from typing import TYPE_CHECKING, Any

import earned_time

from screen_locker import _earned
from screen_locker._constants import REST_DAY_FILE, REST_DAYS_PER_ISO_WEEK
from screen_locker._workout_ledger import append_rows, rest_row

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)

_KIND = "rest_day"


@dataclass(frozen=True)
class Declared:
    """Outcome of :func:`declare`: ``ok`` and a sentence a human can act on."""

    ok: bool
    reason: str


def _key(key_file: Path) -> bytes | None:
    try:
        key = key_file.read_bytes().strip()
    except OSError as exc:
        _logger.warning("Cannot read the rest-day signing key %s (%s)", key_file, exc)
        return None
    return key or None


def _rows(path: Path) -> list[Any] | None:
    """The file's ``entries``; ``[]`` if it does not exist, ``None`` if unreadable."""
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _logger.warning("Rest-day file %s is unreadable (%s)", path, exc)
        return None
    rows = raw.get("entries") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        _logger.warning("Rest-day file %s has no entries array", path)
        return None
    return rows


def _iso_week(day: date) -> tuple[int, int]:
    year, week, _ = day.isocalendar()
    return year, week


def _valid(row: object, key: bytes) -> bool:
    """A signed rest-day row, declared on an earlier day than it names."""
    if not isinstance(row, dict) or row.get("kind") != _KIND:
        return False
    if not earned_time.verified(row, key):
        _logger.warning("Rest-day row %r fails its signature; ignored", row.get("day"))
        return False
    try:
        return date.fromisoformat(str(row["declared_on"])) < date.fromisoformat(
            str(row["day"])
        )
    except (KeyError, ValueError) as exc:
        _logger.warning("Rest-day row %r is malformed (%s); ignored", row, exc)
        return False


def rest_day_declarations(
    path: Path | None = None, key_file: Path | None = None
) -> dict[date, float]:
    """Every rest day that counts, with the unix time it was declared.

    Counted: verified, declared ahead, within the weekly cap (oldest first).
    """
    key = _key(key_file or _earned.HMAC_KEY_FILE)
    rows = _rows(path or REST_DAY_FILE)
    if key is None or rows is None:
        return {}
    good = sorted(
        (r for r in rows if _valid(r, key)), key=lambda r: float(r["declared_at"])
    )
    counted: dict[date, float] = {}
    for row in good:
        day = date.fromisoformat(str(row["day"]))
        same_week = sum(1 for d in counted if _iso_week(d) == _iso_week(day))
        if day not in counted and same_week < REST_DAYS_PER_ISO_WEEK:
            counted[day] = float(row["declared_at"])
    return counted


def rest_days(path: Path | None = None, key_file: Path | None = None) -> set[date]:
    """Every rest day that counts (see :func:`rest_day_declarations`)."""
    return set(rest_day_declarations(path, key_file))


def is_rest_day(
    day: date, path: Path | None = None, key_file: Path | None = None
) -> bool:
    """Whether ``day`` is a declared rest day (``False`` when unverifiable)."""
    return day in rest_days(path, key_file)


def declare(
    day: date,
    *,
    now: datetime | None = None,
    path: Path | None = None,
    key_file: Path | None = None,
    ledger: Path | None = None,
) -> Declared:
    """Sign and append a rest day for ``day``, if the rules allow it.

    Paths default at call time to ``REST_DAY_FILE`` and the key ``_earned``
    verifies every ledger with, so the test suite's redirects apply.
    """
    path = path or REST_DAY_FILE
    key_file = key_file or _earned.HMAC_KEY_FILE
    moment = (now or datetime.now(tz=UTC)).astimezone()
    if day <= moment.date():
        return Declared(
            ok=False,
            reason=f"{day} is not in the future: rest days are declared ahead",
        )
    existing = rest_days(path, key_file)
    if day in existing:
        return Declared(ok=True, reason=f"{day} is already a rest day")
    used = sum(1 for d in existing if _iso_week(d) == _iso_week(day))
    if used >= REST_DAYS_PER_ISO_WEEK:
        return Declared(
            ok=False,
            reason=f"ISO week {_iso_week(day)[1]} already has "
            f"{REST_DAYS_PER_ISO_WEEK} rest days",
        )
    key = _key(key_file)
    rows = _rows(path)
    if key is None or rows is None:
        return Declared(ok=False, reason="rest-day file or signing key unreadable")
    row: dict[str, object] = {
        "kind": _KIND,
        "day": day.isoformat(),
        "declared_on": moment.date().isoformat(),
        "declared_at": moment.timestamp(),
    }
    row["hmac"] = earned_time.entry_signature(row, key)
    rows.append(row)
    try:
        path.write_text(json.dumps({"entries": rows}, indent=2), encoding="utf-8")
    except OSError as exc:
        _logger.warning("Could not write rest day to %s (%s)", path, exc)
        return Declared(ok=False, reason=f"could not write {path}: {exc}")
    append_rows([rest_row(day, moment.timestamp())], ledger, key_file)
    left = REST_DAYS_PER_ISO_WEEK - used - 1
    return Declared(
        ok=True,
        reason=f"{day} is a rest day ({left} left in ISO week {_iso_week(day)[1]})",
    )
