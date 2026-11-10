"""Tests for _compliance_state.explain_lock_decision's full branch trace."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import TYPE_CHECKING
from unittest.mock import patch

import freedays
import sickdays

from screen_locker._compliance_state import explain_lock_decision
from screen_locker._log_mixin import write_signed_entry
from screen_locker.tests._sick_helpers import mark_sick

if TYPE_CHECKING:
    from pathlib import Path


def _today() -> str:
    return datetime.now(tz=UTC).astimezone().strftime("%Y-%m-%d")


class TestExplainLockDecision:
    """Full branch trace of the read-only lock-decision chain."""

    def _files(self, tmp_path: Path) -> dict[str, Path]:
        return {
            "log_file": tmp_path / "log.json",
            "early_bird_pending_file": tmp_path / "early_bird_pending.json",
        }

    def test_scheduled_skip_short_circuits(self, tmp_path: Path) -> None:
        """A freeday mark stops the chain at the scheduled_skip stage, first in the trace."""
        files = self._files(tmp_path)
        freedays.mark(
            freedays.today(),
            paths=freedays.Paths.under(tmp_path / "freedays"),
        )
        result = explain_lock_decision(
            **files,
            weekly_minimum_met=False,
            relaxed_day=False,
        )
        assert result.fired is False
        assert result.stage == "scheduled_skip"
        assert result.trace[0].fired is True

    def test_early_bird_window_still_open_skips(self, tmp_path: Path) -> None:
        """An open early-bird window with a wake-alarm skip stops at early_bird_window_open."""
        files = self._files(tmp_path)
        files["early_bird_pending_file"].write_text(
            json.dumps({"date": _today(), "hmac": "sig"})
        )
        now = datetime.now(tz=UTC).astimezone().replace(hour=6, minute=0)
        with patch(
            "screen_locker._compliance_predicates.verify_entry_hmac", return_value=True
        ):
            result = explain_lock_decision(
                **files,
                weekly_minimum_met=False,
                relaxed_day=False,
                wake_skip=True,
                now=now,
            )
        assert result.fired is False
        assert result.stage == "early_bird_window_open"

    def test_expired_early_bird_falls_through_to_full_lock(
        self, tmp_path: Path
    ) -> None:
        """An expired early-bird marker leads to would_lock via early_bird_expired."""
        files = self._files(tmp_path)
        files["early_bird_pending_file"].write_text(
            json.dumps({"date": _today(), "hmac": "sig"})
        )
        now = datetime.now(tz=UTC).astimezone().replace(hour=10, minute=0)
        with patch(
            "screen_locker._compliance_predicates.verify_entry_hmac", return_value=True
        ):
            result = explain_lock_decision(
                **files,
                weekly_minimum_met=False,
                relaxed_day=False,
                now=now,
            )
        assert result.fired is True
        assert result.stage == "would_lock"
        assert result.auto_upgrade.via == "early_bird_expired"
        expired_step = next(
            t for t in result.trace if t.name == "early_bird_pending_expired"
        )
        assert expired_step.fired is True

    def test_sick_day_skips(self, tmp_path: Path) -> None:
        """A sick day stops the chain at the sick_day stage."""
        files = self._files(tmp_path)
        mark_sick()
        result = explain_lock_decision(
            **files,
            weekly_minimum_met=False,
            relaxed_day=False,
            now=datetime.now(tz=UTC).astimezone().replace(hour=12, minute=0),
        )
        assert result.fired is False
        assert result.stage == "sick_day"

    def test_a_sick_day_that_keeps_the_workout_lock_does_not_skip(
        self, tmp_path: Path
    ) -> None:
        """A sick day that keeps the workout lock does not fire the sick_day skip."""
        files = self._files(tmp_path)
        mark_sick(keep=[sickdays.LOCKER_WORKOUT])
        result = explain_lock_decision(
            **files,
            weekly_minimum_met=False,
            relaxed_day=False,
            now=datetime.now(tz=UTC).astimezone().replace(hour=12, minute=0),
        )
        assert result.stage == "would_lock"
        sick_step = next(t for t in result.trace if t.name == "sick_day")
        assert sick_step.fired is False

    def test_already_logged_skips(self, tmp_path: Path) -> None:
        """A signed log entry for today stops the chain at already_logged."""
        files = self._files(tmp_path)
        files["log_file"].write_text(json.dumps({_today(): {"hmac": "sig"}}))
        with patch(
            "screen_locker._compliance_predicates.verify_entry_hmac", return_value=True
        ):
            result = explain_lock_decision(
                **files,
                weekly_minimum_met=False,
                relaxed_day=False,
                now=datetime.now(tz=UTC).astimezone().replace(hour=12, minute=0),
            )
        assert result.fired is False
        assert result.stage == "already_logged"

    def test_wake_alarm_skip_skips(self, tmp_path: Path) -> None:
        """A wake-alarm skip stops the chain at wake_alarm_skip."""
        files = self._files(tmp_path)
        result = explain_lock_decision(
            **files,
            weekly_minimum_met=False,
            relaxed_day=False,
            wake_skip=True,
            now=datetime.now(tz=UTC).astimezone().replace(hour=12, minute=0),
        )
        assert result.fired is False
        assert result.stage == "wake_alarm_skip"

    def test_carrot_in_force_skips_as_wake_alarm(self, tmp_path: Path) -> None:
        """Before the alarm, during the session, until 11:00 -- one stage, one reason."""
        files = self._files(tmp_path)
        result = explain_lock_decision(
            **files,
            weekly_minimum_met=False,
            relaxed_day=False,
            wake_skip=True,
        )
        assert result.fired is False
        assert result.stage == "wake_alarm_skip"
        assert "early-bird" not in result.reason

    def test_relaxed_day_skips(self, tmp_path: Path) -> None:
        """A relaxed day stops the chain at the relaxed_day stage."""
        files = self._files(tmp_path)
        result = explain_lock_decision(
            **files,
            weekly_minimum_met=False,
            relaxed_day=True,
            now=datetime.now(tz=UTC).astimezone().replace(hour=12, minute=0),
        )
        assert result.fired is False
        assert result.stage == "relaxed_day"

    def test_relaxed_day_already_skipped_short_circuits_before_relaxed_day(
        self, tmp_path: Path
    ) -> None:
        """A same-day relaxed_day_skip entry reports its own accurate stage.

        Without this, the trace would report the generic "relaxed_day" stage
        even after the user already dismissed today's prompt, which is
        misleading — the popup is not about to be shown again.
        """

        files = self._files(tmp_path)
        write_signed_entry(files["log_file"], _today(), {"type": "relaxed_day_skip"})
        result = explain_lock_decision(
            **files,
            weekly_minimum_met=False,
            relaxed_day=True,
            now=datetime.now(tz=UTC).astimezone().replace(hour=12, minute=0),
        )
        assert result.fired is False
        assert result.stage == "relaxed_day_already_skipped"

    def test_weekly_minimum_met_skips(self, tmp_path: Path) -> None:
        """A met weekly minimum stops the chain at weekly_minimum_met."""
        files = self._files(tmp_path)
        result = explain_lock_decision(
            **files,
            weekly_minimum_met=True,
            relaxed_day=False,
            now=datetime.now(tz=UTC).astimezone().replace(hour=12, minute=0),
        )
        assert result.fired is False
        assert result.stage == "weekly_minimum_met"

    def test_full_lock_when_nothing_applies(self, tmp_path: Path) -> None:
        """With no skip applicable the decision is would_lock with no auto-upgrade."""
        files = self._files(tmp_path)
        result = explain_lock_decision(
            **files,
            weekly_minimum_met=False,
            relaxed_day=False,
            now=datetime.now(tz=UTC).astimezone().replace(hour=12, minute=0),
        )
        assert result.fired is True
        assert result.stage == "would_lock"
        assert result.auto_upgrade.via == "none"
        assert result.heat_skip_evaluated is False

    def test_defaults_now_to_current_time(self, tmp_path: Path) -> None:
        """Covers the ``now is None`` branch — just needs to not raise."""
        files = self._files(tmp_path)
        result = explain_lock_decision(
            **files,
            weekly_minimum_met=False,
            relaxed_day=False,
        )
        assert isinstance(result.fired, bool)
