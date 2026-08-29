"""JSON payloads for the local status web UI.

One read-only view, shared by the HTTP server and anything else that wants the
same answer. Deliberately built on :func:`~screen_locker._status_data.gather_status`
rather than on a second walk of the log: ``_mcp`` already proves that snapshot
round-trips through ``json.dumps`` unchanged, and a second projection is exactly
how the status view came to explain a decision the locker never made.

Nothing here reads a secret. The sync token and the HMAC key never appear in a
payload, and no endpoint takes input that reaches the filesystem.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
import logging
from pathlib import Path
from typing import Any

from screen_locker._armed_state import collect_states, systemctl_available
from screen_locker._decision_log import DECISION_LOG_FILE, read_decisions
from screen_locker._log_io import load_workout_log
from screen_locker._status_data import gather_status
from screen_locker._status_projection import (
    compliance_state_word,
    format_summary_line,
)
from screen_locker._weekly_check import count_day_credits

_logger = logging.getLogger(__name__)

# The workout log lives beside the package, same default as
# ``_status_data._DEFAULT_LOG_FILE``; declared here to avoid importing a
# private name across modules, exactly as ``_mcp`` does.
LOG_FILE = Path(__file__).resolve().parent / "log.json"

# The marker that disables enforcement machine-wide. Kept in sync with
# scripts/disarm_guard.sh, which is the thing that writes it.
DISARM_MARKER = Path.home() / ".local" / "share" / "screen_locker" / "DISARMED"

# How many decisions the Why view gets by default. The trail holds 3000; the
# browser only ever needs the recent tail to answer "why did nothing happen".
DEFAULT_DECISION_LIMIT = 200


def workout_credits_today(*, now: datetime | None = None) -> int:
    """Return how many workout credits today has earned so far.

    Uses :func:`~screen_locker._weekly_check.count_day_credits`, the same rule
    the locker enforces with, so "did I work out today" cannot drift from "does
    the locker think I worked out today".

    Args:
        now: Override for the current local datetime (for testing).

    Returns:
        The number of distinct credits earned today, zero if none.
    """
    moment = now if now is not None else datetime.now(tz=UTC).astimezone()
    today = moment.date().isoformat()
    entries = load_workout_log(LOG_FILE).get(today, [])
    return count_day_credits(today, [e for e in entries if isinstance(e, dict)])


def build_status_payload(*, now: datetime | None = None) -> dict[str, Any]:
    """Build the full status payload.

    Args:
        now: Override for the current local datetime (for testing).

    Returns:
        The status snapshot plus the derived one-liners and the gaming-budget
        input the enforcer reads.
    """
    snapshot = gather_status()
    credits_today = workout_credits_today(now=now)
    return {
        "snapshot": asdict(snapshot),
        "summary_line": format_summary_line(snapshot),
        "compliance_state": compliance_state_word(snapshot),
        # The gaming budget is decided by steam-backlog-enforcer, which owns the
        # hour values. This reports only the fact the decision turns on, so the
        # two repos cannot disagree about what a "workout day" is.
        "gaming": {
            "workout_today": credits_today > 0,
            "credits_today": credits_today,
            "reason": (
                f"{credits_today} counted workout(s) logged today"
                if credits_today
                else "no counted workout logged today"
            ),
        },
    }


def build_decisions_payload(
    *,
    limit: int = DEFAULT_DECISION_LIMIT,
) -> dict[str, Any]:
    """Build the decision-history payload, newest first.

    Args:
        limit: Maximum number of decisions to return.

    Returns:
        The recent decisions and the total the trail holds.
    """
    decisions = read_decisions()
    tail = decisions[-limit:] if limit > 0 else decisions
    return {
        "total": len(decisions),
        "returned": len(tail),
        "decisions": list(reversed(tail)),
    }


def _log_age_seconds(*, now: datetime | None = None) -> float | None:
    """Return how long ago the workout log was last written.

    Args:
        now: Override for the current local datetime (for testing).

    Returns:
        Age in seconds, or ``None`` when the log does not exist.
    """
    try:
        mtime = LOG_FILE.stat().st_mtime
    except OSError:
        _logger.warning(
            "Cannot stat the workout log at %s — reporting its age as unknown "
            "rather than as fresh",
            LOG_FILE,
        )
        return None
    moment = now if now is not None else datetime.now(tz=UTC).astimezone()
    return moment.timestamp() - mtime


def _last_decision_age_seconds(*, now: datetime | None = None) -> float | None:
    """Return how long ago a decision was last recorded.

    A locker that stopped running goes quiet rather than failing, so the age of
    the newest decision is the most direct evidence that it is still alive.

    Args:
        now: Override for the current local datetime (for testing).

    Returns:
        Age in seconds, or ``None`` when nothing has been recorded.
    """
    decisions = read_decisions()
    if not decisions:
        return None
    stamp = decisions[-1].get("timestamp")
    if not isinstance(stamp, str):
        return None
    try:
        recorded = datetime.fromisoformat(stamp)
    except ValueError:
        _logger.warning(
            "Newest decision has an unparsable timestamp %r — reporting its "
            "age as unknown rather than as recent",
            stamp,
        )
        return None
    moment = now if now is not None else datetime.now(tz=UTC).astimezone()
    return moment.timestamp() - recorded.timestamp()


def build_health_payload(*, now: datetime | None = None) -> dict[str, Any]:
    """Build the health payload: is the locker actually able to fire.

    Every field here exists because its absence once went unnoticed. A timer
    silently deleted to break an ordering cycle, a disarm marker left in place,
    a log that stopped being written -- none of those raise an error anywhere,
    so each is reported as a value rather than left to be inferred from silence.

    Args:
        now: Override for the current local datetime (for testing).

    Returns:
        Timer arming state, the disarm marker, and freshness of log and trail.
    """
    checked = systemctl_available()
    timers = [
        {
            "name": state.name,
            "enabled": state.enabled,
            "scheduled": state.scheduled,
            "armed": state.armed,
            "describe": state.describe(),
        }
        for state in (collect_states() if checked else ())
    ]
    disarmed = DISARM_MARKER.exists()
    return {
        # "could not check" is reported as its own state: it must never be
        # rendered as a green tick.
        "timers_checked": checked,
        "timers": timers,
        "armed": checked and not disarmed and all(t["armed"] for t in timers),
        "disarmed": disarmed,
        "disarm_marker": str(DISARM_MARKER),
        "log_file": str(LOG_FILE),
        "log_age_seconds": _log_age_seconds(now=now),
        "decision_log_file": str(DECISION_LOG_FILE),
        "last_decision_age_seconds": _last_decision_age_seconds(now=now),
    }
