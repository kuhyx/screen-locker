"""Tests for the read-only Tkinter status window's rendering (StatusWindow.render)."""

from __future__ import annotations

from unittest.mock import MagicMock

from screen_locker._compliance_state import AutoUpgradeOpportunity
from screen_locker._status_view_verify import _verify_phone_then_runnerup
from screen_locker.tests._status_view_helpers import (
    _day,
    _lock_explanation,
    _make_window,
    _shutdown,
    _sick_budget,
    _snapshot,
    _texts,
    _week,
)


class TestSectionToday:
    def test_counted_shows_checkmark_and_entry(self, mock_tk: MagicMock) -> None:
        snap = _snapshot(
            today=_day(
                entry_types=("phone_verified",),
                counted=True,
                day_count=1,
                source="gym",
            )
        )
        _make_window(mock_tk, snap)
        texts = _texts(mock_tk)
        assert any("✓" in t and "phone_verified" in t for t in texts)
        assert any(t == "gym" for t in texts)

    def test_sick_day_shows_sick_mark(self, mock_tk: MagicMock) -> None:
        snap = _snapshot(today=_day(entry_types=(), is_sick_day=True))
        _make_window(mock_tk, snap)
        assert any("😷" in t and "sick day" in t for t in _texts(mock_tk))

    def test_no_entry_shows_dash(self, mock_tk: MagicMock) -> None:
        snap = _snapshot(today=_day(entry_types=(), is_sick_day=False))
        _make_window(mock_tk, snap)
        assert any("no entry yet" in t for t in _texts(mock_tk))

    def test_empty_source_adds_no_extra_line(self, mock_tk: MagicMock) -> None:
        snap = _snapshot(
            today=_day(
                entry_types=("phone_verified",),
                counted=True,
                day_count=1,
                source="",
            )
        )
        _make_window(mock_tk, snap)
        # Only the main "Today (...)" line, no second call for an empty source.
        today_related = [t for t in _texts(mock_tk) if "Today" in t]
        assert len(today_related) == 1


class TestSectionWeek:
    def test_shows_remaining_message_when_under_minimum(
        self, mock_tk: MagicMock
    ) -> None:
        snap = _snapshot(week=_week(counted_count=2, remaining=2, extra=0))
        _make_window(mock_tk, snap)
        assert any("Need 2 more this week." in t for t in _texts(mock_tk))

    def test_shows_extra_message_when_over_minimum(self, mock_tk: MagicMock) -> None:
        snap = _snapshot(week=_week(counted_count=5, remaining=0, extra=1))
        _make_window(mock_tk, snap)
        assert any("above the weekly minimum" in t for t in _texts(mock_tk))

    def test_shows_neither_message_at_exact_minimum(self, mock_tk: MagicMock) -> None:
        snap = _snapshot(week=_week(counted_count=4, remaining=0, extra=0))
        _make_window(mock_tk, snap)
        texts = _texts(mock_tk)
        assert not any("Need" in t and "more this week" in t for t in texts)
        assert not any("above the weekly minimum" in t for t in texts)

    def test_renders_a_line_per_day(self, mock_tk: MagicMock) -> None:
        days = (
            _day(
                date="2024-01-01",
                label="Mon Jan 01",
                counted=True,
                day_count=1,
                entry_types=("phone_verified",),
            ),
            _day(date="2024-01-02", label="Tue Jan 02", is_sick_day=True),
            _day(date="2024-01-03", label="Wed Jan 03"),
        )
        snap = _snapshot(week=_week(days=days))
        _make_window(mock_tk, snap)
        texts = _texts(mock_tk)
        assert any("Mon Jan 01" in t and "✓" in t for t in texts)
        assert any("Tue Jan 02" in t and "😷" in t for t in texts)
        assert any("Wed Jan 03" in t and "no entry" in t for t in texts)


