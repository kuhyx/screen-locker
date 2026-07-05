"""Tests for _extra_benefits module (streak, shutdown bonus, EB extension)."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker._extra_benefits import (
    _load_state,
    _save_state,
    current_streak,
    has_extended_early_bird,
    preview_bonus_if_week_ended_now,
    process_week_transition,
    weekly_shutdown_bonus_hours,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestLoadState:
    """Tests for _load_state helper."""

    def test_returns_empty_dict_when_file_missing(self, tmp_path: Path) -> None:
        """Non-existent file returns empty dict (line 29 — the missing-file branch)."""
        result = _load_state(tmp_path / "nonexistent.json")
        assert result == {}

    def test_returns_parsed_state_when_file_valid(self, tmp_path: Path) -> None:
        """Valid JSON file returns the parsed dict."""
        f = tmp_path / "state.json"
        f.write_text(json.dumps({"weekly_shutdown_bonus_hours": {"2026-W01": 3}}))
        assert _load_state(f) == {"weekly_shutdown_bonus_hours": {"2026-W01": 3}}

    def test_returns_empty_on_oserror(self) -> None:
        """OSError during read is caught and returns empty dict (lines 33-34)."""
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.open.side_effect = OSError("read fail")
        assert _load_state(mock_path) == {}

    def test_returns_empty_on_invalid_json(self, tmp_path: Path) -> None:
        """Corrupt JSON is caught and returns empty dict (lines 33-34)."""
        f = tmp_path / "state.json"
        f.write_text("not-json{{{")
        assert _load_state(f) == {}


class TestSaveState:
    """Tests for _save_state helper."""

    def test_saves_state_to_file(self, tmp_path: Path) -> None:
        """Valid path writes JSON content (lines 39-41)."""
        f = tmp_path / "state.json"
        _save_state(f, {"weekly_shutdown_bonus_hours": {"2026-W01": 2}})
        assert json.loads(f.read_text())["weekly_shutdown_bonus_hours"] == {
            "2026-W01": 2
        }

    def test_logs_warning_on_oserror(self) -> None:
        """OSError during write is caught as warning, does not raise (lines 42-43)."""
        mock_path = MagicMock()
        mock_path.open.side_effect = OSError("write fail")
        _save_state(mock_path, {"key": "val"})  # must not raise


class TestProcessWeekTransition:
    """Tests for process_week_transition."""

    _PAST_WEEK = "2020-W01"

    def test_returns_empty_when_already_processed_this_week(
        self, tmp_path: Path
    ) -> None:
        """Early return when ISO week already processed (line 63)."""
        now = datetime.now(tz=timezone.utc).astimezone()
        year, week, _ = now.isocalendar()
        f = tmp_path / "state.json"
        f.write_text(json.dumps({"last_processed_iso_week": f"{year}-W{week:02d}"}))
        assert process_week_transition(tmp_path / "log.json", f) == []

    @staticmethod
    def _current_week_str() -> str:
        now = datetime.now(tz=timezone.utc).astimezone()
        year, week, _ = now.isocalendar()
        return f"{year}-W{week:02d}"

    def test_awards_bonus_hours_for_5plus_workouts(self, tmp_path: Path) -> None:
        """5+ workouts in previous week: streak += 1, bonus hours += extra."""
        f = tmp_path / "state.json"
        f.write_text(
            json.dumps(
                {
                    "last_processed_iso_week": self._PAST_WEEK,
                    "consecutive_5plus_weeks": 0,
                    "weekly_shutdown_bonus_hours": {},
                    "extended_early_bird_iso_weeks": [],
                }
            )
        )
        with patch(
            "screen_locker._extra_benefits.count_weekly_workouts", return_value=6
        ):
            rewards = process_week_transition(tmp_path / "log.json", f)

        assert len(rewards) >= 1
        assert "+2h shutdown bonus" in rewards[0]
        state = json.loads(f.read_text())
        assert state["consecutive_5plus_weeks"] == 1
        assert state["weekly_shutdown_bonus_hours"][self._current_week_str()] == 2

    def test_awards_milestone_bonus_at_4_week_streak(self, tmp_path: Path) -> None:
        """Streak reaches multiple of 4: +1h extra shutdown bonus."""
        f = tmp_path / "state.json"
        f.write_text(
            json.dumps(
                {
                    "last_processed_iso_week": self._PAST_WEEK,
                    "consecutive_5plus_weeks": 3,
                    "weekly_shutdown_bonus_hours": {},
                    "extended_early_bird_iso_weeks": [],
                }
            )
        )
        with patch(
            "screen_locker._extra_benefits.count_weekly_workouts", return_value=5
        ):
            rewards = process_week_transition(tmp_path / "log.json", f)

        assert any("milestone" in r for r in rewards)
        state = json.loads(f.read_text())
        assert state["consecutive_5plus_weeks"] == 4
        assert state["weekly_shutdown_bonus_hours"][self._current_week_str()] == 2

    def test_marks_current_week_as_extended_early_bird(self, tmp_path: Path) -> None:
        """5+ workouts mark current ISO week as extended EB (line 91-92)."""
        f = tmp_path / "state.json"
        f.write_text(
            json.dumps(
                {
                    "last_processed_iso_week": self._PAST_WEEK,
                    "extended_early_bird_iso_weeks": [],
                }
            )
        )
        with patch(
            "screen_locker._extra_benefits.count_weekly_workouts", return_value=5
        ):
            process_week_transition(tmp_path / "log.json", f)

        now = datetime.now(tz=timezone.utc).astimezone()
        year, week, _ = now.isocalendar()
        state = json.loads(f.read_text())
        assert f"{year}-W{week:02d}" in state["extended_early_bird_iso_weeks"]

    def test_resets_streak_for_fewer_than_5_workouts(self, tmp_path: Path) -> None:
        """< 5 workouts in previous week resets streak and logs message (lines 100-103)."""
        f = tmp_path / "state.json"
        f.write_text(
            json.dumps(
                {
                    "last_processed_iso_week": self._PAST_WEEK,
                    "consecutive_5plus_weeks": 2,
                }
            )
        )
        with patch(
            "screen_locker._extra_benefits.count_weekly_workouts", return_value=3
        ):
            rewards = process_week_transition(tmp_path / "log.json", f)

        assert any("Streak reset" in r for r in rewards)
        assert json.loads(f.read_text())["consecutive_5plus_weeks"] == 0

    def test_no_reset_message_when_streak_was_zero(self, tmp_path: Path) -> None:
        """Zero streak + < 5 workouts: no reset message (line 101 branch False)."""
        f = tmp_path / "state.json"
        f.write_text(
            json.dumps(
                {
                    "last_processed_iso_week": self._PAST_WEEK,
                    "consecutive_5plus_weeks": 0,
                }
            )
        )
        with patch(
            "screen_locker._extra_benefits.count_weekly_workouts", return_value=2
        ):
            rewards = process_week_transition(tmp_path / "log.json", f)

        assert not any("Streak reset" in r for r in rewards)

    def test_fresh_state_file_processed_on_new_week(self, tmp_path: Path) -> None:
        """No state file: _load_state returns {} and transition runs (covers line 29)."""
        f = tmp_path / "nonexistent.json"
        with patch(
            "screen_locker._extra_benefits.count_weekly_workouts", return_value=4
        ):
            process_week_transition(tmp_path / "log.json", f)

        assert f.exists()  # state file created

    def test_duplicate_eb_week_not_added_twice(self, tmp_path: Path) -> None:
        """Current week already in EB list: not added again (line 91 branch False)."""
        now = datetime.now(tz=timezone.utc).astimezone()
        year, week, _ = now.isocalendar()
        current_week = f"{year}-W{week:02d}"
        f = tmp_path / "state.json"
        f.write_text(
            json.dumps(
                {
                    "last_processed_iso_week": self._PAST_WEEK,
                    "extended_early_bird_iso_weeks": [current_week],
                }
            )
        )
        with patch(
            "screen_locker._extra_benefits.count_weekly_workouts", return_value=5
        ):
            process_week_transition(tmp_path / "log.json", f)

        state = json.loads(f.read_text())
        assert state["extended_early_bird_iso_weeks"].count(current_week) == 1


class TestCurrentStreak:
    """Tests for current_streak."""

    def test_returns_zero_when_file_missing(self, tmp_path: Path) -> None:
        """Missing file falls through _load_state → default 0."""
        assert current_streak(tmp_path / "nonexistent.json") == 0

    def test_returns_stored_streak(self, tmp_path: Path) -> None:
        """Stored streak value is returned correctly."""
        f = tmp_path / "state.json"
        f.write_text(json.dumps({"consecutive_5plus_weeks": 5}))
        assert current_streak(f) == 5


class TestWeeklyShutdownBonusHours:
    """Tests for weekly_shutdown_bonus_hours."""

    def test_returns_zero_when_missing(self, tmp_path: Path) -> None:
        """No state file → 0."""
        f = tmp_path / "state.json"
        assert weekly_shutdown_bonus_hours(f) == 0

    def test_returns_current_week_bonus(self, tmp_path: Path) -> None:
        """Returns the banked bonus for the current ISO week."""
        now = datetime.now(tz=timezone.utc).astimezone()
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
        now = datetime.now(tz=timezone.utc).astimezone()
        year, week, _ = now.isocalendar()
        current_week = f"{year}-W{week:02d}"
        f = tmp_path / "state.json"
        f.write_text(json.dumps({"extended_early_bird_iso_weeks": [current_week]}))
        assert has_extended_early_bird(f) is True

    def test_explicit_today_override(self, tmp_path: Path) -> None:
        """An explicit `today` is used instead of the real wall clock."""
        f = tmp_path / "state.json"
        f.write_text(json.dumps({"extended_early_bird_iso_weeks": ["2024-W01"]}))
        fixed_today = datetime(2024, 1, 5, tzinfo=timezone.utc)
        assert has_extended_early_bird(f, today=fixed_today) is True
        assert has_extended_early_bird(f) is False
