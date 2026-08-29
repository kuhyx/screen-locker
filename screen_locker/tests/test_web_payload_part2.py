"""Tests for _web_payload.build_health_payload.

Split out of test_web_payload.py for the 250-line cap.

Every field asserted here exists because its absence once went unnoticed: a
timer systemd deleted to break an ordering cycle, a disarm marker nobody
removed, a log that quietly stopped being written. The rule the tests enforce
is that "could not check" is its own state and never reads as a pass.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import patch

from screen_locker._armed_state import TimerState
from screen_locker._web_payload import build_health_payload

if TYPE_CHECKING:
    from pathlib import Path

_PKG = "screen_locker._web_payload"

_SATURDAY = datetime(2026, 8, 29, 21, 0, 0, tzinfo=UTC)


class TestHealthPayload:
    """Health turns every silent absence into a rendered value."""

    def _states(self, *, armed: bool) -> list[TimerState]:
        """Build timer states for the fake.

        Args:
            armed: Whether the timers should read as armed.

        Returns:
            One state per required timer.
        """
        return [
            TimerState("workout-locker.timer", armed, "enabled", armed),
        ]

    def test_armed_when_everything_checks_out(self, tmp_path: Path) -> None:
        """Timers armed, no marker, systemctl present."""
        with (
            patch(f"{_PKG}.systemctl_available", return_value=True),
            patch(f"{_PKG}.collect_states", return_value=self._states(armed=True)),
            patch(f"{_PKG}.DISARM_MARKER", tmp_path / "absent"),
        ):
            payload = build_health_payload(now=_SATURDAY)
        assert payload["armed"] is True
        assert payload["timers"][0]["armed"] is True

    def test_unchecked_is_never_armed(self, tmp_path: Path) -> None:
        """Without systemctl the answer is unknown, which is not a pass."""
        with (
            patch(f"{_PKG}.systemctl_available", return_value=False),
            patch(f"{_PKG}.DISARM_MARKER", tmp_path / "absent"),
        ):
            payload = build_health_payload(now=_SATURDAY)
        assert payload["timers_checked"] is False
        assert payload["armed"] is False
        assert payload["timers"] == []

    def test_disarm_marker_overrides_armed_timers(self, tmp_path: Path) -> None:
        """The marker is the deliberate off switch; it must win."""
        marker = tmp_path / "DISARMED"
        marker.write_text("off for a reason", encoding="utf-8")
        with (
            patch(f"{_PKG}.systemctl_available", return_value=True),
            patch(f"{_PKG}.collect_states", return_value=self._states(armed=True)),
            patch(f"{_PKG}.DISARM_MARKER", marker),
        ):
            payload = build_health_payload(now=_SATURDAY)
        assert payload["disarmed"] is True
        assert payload["armed"] is False

    def test_missing_log_reports_unknown_age(self, tmp_path: Path) -> None:
        """A log that is not there reads as unknown, not as fresh."""
        with (
            patch(f"{_PKG}.systemctl_available", return_value=False),
            patch(f"{_PKG}.DISARM_MARKER", tmp_path / "absent"),
            patch(f"{_PKG}.LOG_FILE", tmp_path / "missing.json"),
            patch(f"{_PKG}.read_decisions", return_value=[]),
        ):
            payload = build_health_payload(now=_SATURDAY)
        assert payload["log_age_seconds"] is None
        assert payload["last_decision_age_seconds"] is None

    def test_decision_age_is_measured_from_the_newest_entry(
        self,
        tmp_path: Path,
    ) -> None:
        """A quiet locker shows up as an old last decision."""
        trail = [{"timestamp": "2026-08-29T20:00:00+00:00"}]
        with (
            patch(f"{_PKG}.systemctl_available", return_value=False),
            patch(f"{_PKG}.DISARM_MARKER", tmp_path / "absent"),
            patch(f"{_PKG}.read_decisions", return_value=trail),
        ):
            payload = build_health_payload(now=_SATURDAY)
        assert payload["last_decision_age_seconds"] == 3600

    def test_a_corrupt_timestamp_reads_as_unknown(self, tmp_path: Path) -> None:
        """An unparsable stamp must not crash the Health view."""
        with (
            patch(f"{_PKG}.systemctl_available", return_value=False),
            patch(f"{_PKG}.DISARM_MARKER", tmp_path / "absent"),
            patch(f"{_PKG}.read_decisions", return_value=[{"timestamp": "nonsense"}]),
        ):
            payload = build_health_payload(now=_SATURDAY)
        assert payload["last_decision_age_seconds"] is None

    def test_a_missing_timestamp_reads_as_unknown(self, tmp_path: Path) -> None:
        """A decision line without a timestamp is handled, not assumed."""
        with (
            patch(f"{_PKG}.systemctl_available", return_value=False),
            patch(f"{_PKG}.DISARM_MARKER", tmp_path / "absent"),
            patch(f"{_PKG}.read_decisions", return_value=[{"reason": "enforced"}]),
        ):
            payload = build_health_payload(now=_SATURDAY)
        assert payload["last_decision_age_seconds"] is None

    def test_log_age_is_measured_from_mtime(self, tmp_path: Path) -> None:
        """A written log reports a real, non-negative age."""
        log = tmp_path / "log.json"
        log.write_text("{}", encoding="utf-8")
        with (
            patch(f"{_PKG}.systemctl_available", return_value=False),
            patch(f"{_PKG}.DISARM_MARKER", tmp_path / "absent"),
            patch(f"{_PKG}.LOG_FILE", log),
            patch(f"{_PKG}.read_decisions", return_value=[]),
        ):
            payload = build_health_payload()
        age = payload["log_age_seconds"]
        assert isinstance(age, float)
        assert age >= 0
