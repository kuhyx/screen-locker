"""Writing the durable decision trail, including repeat-collapsing.

Split out of ``_decision_log.py`` to keep every file under the 250-line cap.
``_decision_log`` owns *what* a decision is and how it reads in the journal;
this module owns how it lands on disk.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Final

_logger = logging.getLogger(__name__)

# Outside the repo on purpose -- workout state is private and git-untracked.
DECISION_LOG_FILE: Path = (
    Path.home() / ".local" / "share" / "screen_locker" / "decisions.jsonl"
)

# Trimmed on write so the recurring timers cannot grow this without bound.
# Writers are the 5-minute locker timer plus the 15-minute sync run (which
# records "made no decision"). Consecutive identical records collapse into
# one row, so a restart loop can no longer evict a month of history.
DECISION_LOG_MAX_ENTRIES: Final[int] = 3000


# Fields that differ between two recordings of the *same* event, and so must
# not stop them collapsing into one row.
_COLLAPSE_VOLATILE_KEYS = frozenset({"timestamp", "repeat_count", "last_timestamp"})


def _is_repeat(previous_line: str, record: dict[str, object]) -> bool:
    """Return whether ``record`` restates the event on ``previous_line``.

    Everything but the timestamps and the repeat counter must match, so a
    change in ``weekly_count`` or ``detail`` still opens a new row -- only a
    genuinely identical event collapses.

    Args:
        previous_line: The newest line already in the trail.
        record: The record about to be written.

    Returns:
        True when the two describe the same event.
    """
    try:
        previous = json.loads(previous_line)
    except json.JSONDecodeError as exc:
        # An unparsable tail is history we cannot compare against, so we keep
        # it and start a new row rather than overwrite it. Said out loud: a
        # corrupt trail is exactly the thing that must not stay quiet.
        _logger.warning(
            "Newest line of the decision trail is unparsable (%s) — starting "
            "a new row instead of collapsing into it, so nothing is lost",
            exc,
        )
        return False
    if not isinstance(previous, dict):
        return False
    return {
        key: value
        for key, value in previous.items()
        if key not in _COLLAPSE_VOLATILE_KEYS
    } == {
        key: value
        for key, value in record.items()
        if key not in _COLLAPSE_VOLATILE_KEYS
    }


def _trimmed(lines: list[str], record: dict[str, object]) -> list[str]:
    """Return the retained history with ``record`` folded in.

    Consecutive identical events collapse into one row carrying
    ``repeat_count`` and ``last_timestamp`` instead of appending a new line.
    On 2026-08-30 a restart loop (no X server at 02:00, ``Restart=on-failure``
    every ~6s) wrote ~1693 identical ``enforced`` records in three hours and
    evicted the entire history behind them: the tool built to make blind spots
    impossible erased its own. Collapsing bounds any such storm to a single
    row, and does the same for the every-15-minutes ``--sync-only`` runs.

    Args:
        lines: The existing trail, oldest first.
        record: The record to fold in.

    Returns:
        The new trail, oldest first.
    """
    if lines and _is_repeat(lines[-1], record):
        previous = json.loads(lines[-1])
        merged = {
            **record,
            # The FIRST sighting stays in `timestamp` so the row still says
            # when the streak began; readers wanting freshness use
            # `last_timestamp` (see _web_payload.decision_age_seconds).
            "timestamp": previous.get("timestamp", record["timestamp"]),
            "repeat_count": int(previous.get("repeat_count", 1)) + 1,
            "last_timestamp": record["timestamp"],
        }
        return [*lines[:-1], json.dumps(merged)]
    if len(lines) >= DECISION_LOG_MAX_ENTRIES:
        lines = lines[-(DECISION_LOG_MAX_ENTRIES - 1) :]
    return [*lines, json.dumps(record)]


def append_record(record: dict[str, object], *, log_file: Path | None = None) -> None:
    """Append one record to the durable trail, trimming old history.

    Never raises: failing to *record* why the locker acted must not stop the
    locker from acting. A write failure is reported at ``warning`` rather than
    swallowed, so the gap in the trail is itself visible.
    """
    target = DECISION_LOG_FILE if log_file is None else log_file
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        existing = (
            target.read_text(encoding="utf-8").splitlines() if target.exists() else []
        )
        kept = _trimmed([entry for entry in existing if entry.strip()], record)
        target.write_text("\n".join(kept) + "\n", encoding="utf-8")
    except OSError as exc:
        _logger.warning(
            "Could not append to the decision log at %s (%s) — this run's "
            "decision is in the journal only, so the durable trail now has a "
            "gap",
            target,
            exc,
        )
