"""Sick-day rate-limiting, workout debt, commitment, and justification tracking.

Pure logic — no Tk imports. The UI calls into these helpers and persists
state via :func:`save_history`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
import logging
from typing import Any

from gatelock.log_integrity import compute_entry_hmac

from screen_locker._constants import (
    SICK_COMMITMENT_PENALTY_DAYS,
    SICK_HISTORY_FILE,
    SICK_HISTORY_REVIEW_COUNT,
    SICK_JUSTIFICATION_MIN_CHARS,
)
from screen_locker._sick_budget import (
    SickHistory,
    _parse_iso,
    _today_iso,
    budget_summary,
    compute_lockout_seconds,
    count_in_window,
    is_budget_exhausted,
    is_sick_day,
)

__all__ = [
    "SickHistory",
    "add_sick_day",
    "budget_summary",
    "clear_one_debt",
    "compute_lockout_seconds",
    "count_in_window",
    "had_commitment_for_today",
    "is_budget_exhausted",
    "is_sick_day",
    "load_history",
    "mark_commitment_broken",
    "record_commitment_for_tomorrow",
    "save_history",
]

_logger = logging.getLogger(__name__)


def load_history() -> SickHistory:
    """Read the persistent sick-day history file.

    Missing or unreadable files yield an empty :class:`SickHistory`.
    """
    if not SICK_HISTORY_FILE.exists():
        return SickHistory()
    try:
        with SICK_HISTORY_FILE.open() as f:
            data = json.load(f)
    except OSError, json.JSONDecodeError:
        _logger.warning("Could not read sick history; starting fresh")
        return SickHistory()
    return SickHistory(
        sick_days=list(data.get("sick_days", [])),
        debt=int(data.get("debt", 0)),
        commitments=dict(data.get("commitments", {})),
        broken_commitments=list(data.get("broken_commitments", [])),
        justifications=list(data.get("justifications", [])),
        revocations=list(data.get("revocations", [])),
    )


def save_history(history: SickHistory) -> bool:
    """Persist ``history``. Returns True on success."""
    payload = {
        "sick_days": history.sick_days,
        "debt": history.debt,
        "commitments": history.commitments,
        "broken_commitments": history.broken_commitments,
        "justifications": history.justifications,
        "revocations": history.revocations,
    }
    try:
        with SICK_HISTORY_FILE.open("w") as f:
            json.dump(payload, f, indent=2)
    except OSError as exc:
        _logger.warning("Failed to save sick history: %s", exc)
        return False
    return True


def add_sick_day(history: SickHistory, *, today: str | None = None) -> int:
    """Append today's date and increment debt. Returns new debt.

    If today appears in ``broken_commitments`` the debt grows by
    :data:`SICK_COMMITMENT_PENALTY_DAYS` instead of 1.
    """
    today_str = today or _today_iso()
    if today_str not in history.sick_days:
        history.sick_days.append(today_str)
    increment = (
        SICK_COMMITMENT_PENALTY_DAYS if today_str in history.broken_commitments else 1
    )
    history.debt += increment
    return history.debt


def clear_one_debt(history: SickHistory) -> int:
    """Decrement debt by one (clamped at zero). Returns new debt."""
    if history.debt > 0:
        history.debt -= 1
    return history.debt


def record_commitment_for_tomorrow(
    history: SickHistory,
    *,
    today: str | None = None,
) -> str:
    """Record that the user committed to working out tomorrow.

    Returns the ISO date for tomorrow.
    """
    today_str = today or _today_iso()
    today_dt = _parse_iso(today_str)
    if today_dt is None:
        return today_str
    tomorrow = (today_dt + timedelta(days=1)).strftime("%Y-%m-%d")
    history.commitments[tomorrow] = True
    return tomorrow


def had_commitment_for_today(
    history: SickHistory,
    *,
    today: str | None = None,
) -> bool:
    """Return True if a commitment exists for today."""
    today_str = today or _today_iso()
    return bool(history.commitments.get(today_str, False))


def mark_commitment_broken(
    history: SickHistory,
    *,
    today: str | None = None,
) -> None:
    """Mark today's commitment as broken (idempotent)."""
    today_str = today or _today_iso()
    if today_str in history.commitments and today_str not in history.broken_commitments:
        history.broken_commitments.append(today_str)


SICK_SEVERITY_MIN = 1
SICK_SEVERITY_MAX = 10


@dataclass
class JustificationDraft:
    """User-supplied justification fields for a sick-day request."""

    symptom: str
    onset: str
    severity: int
    text: str


def validate_justification(draft: JustificationDraft) -> str | None:
    """Return an error message if the justification is invalid, else None."""
    if not draft.symptom.strip():
        return "Symptom is required"
    if not draft.onset.strip():
        return "Onset time is required"
    if not SICK_SEVERITY_MIN <= draft.severity <= SICK_SEVERITY_MAX:
        return f"Severity must be between {SICK_SEVERITY_MIN} and {SICK_SEVERITY_MAX}"
    if len(draft.text.strip()) < SICK_JUSTIFICATION_MIN_CHARS:
        return (
            f"Description must be at least "
            f"{SICK_JUSTIFICATION_MIN_CHARS} characters "
            f"(currently {len(draft.text.strip())})"
        )
    return None


def add_justification(
    history: SickHistory,
    draft: JustificationDraft,
    *,
    today: str | None = None,
) -> dict[str, Any]:
    """HMAC-sign and append a sick-day justification.

    Returns the stored entry (with ``hmac`` field if a key was available).
    """
    today_str = today or _today_iso()
    entry: dict[str, Any] = {
        "date": today_str,
        "timestamp": datetime.now(tz=UTC).isoformat(),
        "symptom": draft.symptom.strip(),
        "onset": draft.onset.strip(),
        "severity": int(draft.severity),
        "text": draft.text.strip(),
    }
    signature = compute_entry_hmac(entry)
    if signature is not None:
        entry["hmac"] = signature
    history.justifications.append(entry)
    return entry


def recent_justifications(
    history: SickHistory,
    n: int = SICK_HISTORY_REVIEW_COUNT,
) -> list[dict[str, Any]]:
    """Return the last ``n`` justifications (oldest first)."""
    if n <= 0:
        return []
    return list(history.justifications[-n:])


def format_recent_justifications(
    history: SickHistory,
    n: int = SICK_HISTORY_REVIEW_COUNT,
) -> str:
    """Human-readable multi-line summary of recent justifications.

    Empty string when there are no past entries.
    """
    entries = recent_justifications(history, n)
    if not entries:
        return ""
    lines: list[str] = []
    for entry in entries:
        date_str = entry.get("date", "?")
        symptom = entry.get("symptom", "?")
        severity = entry.get("severity", "?")
        lines.append(f"{date_str}  sev {severity}/10  —  {symptom}")
    return "\n".join(lines)
