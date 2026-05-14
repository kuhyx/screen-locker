"""Sick-day rate-limiting, workout debt, commitment, and justification tracking.

Pure logic — no Tk imports. The UI calls into these helpers and persists
state via :func:`save_history`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
import logging
from typing import Any

from python_pkg.screen_locker._constants import (
    SICK_BUDGET_PER_7_DAYS,
    SICK_BUDGET_PER_30_DAYS,
    SICK_BUDGET_PER_90_DAYS,
    SICK_COMMITMENT_PENALTY_DAYS,
    SICK_HISTORY_FILE,
    SICK_HISTORY_REVIEW_COUNT,
    SICK_JUSTIFICATION_MIN_CHARS,
    SICK_LOCKOUT_MULTIPLIER_PER_RECENT,
    SICK_LOCKOUT_SECONDS,
)
from python_pkg.shared.log_integrity import compute_entry_hmac

_logger = logging.getLogger(__name__)


@dataclass
class SickHistory:
    """Persistent sick-day bookkeeping."""

    sick_days: list[str] = field(default_factory=list)
    debt: int = 0
    commitments: dict[str, bool] = field(default_factory=dict)
    broken_commitments: list[str] = field(default_factory=list)
    justifications: list[dict[str, Any]] = field(default_factory=list)


def _today_iso() -> str:
    """Return today's date as ``YYYY-MM-DD`` (UTC)."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


def _parse_iso(date_str: str) -> datetime | None:
    """Parse ``YYYY-MM-DD`` into a UTC datetime, or return None."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def load_history() -> SickHistory:
    """Read the persistent sick-day history file.

    Missing or unreadable files yield an empty :class:`SickHistory`.
    """
    if not SICK_HISTORY_FILE.exists():
        return SickHistory()
    try:
        with SICK_HISTORY_FILE.open() as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        _logger.warning("Could not read sick history; starting fresh")
        return SickHistory()
    return SickHistory(
        sick_days=list(data.get("sick_days", [])),
        debt=int(data.get("debt", 0)),
        commitments=dict(data.get("commitments", {})),
        broken_commitments=list(data.get("broken_commitments", [])),
        justifications=list(data.get("justifications", [])),
    )


def save_history(history: SickHistory) -> bool:
    """Persist ``history``. Returns True on success."""
    payload = {
        "sick_days": history.sick_days,
        "debt": history.debt,
        "commitments": history.commitments,
        "broken_commitments": history.broken_commitments,
        "justifications": history.justifications,
    }
    try:
        with SICK_HISTORY_FILE.open("w") as f:
            json.dump(payload, f, indent=2)
    except OSError as exc:
        _logger.warning("Failed to save sick history: %s", exc)
        return False
    return True


def count_in_window(
    history: SickHistory,
    days: int,
    *,
    today: str | None = None,
) -> int:
    """Return how many ``sick_days`` fall in the trailing ``days`` window."""
    today_str = today or _today_iso()
    today_dt = _parse_iso(today_str)
    if today_dt is None:
        return 0
    cutoff = today_dt - timedelta(days=days)
    count = 0
    for entry in history.sick_days:
        parsed = _parse_iso(entry)
        if parsed is None:
            continue
        if cutoff < parsed <= today_dt:
            count += 1
    return count


def is_budget_exhausted(
    history: SickHistory,
    *,
    today: str | None = None,
) -> bool:
    """Return True if any rolling window has reached its sick budget."""
    return (
        count_in_window(history, 7, today=today) >= SICK_BUDGET_PER_7_DAYS
        or count_in_window(history, 30, today=today) >= SICK_BUDGET_PER_30_DAYS
        or count_in_window(history, 90, today=today) >= SICK_BUDGET_PER_90_DAYS
    )


def compute_lockout_seconds(
    history: SickHistory,
    *,
    today: str | None = None,
) -> int:
    """Escalating sick countdown: ``base * 2 ** recent_count_in_30d``."""
    recent = count_in_window(history, 30, today=today)
    multiplier = SICK_LOCKOUT_MULTIPLIER_PER_RECENT**recent
    return SICK_LOCKOUT_SECONDS * multiplier


def budget_summary(
    history: SickHistory,
    *,
    today: str | None = None,
) -> str:
    """One-line UI summary string for budget + debt."""
    week = count_in_window(history, 7, today=today)
    month = count_in_window(history, 30, today=today)
    quarter = count_in_window(history, 90, today=today)
    return (
        f"Sick: {week}/{SICK_BUDGET_PER_7_DAYS}w · "
        f"{month}/{SICK_BUDGET_PER_30_DAYS}m · "
        f"{quarter}/{SICK_BUDGET_PER_90_DAYS}q  ·  "
        f"Debt: {history.debt}"
    )


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
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
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
