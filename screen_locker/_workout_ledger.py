"""The workout ledger: signed credit rows, the workout's side of ``earned_time``.

Every other earner publishes its credits as HMAC-signed rows in a ledger that
``earned_time`` reads (``first_credit_at``, ``credit_units``). This is the
workout's: ``~/.local/share/workout_locker/ledger.json``, one row per

* workout credit slot in ``log.json`` -- RunnerUp (a run, or the day's walks
  summed), StrongLifts (phone or PC session), manual, any lock-screen or
  verify path -- appended by the one log write chokepoint
  (``_log_mixin.write_signed_entry``), so no path can credit without it; and
* declared rest day -- appended when it is declared.

Row::

    {"kind": "credit", "entry_id": ..., "day": "YYYY-MM-DD",
     "detail": {"completed_at": "<unix>", "source": "runnerup_tcx" |
                "stronglifts" | "manual" | "rest_day", ["declared_at": ...]},
     "hmac": ...}

``credit_units(WORKOUT)`` therefore equals the log's own credit count: one row
per ``credit_key`` slot, idempotent on ``entry_id`` (the slot's first entry's
``workout_id``), so a re-scan or a second ingestion path writes nothing.
``completed_at`` is the activity's real end where the log knows it
(:func:`entry_done_at`). A rest day's is local midnight at the start of that
day, and its ``declared_at`` (earlier, by construction) proves it was planned.
"""

from __future__ import annotations

from datetime import date, datetime, time
import json
import logging
import os
from pathlib import Path
import tempfile
from typing import TYPE_CHECKING, Any

import earned_time

from screen_locker import _earned
from screen_locker._bonus_lock import bonus_lock
from screen_locker._constants import WORKOUT_LEDGER_RELATIVE
from screen_locker._weekly_check import credit_key, day_workout_index

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

_logger = logging.getLogger(__name__)

# The ledger's ``detail.source`` per log type; anything else keeps its type.
_SOURCES = {
    "runnerup_verified": "runnerup_tcx",
    "phone_verified": "stronglifts",
    "pc_workout_verified": "stronglifts",
    "manual_workout": "manual",
}
_HHMM = len("HH:MM")


def ledger_path() -> Path:
    """Where the workout ledger lives (redirected with ``_earned.LEDGER_HOME``)."""
    return _earned.LEDGER_HOME / WORKOUT_LEDGER_RELATIVE


def _as_stamp(raw: object, day: date) -> float | None:
    """A unix time from a number, a numeric string, ISO, or ``HH:MM`` on ``day``."""
    if isinstance(raw, int | float):
        return float(raw)
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        if text.replace(".", "", 1).isdigit():
            return float(text)
        if len(text) <= _HHMM:
            hours, _, minutes = text.partition(":")
            clock = time(int(hours), int(minutes))
            return datetime.combine(day, clock).astimezone().timestamp()
        return datetime.fromisoformat(text).astimezone().timestamp()
    except ValueError:
        _logger.warning("Unusable workout time %r; ignored", raw)
        return None


def entry_done_at(entry: Mapping[str, Any], day: date) -> float | None:
    """When a logged workout ended; the moment it was logged as a last resort."""
    real = _real_end(entry, day)
    return real if real is not None else _as_stamp(entry.get("timestamp"), day)


def _real_end(entry: Mapping[str, Any], day: date) -> float | None:
    """When a logged workout actually ended, as unix seconds.

    In order: the RunnerUp TCX end (``completed_at``), a manual workout's
    ``end_time``, a StrongLifts session's start (``sync_record_id``) plus its
    ``duration_minutes``; ``None`` when the entry records no end of its own.
    """
    data = entry.get("workout_data")
    data = data if isinstance(data, dict) else {}
    for raw in (data.get("completed_at"), data.get("end_time")):
        stamp = _as_stamp(raw, day)
        if stamp is not None:
            return stamp
    if data.get("type") == "pc_workout_verified":
        start = _as_stamp(data.get("sync_record_id"), day)
        try:
            minutes = float(str(data.get("duration_minutes", "")))
        except ValueError:
            _logger.warning("Session on %s has no usable duration", day)
            minutes = None
        if start is not None and minutes is not None:
            return start + minutes * 60
    return None


