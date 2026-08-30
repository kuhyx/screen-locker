"""The decision-history payload, with timestamps rendered server-side.

Split out of ``_web_payload.py`` to keep every file under the 250-line cap.

The local-time rendering lives here rather than in the browser because
LibreWolf's ``privacy.resistFingerprinting`` pins JavaScript's ``Date`` to
UTC: on 2026-08-30 a 14:00 CEST decision rendered as "12:00 PM" beside a
correct, server-computed "6m ago", and the two-hour disagreement made a live
page look stale.
"""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from screen_locker._decision_log import read_decisions

_logger = logging.getLogger(__name__)

# How many decisions the Why view gets by default. The trail holds 3000;
# the browser only ever needs the recent tail to answer "why did nothing
# happen".
DEFAULT_DECISION_LIMIT = 200


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
        "decisions": [_with_local_stamps(entry) for entry in reversed(tail)],
    }


def _local_stamp(value: object) -> str | None:
    """Render one ISO timestamp in this machine's local time.

    Formatted server-side on purpose. The browser used to do it with
    ``toLocaleString``, which LibreWolf's ``privacy.resistFingerprinting``
    pins to UTC -- so on 2026-08-30 a 14:00 CEST decision rendered as
    "12:00 PM", two hours stale-looking, right next to a correct
    server-computed "6m ago".

    Args:
        value: The stored ISO-8601 timestamp, if it is one.

    Returns:
        A local-time string, or None when there is nothing to render.
    """
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        _logger.warning(
            "Decision timestamp %r is unparsable — leaving it unformatted "
            "rather than showing a wrong local time",
            value,
        )
        return None
    return moment.astimezone().strftime("%b %d, %H:%M")


def _with_local_stamps(entry: dict[str, object]) -> dict[str, object]:
    """Return *entry* with server-rendered local-time fields added.

    Args:
        entry: One decision record from the trail.

    Returns:
        The record plus ``local_time`` (and ``local_last_time`` for a
        collapsed row).
    """
    enriched = dict(entry)
    local = _local_stamp(entry.get("timestamp"))
    if local is not None:
        enriched["local_time"] = local
    last_local = _local_stamp(entry.get("last_timestamp"))
    if last_local is not None:
        enriched["local_last_time"] = last_local
    return enriched