class TestSectionLockExplanation:
    def test_fired_with_auto_upgrade_and_heat_skip_pending(
        self, mock_tk: MagicMock
    ) -> None:
        snap = _snapshot(
            lock_explanation=_lock_explanation(
                fired=True,
                reason="Full lock.",
                auto_upgrade=AutoUpgradeOpportunity(
                    would_attempt=True, via="sick_day", reason="will try phone"
                ),
                heat_skip_evaluated=False,
            )
        )
        _make_window(mock_tk, snap)
        texts = _texts(mock_tk)
        assert any(t == "Full lock." for t in texts)
        assert any("Pending auto-upgrade: will try phone" in t for t in texts)

    def test_not_fired_no_auto_upgrade(self, mock_tk: MagicMock) -> None:
        snap = _snapshot(
            lock_explanation=_lock_explanation(fired=False, reason="Skipped.")
        )
        _make_window(mock_tk, snap)
        texts = _texts(mock_tk)
        assert any(t == "Skipped." for t in texts)
        assert not any("Pending auto-upgrade" in t for t in texts)

    def test_temperature_section_renders_regardless_of_heat_skip_evaluated(
        self, mock_tk: MagicMock
    ) -> None:
        """The live temperature section is unconditional — see
        ``TestTemperatureSectionRendering`` for its actual content states."""
        snap = _snapshot(
            lock_explanation=_lock_explanation(fired=True, heat_skip_evaluated=True)
        )
        _make_window(mock_tk, snap)
        assert any("Warsaw Temperature" in t for t in _texts(mock_tk))


class TestSectionSickBudget:
    def test_exhausted_uses_warning_color(self, mock_tk: MagicMock) -> None:
        snap = _snapshot(sick_budget=_sick_budget(used_7d=1, exhausted=True))
        _make_window(mock_tk, snap)
        calls = [
            c
            for c in mock_tk.Label.call_args_list
            if "week" in c.kwargs.get("text", "")
        ]
        assert any(c.kwargs.get("fg") == "#ff4444" for c in calls)

    def test_not_exhausted_uses_normal_color(self, mock_tk: MagicMock) -> None:
        snap = _snapshot(sick_budget=_sick_budget(used_7d=0, exhausted=False))
        _make_window(mock_tk, snap)
        calls = [
            c
            for c in mock_tk.Label.call_args_list
            if "week" in c.kwargs.get("text", "")
        ]
        assert any(c.kwargs.get("fg") == "#cccccc" for c in calls)


class TestSectionShutdown:
    def test_tonight_present_shows_live_config(self, mock_tk: MagicMock) -> None:
        snap = _snapshot(shutdown=_shutdown(tonight=(22, 23, 5)))
        _make_window(mock_tk, snap)
        assert any("22:00" in t and "23:00" in t for t in _texts(mock_tk))

    def test_tonight_absent_shows_unavailable_message(self, mock_tk: MagicMock) -> None:
        snap = _snapshot(shutdown=_shutdown(tonight=None))
        _make_window(mock_tk, snap)
        assert any("Live shutdown config unavailable." in t for t in _texts(mock_tk))

    def test_shows_rest_of_week_and_next_week_preview(self, mock_tk: MagicMock) -> None:
        snap = _snapshot()
        _make_window(mock_tk, snap)
        texts = _texts(mock_tk)
        assert any("Rest of week:" in t for t in texts)
        assert any("Next week (speculative):" in t for t in texts)


class TestVerifyPhoneThenRunnerup:
    """The "Check Phone" worker: StrongLifts first, then RunnerUp as fallback."""

    def test_stronglifts_verified_short_circuits(self) -> None:
        """A verified phone workout wins and RunnerUp is never consulted."""
        verifier = MagicMock()
        verifier._verify_phone_workout.return_value = ("verified", "5x5 done")

        result = _verify_phone_then_runnerup(verifier)

        assert result == ("phone_verified", "verified", "5x5 done", None)
        verifier._verify_runnerup_workout.assert_not_called()

    def test_falls_back_to_runnerup_when_phone_not_verified(self) -> None:
        """StrongLifts miss → a verified run credits as runnerup_verified."""
        verifier = MagicMock()
        verifier._verify_phone_workout.return_value = ("not_verified", "stale")
        verifier._verify_runnerup_workout.return_value = ("verified", "9.8 km")

        result = _verify_phone_then_runnerup(verifier)

        assert result == ("runnerup_verified", "verified", "stale", "9.8 km")

    def test_neither_source_verified(self) -> None:
        """Neither verified → no credited type, both messages carried back."""
        verifier = MagicMock()
        verifier._verify_phone_workout.return_value = ("not_verified", "stale")
        verifier._verify_runnerup_workout.return_value = ("too_short", "3 km")

        result = _verify_phone_then_runnerup(verifier)

        assert result == (None, "too_short", "stale", "3 km")
