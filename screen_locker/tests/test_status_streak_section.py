"""The status window shows the workout streak and early-bird state it tracks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from screen_locker import _glyphs as g
from screen_locker.tests._status_view_helpers import (
    _make_window,
    _snapshot,
    _texts,
)

if TYPE_CHECKING:
    from unittest.mock import MagicMock


def _fg_of(mock_tk: MagicMock, text: str) -> list[object]:
    """fg of every Label whose text is exactly *text*."""
    return [
        c.kwargs.get("fg")
        for c in mock_tk.Label.call_args_list
        if c.kwargs.get("text", "") == text
    ]


class TestSectionStreak:
    """Tests for StatusWindow._section_streak (display only, glyphs + numbers)."""

    def test_shows_the_real_week_count_in_success_color(
        self, mock_tk: MagicMock
    ) -> None:
        """One bar per streak week plus the real count, in the success colour."""
        window = _make_window(mock_tk, _snapshot(streak=3))
        line = f"{g.STREAK * 3} 3"
        assert line in _texts(mock_tk)
        assert window._colors.palette.success in _fg_of(mock_tk, line)

    def test_long_streak_caps_the_bars_not_the_number(self, mock_tk: MagicMock) -> None:
        """Past 10 weeks the bars stop growing; the number stays exact."""
        _make_window(mock_tk, _snapshot(streak=14))
        assert f"{g.STREAK * 10} 14" in _texts(mock_tk)

    def test_zero_streak_is_stated_plainly_not_padded(self, mock_tk: MagicMock) -> None:
        """A zero streak is one bar and 0, muted, never padded."""
        window = _make_window(mock_tk, _snapshot(streak=0))
        line = f"{g.STREAK} 0"
        assert line in _texts(mock_tk)
        assert window._colors.palette.muted in _fg_of(mock_tk, line)

    def test_early_bird_is_never_rendered(self, mock_tk: MagicMock) -> None:
        """The 09:00 early-bird extension is gone (wake-alarm owns it)."""
        _make_window(mock_tk, _snapshot(streak=2, early_bird_extended=True))
        assert not any("arly-bird" in t for t in _texts(mock_tk))

    def test_week_reward_reaches_the_window_in_success_color(
        self, mock_tk: MagicMock
    ) -> None:
        """A week reward shows as bar + gift, success colour; never its words."""
        msg = "5 workouts in 2026-W41! 4-week streak"
        window = _make_window(mock_tk, _snapshot(streak=4, week_rewards=(msg,)))
        assert msg not in _texts(mock_tk)
        line = f"{g.STREAK}{g.GIFT}"
        assert window._colors.palette.success in _fg_of(mock_tk, line)

    def test_no_reward_line_when_the_week_has_none(self, mock_tk: MagicMock) -> None:
        """No reward or reset line appears when the week has no reward."""
        _make_window(mock_tk, _snapshot(streak=4))
        texts = _texts(mock_tk)
        assert f"{g.STREAK}{g.GIFT}" not in texts
        assert f"{g.STREAK}{g.FAIL}" not in texts

    def test_a_streak_reset_is_not_painted_as_a_win(self, mock_tk: MagicMock) -> None:
        """A streak reset shows as bar + fail in the warning colour, not as a win."""
        msg = "Streak reset (was 3 weeks of 5+ workouts)"
        window = _make_window(mock_tk, _snapshot(streak=0, week_rewards=(msg,)))
        assert _fg_of(mock_tk, f"{g.STREAK}{g.FAIL}") == [
            window._colors.palette.warning
        ]
