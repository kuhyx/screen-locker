"""The status window shows the workout streak and early-bird state it tracks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from screen_locker.tests._status_view_helpers import (
    _make_window,
    _snapshot,
    _texts,
)

if TYPE_CHECKING:
    from unittest.mock import MagicMock


def _fg_of(mock_tk: MagicMock, needle: str) -> list[object]:
    return [
        c.kwargs.get("fg")
        for c in mock_tk.Label.call_args_list
        if needle in c.kwargs.get("text", "")
    ]


class TestSectionStreak:
    """Tests for StatusWindow._section_streak (display only)."""

    def test_shows_the_real_week_count_in_success_color(
        self, mock_tk: MagicMock
    ) -> None:
        window = _make_window(mock_tk, _snapshot(streak=3))
        assert any("3-week streak" in t for t in _texts(mock_tk))
        assert window._colors.palette.success in _fg_of(mock_tk, "3-week streak")

    def test_zero_streak_is_stated_plainly_not_padded(self, mock_tk: MagicMock) -> None:
        window = _make_window(mock_tk, _snapshot(streak=0))
        texts = _texts(mock_tk)
        assert any("No streak" in t for t in texts)
        assert not any("-week streak" in t for t in texts)
        assert window._colors.palette.muted in _fg_of(mock_tk, "No streak")

    def test_early_bird_is_never_rendered(self, mock_tk: MagicMock) -> None:
        """The 09:00 early-bird extension is gone (wake-alarm owns it)."""
        _make_window(mock_tk, _snapshot(streak=2, early_bird_extended=True))
        assert not any("arly-bird" in t for t in _texts(mock_tk))

    def test_week_reward_reaches_the_window_in_success_color(
        self, mock_tk: MagicMock
    ) -> None:
        msg = "5 workouts in 2026-W41! 4-week streak"
        window = _make_window(mock_tk, _snapshot(streak=4, week_rewards=(msg,)))
        assert msg in _texts(mock_tk)
        assert window._colors.palette.success in _fg_of(mock_tk, msg)

    def test_no_reward_text_when_the_week_has_none(self, mock_tk: MagicMock) -> None:
        _make_window(mock_tk, _snapshot(streak=4))
        assert not any("workouts in 20" in t for t in _texts(mock_tk))

    def test_a_streak_reset_is_not_painted_as_a_win(self, mock_tk: MagicMock) -> None:
        msg = "Streak reset (was 3 weeks of 5+ workouts)"
        window = _make_window(mock_tk, _snapshot(streak=0, week_rewards=(msg,)))
        assert window._colors.palette.warning in _fg_of(mock_tk, msg)
