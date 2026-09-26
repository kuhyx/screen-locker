"""One extra shutdown hour on a day with an accepted LeetCode submission.

leetcode-guard never writes the shutdown config itself; it only publishes the
fact through its ledger, the same way ``steam-backlog-enforcer`` reads it for
an hour of gaming budget. The write has to live here because
:func:`~screen_locker._shutdown_base.reset_to_base_if_new_day` recomputes the
config from scratch on every new day -- a bonus written by another program
would be wiped by that reset, exactly as a pre-tick workout credit was on
2026-09-13. So the hour is a *term* of the derived target, not an increment
that survives by luck.

Three things are pinned deliberately, mirroring leetcode-guard's own
``solved_today`` contract:

**Only ``credit`` entries count.** A ``seen`` entry is first-run seeding worth
zero, and a ``charge`` proves only that the day was *settled* -- which also
happens from banked credit, from the escape hatch and from a classified
outage, so it can never stand in for a solve.

**The solve time is ``detail["submitted_at"]``, not ``day``.** ``day`` is the
*harvesting* run's date, and a problem solved at 23:50 and harvested the next
morning carries the next day's key. It earns for the day it was solved on,
which by then is over -- never for the next one.

**"Cannot check" is not "not solved".** An unreadable ledger or key yields
``None``, and the caller fails closed to no hour. Failing open would let the
coupling be defeated by deleting a file.
"""

from __future__ import annotations

from datetime import UTC, datetime, time
import json
import logging
from pathlib import Path
from typing import Final

from gatelock.log_integrity import verify_entry_hmac

from screen_locker._constants import HMAC_KEY_FILE

_logger: Final = logging.getLogger(__name__)

# Flat, once per day, regardless of how many problems were solved -- the
# workout is the harder thing and keeps the bigger, per-session reward.
LEETCODE_BONUS_HOURS: Final = 1

# leetcode-guard's real ledger (its DATA_DIR / "ledger.json"). Read-only from
# here; resolved at call time so the test suite's path redirect applies.
LEETCODE_LEDGER_FILE: Final = Path.home() / ".local/share/leetcode_guard/ledger.json"

_CREDIT: Final = "credit"


def _today_window(now: datetime | None = None) -> tuple[float, float]:
    """Local midnight and now, as unix seconds.

    Args:
        now: Stand-in for the current local time, for tests.

    Returns:
        The inclusive window a solve must fall in to count for today.
    """
    moment = (now or datetime.now(tz=UTC)).astimezone()
    midnight = datetime.combine(moment.date(), time.min, moment.tzinfo)
    return midnight.timestamp(), moment.timestamp()


def _landed_today(entry: dict[str, object], *, window: tuple[float, float]) -> bool:
    """Whether this verified credit's accepted submission happened today.

    Args:
        entry: One ledger entry, already known to be a verified credit.
        window: Local midnight and now, as unix seconds.

    Returns:
        Whether the solve falls inside today. Without a usable
        ``submitted_at`` the harvest ``day`` is the fallback: it runs late,
        never early, so it can miss a late solve but never invent one.
    """
    detail = entry.get("detail")
    raw = detail.get("submitted_at") if isinstance(detail, dict) else None
    if raw is not None:
        try:
            stamp = float(str(raw))
        except ValueError:
            _logger.warning(
                "LeetCode credit %r has an unparsable submitted_at (%r); "
                "falling back to its day key",
                entry.get("entry_id"),
                raw,
            )
        else:
            start, end = window
            return start <= stamp <= end
    start, _ = window
    today = datetime.fromtimestamp(start).astimezone().date().isoformat()
    return entry.get("day") == today


def _read_entries(ledger_path: Path, label: str = "LeetCode") -> list[object] | None:
    """Read the ledger's entry list, or ``None`` when it cannot be read.

    Args:
        ledger_path: leetcode-guard's (or book-guard's) ledger file.
        label: Whose ledger, for the log line.

    Returns:
        The raw entries, or ``None`` -- which is never "no entries".
    """
    try:
        raw = json.loads(ledger_path.read_text(encoding="utf-8"))
    except OSError as exc:
        _logger.warning("Cannot read the %s ledger at %s (%s)", label, ledger_path, exc)
        return None
    except ValueError as exc:
        _logger.warning(
            "%s ledger at %s is not valid JSON (%s)", label, ledger_path, exc
        )
        return None
    rows = raw.get("entries") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        _logger.warning("%s ledger at %s has no entries array", label, ledger_path)
        return None
    return rows


def leetcode_solved_today(
    ledger_path: Path | None = None,
    *,
    now: datetime | None = None,
) -> bool | None:
    """Whether a verified accepted submission landed today, locally.

    Args:
        ledger_path: The ledger to read. None resolves
            :data:`LEETCODE_LEDGER_FILE` at call time.
        now: Stand-in for the current local time, for tests.

    Returns:
        True or False when the ledger could be read and verified, ``None``
        when it could not -- which is never "nothing was solved".
    """
    target = LEETCODE_LEDGER_FILE if ledger_path is None else ledger_path
    try:
        key_usable = bool(HMAC_KEY_FILE.read_bytes().strip())
    except OSError as exc:
        _logger.warning("Cannot read the integrity key at %s (%s)", HMAC_KEY_FILE, exc)
        return None
    if not key_usable:
        _logger.warning("Integrity key at %s is empty", HMAC_KEY_FILE)
        return None

    rows = _read_entries(target)
    if rows is None:
        return None

    window = _today_window(now)
    return any(
        isinstance(row, dict)
        and row.get("kind") == _CREDIT
        and verify_entry_hmac(row, key_file=HMAC_KEY_FILE)
        and _landed_today(row, window=window)
        for row in rows
    )


def leetcode_bonus_hours(ledger_path: Path | None = None) -> int:
    """The shutdown hours today's LeetCode solve has earned, failing closed.

    Args:
        ledger_path: The ledger to read. None resolves the real one.

    Returns:
        :data:`LEETCODE_BONUS_HOURS` on a day with a verified solve, else 0.
        A ledger that cannot be checked is 0 too, and logged -- it must never
        be mistaken for a confident "not solved", but it earns nothing either.
    """
    solved = leetcode_solved_today(ledger_path)
    if solved is None:
        _logger.warning("LeetCode solve state could not be checked; no shutdown hour")
        return 0
    return LEETCODE_BONUS_HOURS if solved else 0
