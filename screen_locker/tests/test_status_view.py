"""Tests for the read-only Tkinter status window's rendering (StatusWindow.render).

textgate: every section is glyphs (``screen_locker._glyphs``) and numbers,
so these assert glyphs, numbers and colours, never English words.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gatelock import LockConfig

from screen_locker import _glyphs as g
from screen_locker._compliance_state import AutoUpgradeOpportunity

if TYPE_CHECKING:
    from unittest.mock import MagicMock
from screen_locker.tests._status_view_helpers import (
    _day,
    _lock_explanation,
    _make_window,
    _shutdown,
    _snapshot,
    _texts,
    _week,
)

_PALETTE = LockConfig().palette


def _colored(mock_tk: MagicMock) -> list[tuple[str, str]]:
    """(text, fg) of every Label, in call order."""
    return [
        (c.kwargs.get("text", ""), c.kwargs.get("fg", ""))
        for c in mock_tk.Label.call_args_list
    ]


class TestSectionToday:
    """SectionToday."""

    def test_counted_shows_checkmark_and_entry(self, mock_tk: MagicMock) -> None:
        """A counted day shows the tick and its entry's glyph, not the source."""
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
        assert f"{g.OK} {g.LIFT}" in texts
        assert "gym" not in texts

    def test_sick_day_shows_sick_mark(self, mock_tk: MagicMock) -> None:
        """Sick day shows the sick cross twice: mark and cell."""
        snap = _snapshot(today=_day(entry_types=(), is_sick_day=True))
        _make_window(mock_tk, snap)
        assert f"{g.SICK} {g.WEEK_SICK}" in _texts(mock_tk)

    def test_no_entry_shows_fail_and_empty_circle(self, mock_tk: MagicMock) -> None:
        """No entry: the fail mark over an empty circle, in warning colour."""
        snap = _snapshot(today=_day(entry_types=(), is_sick_day=False))
        _make_window(mock_tk, snap)
        assert (f"{g.FAIL} {g.WEEK_EMPTY}", _PALETTE.warning) in _colored(mock_tk)

    def test_unknown_entry_type_falls_back_to_tick(self, mock_tk: MagicMock) -> None:
        """An entry type with no glyph shows as a tick, never as its name."""
        snap = _snapshot(today=_day(entry_types=("mystery",), counted=True))
        _make_window(mock_tk, snap)
        texts = _texts(mock_tk)
        assert f"{g.OK} {g.OK}" in texts
        assert not any("mystery" in t for t in texts)


class TestSectionWeek:
    """SectionWeek."""

    def test_under_minimum_is_warning_dots(self, mock_tk: MagicMock) -> None:
        """Under the minimum: filled/empty dots and the count, warning colour."""
        snap = _snapshot(week=_week(counted_count=2, remaining=2, extra=0))
        _make_window(mock_tk, snap)
        assert (g.dots(2, 4), _PALETTE.warning) in _colored(mock_tk)

    def test_over_minimum_is_success_dots(self, mock_tk: MagicMock) -> None:
        """Over the minimum: the count above the total, success colour."""
        snap = _snapshot(week=_week(counted_count=5, remaining=0, extra=1))
        _make_window(mock_tk, snap)
        assert ("●●●● 5/4", _PALETTE.success) in _colored(mock_tk)

    def test_exact_minimum_is_success(self, mock_tk: MagicMock) -> None:
        """At exactly the minimum the week is met: success colour."""
        snap = _snapshot(week=_week(counted_count=4, remaining=0, extra=0))
        _make_window(mock_tk, snap)
        assert (g.dots(4, 4), _PALETTE.success) in _colored(mock_tk)

    def test_renders_one_cell_per_day(self, mock_tk: MagicMock) -> None:
        """One row, one cell per day in order, no weekday names."""
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
        assert f"{g.LIFT}  {g.WEEK_SICK}  {g.WEEK_EMPTY}" in texts
        assert not any("Mon" in t for t in texts)


class TestSectionLockExplanation:
    """SectionLockExplanation."""

    def test_fired_with_auto_upgrade_and_heat_skip_pending(
        self, mock_tk: MagicMock
    ) -> None:
        """Fired: the lock square + stage glyph in danger, and a retry mark."""
        snap = _snapshot(
            lock_explanation=_lock_explanation(
                fired=True,
                stage="would_lock",
                reason="Full lock.",
                auto_upgrade=AutoUpgradeOpportunity(
                    would_attempt=True, via="sick_day", reason="will try phone"
                ),
                heat_skip_evaluated=False,
            )
        )
        _make_window(mock_tk, snap)
        colored = _colored(mock_tk)
        assert (f"{g.LOCK} {g.LIFT}", _PALETTE.danger) in colored
        assert (g.RETRY, _PALETTE.warning) in colored
        assert "Full lock." not in _texts(mock_tk)

    def test_not_fired_no_auto_upgrade(self, mock_tk: MagicMock) -> None:
        """Not fired: the open square + stage glyph in success, no retry mark."""
        snap = _snapshot(
            lock_explanation=_lock_explanation(fired=False, reason="Skipped.")
        )
        _make_window(mock_tk, snap)
        colored = _colored(mock_tk)
        assert (f"{g.UNLOCK} {g.OK}", _PALETTE.success) in colored
        assert (g.RETRY, _PALETTE.warning) not in colored

    def test_unknown_stage_shows_only_the_square(self, mock_tk: MagicMock) -> None:
        """A stage without a glyph shows just the square, no trailing space."""
        snap = _snapshot(lock_explanation=_lock_explanation(stage="brand_new_step"))
        _make_window(mock_tk, snap)
        assert g.UNLOCK in _texts(mock_tk)

    def test_temperature_section_renders_regardless_of_heat_skip_evaluated(
        self, mock_tk: MagicMock
    ) -> None:
        """The live temperature section is unconditional — see
        ``TestTemperatureSectionRendering`` for its actual content states."""
        snap = _snapshot(
            lock_explanation=_lock_explanation(fired=True, heat_skip_evaluated=True)
        )
        _make_window(mock_tk, snap)
        assert any(t.startswith(g.HEAT) for t in _texts(mock_tk))


class TestSectionShutdown:
    """SectionShutdown."""

    def test_tonight_present_shows_live_config(self, mock_tk: MagicMock) -> None:
        """Tonight present shows both live times after the shutdown glyph."""
        snap = _snapshot(shutdown=_shutdown(tonight=(1320, 1380, 300)))
        _make_window(mock_tk, snap)
        assert f"{g.SHUTDOWN} 22:00 · 23:00" in _texts(mock_tk)

    def test_tonight_absent_shows_fail_glyph(self, mock_tk: MagicMock) -> None:
        """Tonight absent shows the shutdown glyph crossed out, warning colour."""
        snap = _snapshot(shutdown=_shutdown(tonight=None))
        _make_window(mock_tk, snap)
        assert (f"{g.SHUTDOWN} {g.FAIL}", _PALETTE.warning) in _colored(mock_tk)

    def test_shows_rest_of_week_and_next_week_preview(self, mock_tk: MagicMock) -> None:
        """Rest of week and next week are rows of times, muted, no labels."""
        snap = _snapshot()
        _make_window(mock_tk, snap)
        row = "  ".join(["21:00"] * 7)
        assert _colored(mock_tk).count((row, _PALETTE.muted)) == 2
        assert not any("two separate systems" in t for t in _texts(mock_tk))
