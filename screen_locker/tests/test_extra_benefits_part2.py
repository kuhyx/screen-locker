"""Tests for _extra_benefits module (streak, shutdown bonus, EB extension)."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import TYPE_CHECKING

from screen_locker._extra_benefits import (
    has_extended_early_bird,
    preview_bonus_if_week_ended_now,
    weekly_shutdown_bonus_hours,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestWeeklyShutdownBonusHours:
    """Tests for weekly_shutdown_bonus_hours."""

    def test_returns_zero_when_missing(self, tmp_path: Path) -> None:
        """No state file → 0."""
        f = tmp_path / "state.json"
        assert weekly_shutdown_bonus_hours(f) == 0

    def test_returns_current_week_bonus(self, tmp_path: Path) -> None:
        """Returns the banked bonus for the current ISO week."""
        now = datetime.now(tz=UTC).astimezone()
        year, week, _ = now.isocalendar()
        current_week = f"{year}-W{week:02d}"
        f = tmp_path / "state.json"
        f.write_text(json.dumps({"weekly_shutdown_bonus_hours": {current_week: 3}}))
        assert weekly_shutdown_bonus_hours(f) == 3

    def test_ignores_other_weeks(self, tmp_path: Path) -> None:
        """A bonus banked for a different ISO week is not returned."""
        f = tmp_path / "state.json"
        f.write_text(json.dumps({"weekly_shutdown_bonus_hours": {"2020-W01": 5}}))
        assert weekly_shutdown_bonus_hours(f) == 0


class TestPreviewBonusIfWeekEndedNow:
    """Tests for preview_bonus_if_week_ended_now — pure threshold math."""

    def test_below_threshold_returns_zero(self) -> None:
        """< 5 workouts: no streak increment, no bonus (line 67 branch)."""
        assert preview_bonus_if_week_ended_now(3, current_streak=2) == (0, 0)

    def test_at_threshold_awards_streak_and_bonus(self) -> None:
        """Exactly 5 workouts: streak+1, bonus = count - 4."""
        assert preview_bonus_if_week_ended_now(5, current_streak=0) == (1, 1)

    def test_above_threshold_awards_larger_bonus(self) -> None:
        """7 workouts: bonus = 7 - 4 = 3."""
        assert preview_bonus_if_week_ended_now(7, current_streak=0) == (1, 3)

    def test_milestone_streak_adds_extra_hour(self) -> None:
        """Streak reaching a multiple of 4 adds +1h on top of the base bonus."""
        assert preview_bonus_if_week_ended_now(5, current_streak=3) == (4, 2)


class TestHasExtendedEarlyBird:
    """Tests for has_extended_early_bird."""

    def test_returns_false_when_current_week_not_in_list(self, tmp_path: Path) -> None:
        """Current ISO week absent from list → False."""
        f = tmp_path / "state.json"
        f.write_text(json.dumps({"extended_early_bird_iso_weeks": ["2020-W01"]}))
        assert has_extended_early_bird(f) is False

    def test_returns_true_when_current_week_is_in_list(self, tmp_path: Path) -> None:
        """Current ISO week present in list → True."""
        now = datetime.now(tz=UTC).astimezone()
        year, week, _ = now.isocalendar()
        current_week = f"{year}-W{week:02d}"
        f = tmp_path / "state.json"
        f.write_text(json.dumps({"extended_early_bird_iso_weeks": [current_week]}))
        assert has_extended_early_bird(f) is True

    def test_explicit_today_override(self, tmp_path: Path) -> None:
        """An explicit `today` is used instead of the real wall clock."""
        f = tmp_path / "state.json"
        f.write_text(json.dumps({"extended_early_bird_iso_weeks": ["2024-W01"]}))
        fixed_today = datetime(2024, 1, 5, tzinfo=UTC)
        assert has_extended_early_bird(f, today=fixed_today) is True
        assert has_extended_early_bird(f) is False