def credit_row(
    day: str, entries: Sequence[Mapping[str, Any]], index: int
) -> dict[str, Any] | None:
    """The unsigned row for ``entries[index]``; ``None`` if it earns no credit.

    One row per CREDIT SLOT (``_weekly_check.credit_key``), not per entry: the
    two StrongLifts ingestion paths and a synced copy of an entry share their
    slot, and so share the ``entry_id`` -- the slot's first entry's own
    ``workout_id`` -- and the second never writes a row.
    """
    siblings = day_workout_index(entries)
    slot = credit_key(day, index, entries[index], siblings)
    if slot is None:
        return None
    members = [
        e for i, e in enumerate(entries) if credit_key(day, i, e, siblings) == slot
    ]
    owner = members[0]
    data = owner.get("workout_data")
    wtype = str(data.get("type")) if isinstance(data, dict) else ""
    # The slot's real end, from whichever member recorded one (the PC session
    # of a StrongLifts slot knows its duration, the phone copy does not).
    when = date.fromisoformat(day)
    ends = [t for e in members if (t := _real_end(e, when)) is not None]
    done = min(ends) if ends else entry_done_at(owner, when)
    if done is None:
        _logger.warning("Workout on %s has no usable time; no ledger row", day)
        return None
    entry_id = owner.get("workout_id") or f"{slot[0]}:{slot[1]}"
    return {
        "kind": "credit",
        "entry_id": str(entry_id),
        "day": day,
        "detail": {"completed_at": str(done), "source": _SOURCES.get(wtype, wtype)},
    }


def rest_row(day: date, declared_at: float) -> dict[str, Any]:
    """The unsigned row for a declared rest day, stamped at its own midnight."""
    midnight = datetime.combine(day, time.min).astimezone().timestamp()
    return {
        "kind": "credit",
        "entry_id": f"rest:{day.isoformat()}",
        "day": day.isoformat(),
        "detail": {
            "completed_at": str(midnight),
            "declared_at": str(declared_at),
            "source": "rest_day",
        },
    }


def existing_rows(path: Path) -> list[Any] | None:
    """The ledger's rows; ``[]`` if absent, ``None`` (logged) if malformed."""
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows = raw.get("entries") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        _logger.warning("Workout ledger %s has no entries array", path)
        return None
    return rows


def _atomic_write(path: Path, rows: list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".ledger-", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump({"entries": rows}, handle, indent=2)
    Path(tmp).replace(path)


def new_rows(
    rows: Iterable[dict[str, Any]], existing: list[Any]
) -> list[dict[str, Any]]:
    """The rows whose ``entry_id`` is not among ``existing`` yet."""
    seen = {r.get("entry_id") for r in existing if isinstance(r, dict)}
    fresh: list[dict[str, Any]] = []
    for row in rows:
        if row["entry_id"] not in seen:
            seen.add(row["entry_id"])
            fresh.append(row)
    return fresh


def append_rows(
    rows: Iterable[dict[str, Any]],
    path: Path | None = None,
    key_file: Path | None = None,
) -> int:
    """Sign and append every row not already there. Returns how many were new.

    Never raises: a ledger that cannot be written is logged loudly, and the
    credit it mirrors (log.json) stands regardless.
    """
    target = path or ledger_path()
    # The same key binding ``_earned`` verifies the gates' ledgers with.
    key_path = key_file or _earned.HMAC_KEY_FILE
    try:
        key = key_path.read_bytes().strip()
        target.parent.mkdir(parents=True, exist_ok=True)
        with bonus_lock(target):
            existing = existing_rows(target)
            if existing is None:
                return 0
            fresh = new_rows(rows, existing)
            if not fresh:
                return 0
            for row in fresh:
                row["hmac"] = earned_time.entry_signature(row, key)
            _atomic_write(target, [*existing, *fresh])
    except (OSError, ValueError) as exc:
        _logger.warning("Workout ledger %s NOT updated: %s", target, exc)
        return 0
    _logger.info("Workout ledger: %d new credit row(s) in %s", len(fresh), target)
    return len(fresh)


def record_log_entry(day: str, entries: Sequence[Mapping[str, Any]]) -> None:
    """Mirror the day's newest log entry into the ledger, if it earns a credit."""
    row = credit_row(day, entries, len(entries) - 1)
    if row is not None:
        append_rows([row])
