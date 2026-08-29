"""Tests for _web_payload: the JSON the UI and the enforcer both read.

The load-bearing assertion here is that ``gaming.workout_today`` comes from the
same credit rule the locker enforces with. steam-backlog-enforcer cuts the
gaming budget on that field, so if it ever drifted from
``count_day_credits`` the two repos would disagree about what a workout day is.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

from screen_locker._web_payload import (
    build_decisions_payload,
    build_status_payload,
    workout_credits_today,
)

if TYPE_CHECKING:
    from pathlib import Path

_PKG = "screen_locker._web_payload"

_SATURDAY = datetime(2026, 8, 29, 21, 0, 0, tzinfo=UTC)


def _entry(wtype: str) -> dict[str, Any]:
    """Build a log entry of the given type.

    Args:
        wtype: The ``workout_data.type`` value.

    Returns:
        A log entry dict.
    """
    return {"timestamp": "2026-08-29T10:00:00+00:00", "workout_data": {"type": wtype}}


def _with_log(entries: dict[str, list[dict[str, Any]]], tmp_path: Path) -> Any:
    """Patch the module's LOG_FILE at a temporary log holding ``entries``.

    Args:
        entries: Date-keyed log contents.
        tmp_path: pytest temporary directory.

    Returns:
        A patch context manager for the module-level LOG_FILE.
    """
    log = tmp_path / "log.json"
    log.write_text(json.dumps(entries), encoding="utf-8")
    return patch(f"{_PKG}.LOG_FILE", log)


class TestWorkoutCreditsToday:
    """Today's credits come from the enforcement rule, not a second count."""

    def test_no_entries_is_zero(self, tmp_path: Path) -> None:
        """An untouched day earns nothing."""
        with _with_log({}, tmp_path):
            assert workout_credits_today(now=_SATURDAY) == 0

    def test_a_workout_counts(self, tmp_path: Path) -> None:
        """A verified workout today earns a credit."""
        with _with_log({"2026-08-29": [_entry("phone_verified")]}, tmp_path):
            assert workout_credits_today(now=_SATURDAY) == 1

    def test_the_stronglifts_pair_still_counts_once(self, tmp_path: Path) -> None:
        """Both ingestion paths for one session share today's credit too."""
        entries = {
            "2026-08-29": [_entry("phone_verified"), _entry("pc_workout_verified")],
        }
        with _with_log(entries, tmp_path):
            assert workout_credits_today(now=_SATURDAY) == 1

    def test_a_relaxed_day_skip_earns_nothing(self, tmp_path: Path) -> None:
        """Dismissing the popup is not a workout — so it is a 6h gaming day."""
        with _with_log({"2026-08-29": [_entry("relaxed_day_skip")]}, tmp_path):
            assert workout_credits_today(now=_SATURDAY) == 0

    def test_yesterdays_workout_does_not_count_today(self, tmp_path: Path) -> None:
        """The budget is per gaming day, so only today's entries count."""
        with _with_log({"2026-08-28": [_entry("phone_verified")]}, tmp_path):
            assert workout_credits_today(now=_SATURDAY) == 0

    def test_non_dict_entries_are_ignored(self, tmp_path: Path) -> None:
        """A malformed entry must not crash the endpoint."""
        log = tmp_path / "log.json"
        log.write_text(json.dumps({"2026-08-29": ["junk"]}), encoding="utf-8")
        with patch(f"{_PKG}.LOG_FILE", log):
            assert workout_credits_today(now=_SATURDAY) == 0


class TestStatusPayload:
    """The status payload is JSON-safe and carries the gaming fact."""

    def test_no_workout_today_reads_as_a_cut_budget(self, tmp_path: Path) -> None:
        """workout_today False is what makes the enforcer apply 6h."""
        with _with_log({}, tmp_path):
            payload = build_status_payload(now=_SATURDAY)
        assert payload["gaming"]["workout_today"] is False
        assert "no counted workout" in payload["gaming"]["reason"]

    def test_a_workout_today_reads_as_earned(self, tmp_path: Path) -> None:
        """A logged workout restores the full budget."""
        with _with_log({"2026-08-29": [_entry("phone_verified")]}, tmp_path):
            payload = build_status_payload(now=_SATURDAY)
        assert payload["gaming"]["workout_today"] is True
        assert payload["gaming"]["credits_today"] == 1

    def test_payload_round_trips_through_json(self, tmp_path: Path) -> None:
        """No dataclass or datetime may leak into the HTTP body."""
        with _with_log({}, tmp_path):
            payload = build_status_payload(now=_SATURDAY)
        assert json.loads(json.dumps(payload))["summary_line"]

    def test_payload_carries_the_derived_one_liners(self, tmp_path: Path) -> None:
        """The i3blocks line and the tray word come from the same snapshot."""
        with _with_log({}, tmp_path):
            payload = build_status_payload(now=_SATURDAY)
        assert payload["compliance_state"] in {"ok", "warn", "lock"}
        assert "snapshot" in payload


class TestDecisionsPayload:
    """The Why view gets a bounded, newest-first slice of the trail."""

    def test_newest_first(self) -> None:
        """The browser reads top-down; the trail is stored oldest-first."""
        trail = [{"timestamp": "1"}, {"timestamp": "2"}, {"timestamp": "3"}]
        with patch(f"{_PKG}.read_decisions", return_value=trail):
            payload = build_decisions_payload(limit=2)
        assert [d["timestamp"] for d in payload["decisions"]] == ["3", "2"]
        assert payload["total"] == 3
        assert payload["returned"] == 2

    def test_a_non_positive_limit_returns_everything(self) -> None:
        """Guards the slice: limit=0 must not silently mean "no history"."""
        trail = [{"timestamp": "1"}, {"timestamp": "2"}]
        with patch(f"{_PKG}.read_decisions", return_value=trail):
            payload = build_decisions_payload(limit=0)
        assert payload["returned"] == 2
