"""One extra shutdown hour on a day with a credited paper-book reading session.

book-guard (``~/src/book-guard``) publishes reading through its ledger, the
same way leetcode-guard publishes solves, and steam-backlog-enforcer reads the
same fact for an hour of gaming. Like the LeetCode hour it is a *term* of the
daily derivation in :mod:`screen_locker._shutdown_base`, never an increment
another program writes into the config.

The contract, pinned in book-guard's ``_quiz.record_verdict``:

**Only ``credit`` rows count**, and only those with ``detail["bonus"] ==
"1"`` -- book-guard sets that when the session passed its quiz *and* was big
enough (20+ pages, 20+ minutes). A ``reject`` is a failed quiz; an
``escape`` forgives a lock and earns nothing.

**The reading time is ``detail["ended_at"]``**, not the row's creation: a
session read at 22:30 and quizzed next morning earns for the evening it was
read, which by then is over -- never for the quiz day.

**"Cannot check" is not "did not read"**: an unreadable ledger or key yields
``None`` and the caller fails closed to no hour.
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
from pathlib import Path
from typing import Final

from gatelock.log_integrity import verify_entry_hmac

from screen_locker._constants import HMAC_KEY_FILE
from screen_locker._leetcode_bonus import _read_entries, _today_window

_logger: Final = logging.getLogger(__name__)

READING_BONUS_HOURS: Final = 1

# book-guard's real ledger. Read-only from here; resolved at call time so the
# test suite's path redirect (tests/_isolated_state.py) applies.
READING_LEDGER_FILE: Final = Path.home() / ".local/share/book_guard/ledger.json"


def _read_today(entry: dict[str, object], *, window: tuple[float, float]) -> bool:
    """Whether this verified credit is bonus-eligible and was read today."""
    detail = entry.get("detail")
    if not isinstance(detail, dict) or detail.get("bonus") != "1":
        return False
    try:
        ended = float(str(detail.get("ended_at")))
    except ValueError:
        _logger.warning(
            "reading credit %r has no usable ended_at", entry.get("entry_id")
        )
        return False
    start, end = window
    return start <= ended <= end


def read_today(
    ledger_path: Path | None = None,
    *,
    now: datetime | None = None,
) -> bool | None:
    """Whether a verified, bonus-eligible reading session ended today, locally.

    Returns:
        True or False when the ledger could be read and verified, ``None``
        when it could not -- which is never "did not read".
    """
    target = READING_LEDGER_FILE if ledger_path is None else ledger_path
    try:
        key_usable = bool(HMAC_KEY_FILE.read_bytes().strip())
    except OSError as exc:
        _logger.warning("Cannot read the integrity key at %s (%s)", HMAC_KEY_FILE, exc)
        return None
    if not key_usable:
        _logger.warning("Integrity key at %s is empty", HMAC_KEY_FILE)
        return None
    if not target.exists():
        return False  # book-guard never registered a book: no reading, no fault
    rows = _read_entries(target, "book-guard")
    if rows is None:
        return None
    window = _today_window(now or datetime.now(tz=UTC))
    return any(
        isinstance(row, dict)
        and row.get("kind") == "credit"
        and verify_entry_hmac(row, key_file=HMAC_KEY_FILE)
        and _read_today(row, window=window)
        for row in rows
    )


def reading_bonus_hours(ledger_path: Path | None = None) -> int:
    """The shutdown hours today's reading has earned, failing closed.

    A ledger that does not exist yet (book-guard never ran) is a plain 0,
    logged by :func:`_read_entries` like any unreadable one.
    """
    done = read_today(ledger_path)
    if done is None:
        _logger.warning("Reading state could not be checked; no shutdown hour")
        return 0
    return READING_BONUS_HOURS if done else 0
