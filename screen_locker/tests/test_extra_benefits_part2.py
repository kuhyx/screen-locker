"""Tests for _extra_benefits (streak, legacy bonus key dropped, EB extension)."""

from __future__ import annotations

from datetime import UTC, datetime, tzinfo
import json
from typing import TYPE_CHECKING, ClassVar, Self
from unittest.mock import patch

from screen_locker._extra_benefits import (
    has_extended_early_bird,
    process_week_transition,
    week_rewards,
)

if TYPE_CHECKING:
    from pathlib import Path


class _FrozenDatetime(datetime):
    """``datetime`` whose ``now`` is pinned to Monday 2026-10-12 12:00 UTC."""

    @classmethod
    def now(cls, tz: tzinfo | None = None) -> Self:
        """The first Monday after the bonus was dropped (start of 2026-W42)."""
        del tz
        return cls(2026, 10, 12, 12, 0, tzinfo=UTC)


class TestBonusDroppedAtW42:
    """The 2026-W41 -> W42 rollover banks nothing and drops the legacy bonus map."""

    _STATE: ClassVar[dict[str, object]] = {
        "consecutive_5plus_weeks": 3,
        "last_processed_iso_week": "2026-W41",
        "weekly_shutdown_bonus_hours": {"2026-W40": 3, "2026-W41": 2},
        "extended_early_bird_iso_weeks": ["2026-W41"],
        "shutdown_bonus_granted_for": ["2026-08-24"],
    }

    def test_w42_transition_banks_nothing(self, tmp_path: Path) -> None:
        """5 workouts in W41 and a 4th streak week: early-bird yes, hours no."""
        f = tmp_path / "state.json"
        f.write_text(json.dumps(self._STATE))
        with (
            patch("screen_locker._extra_benefits.datetime", _FrozenDatetime),
            patch(
                "screen_locker._extra_benefits.count_weekly_workouts", return_value=5
            ),
        ):
            rewards = process_week_transition(tmp_path / "log.json", f)

        assert rewards == ["5 workouts in 2026-W41! 4-week streak"]
        state = json.loads(f.read_text())
        # Sibling keys (the compensation guard) survive; only the dead map goes.
        assert state == {
            "consecutive_5plus_weeks": 4,
            "last_processed_iso_week": "2026-W42",
            "extended_early_bird_iso_weeks": ["2026-W41", "2026-W42"],
            "shutdown_bonus_granted_for": ["2026-08-24"],
            "week_rewards": {"iso_week": "2026-W42", "messages": rewards},
        }
        w42 = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
        assert has_extended_early_bird(f, today=w42) is True
        # The message the transition produced is kept for the status window,
        # for the week it was earned in only.
        assert week_rewards(f, today=w42) == tuple(rewards)
        assert not week_rewards(f, today=datetime(2026, 10, 19, 12, 0, tzinfo=UTC))

    def test_no_stored_rewards_reads_as_empty(self, tmp_path: Path) -> None:
        """Missing file, or a state without the key, has nothing to show."""
        assert not week_rewards(tmp_path / "absent.json")
        f = tmp_path / "state.json"
        f.write_text(json.dumps({"consecutive_5plus_weeks": 2}))
        assert not week_rewards(f)


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
