"""Tests for _compliance_state.explain_lock_decision's full branch trace."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import TYPE_CHECKING
from unittest.mock import patch

from screen_locker._compliance_state import explain_lock_decision
from screen_locker._sick_tracker import SickHistory

if TYPE_CHECKING:
    from pathlib import Path


def _today() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


class TestExplainLockDecision:
    """Full branch trace of the read-only lock-decision chain."""

    def _files(self, tmp_path: Path) -> dict[str, Path]:
        return {
            "log_file": tmp_path / "workout_log.json",
            "scheduled_skips_file": tmp_path / "scheduled_skips.json",
            "early_bird_pending_file": tmp_path / "early_bird_pending.json",
        }

    def test_scheduled_skip_short_circuits(self, tmp_path: Path) -> None:
        files = self._files(tmp_path)
        files["scheduled_skips_file"].write_text(json.dumps([_today()]))
        result = explain_lock_decision(
            **files,
            sick_history=SickHistory(),
            extended_early_bird=False,
            weekly_minimum_met=False,
            relaxed_day=False,
        )
        assert result.fired is False
        assert result.stage == "scheduled_skip"
        assert result.trace[0].fired is True

    def test_early_bird_window_still_open_skips(self, tmp_path: Path) -> None:
        files = self._files(tmp_path)
        files["early_bird_pending_file"].write_text(
            json.dumps({"date": _today(), "hmac": "sig"})
        )
        now = datetime.now(tz=timezone.utc).astimezone().replace(hour=6, minute=0)
        with patch(
            "screen_locker._compliance_state.verify_entry_hmac", return_value=True
        ):
            result = explain_lock_decision(
                **files,
                sick_history=SickHistory(),
                extended_early_bird=False,
                weekly_minimum_met=False,
                relaxed_day=False,
                now=now,
            )
        assert result.fired is False
        assert result.stage == "early_bird_window_open"

    def test_expired_early_bird_falls_through_to_full_lock(
        self, tmp_path: Path
    ) -> None:
        files = self._files(tmp_path)
        files["early_bird_pending_file"].write_text(
            json.dumps({"date": _today(), "hmac": "sig"})
        )
        now = datetime.now(tz=timezone.utc).astimezone().replace(hour=10, minute=0)
        with patch(
            "screen_locker._compliance_state.verify_entry_hmac", return_value=True
        ):
            result = explain_lock_decision(
                **files,
                sick_history=SickHistory(),
                extended_early_bird=False,
                weekly_minimum_met=False,
                relaxed_day=False,
                now=now,
            )
        assert result.fired is True
        assert result.stage == "full_lock_pending_heat_check"
        assert result.auto_upgrade.via == "early_bird_expired"
        expired_step = next(
            t for t in result.trace if t.name == "early_bird_pending_expired"
        )
        assert expired_step.fired is True

    def test_sick_day_skips(self, tmp_path: Path) -> None:
        files = self._files(tmp_path)
        result = explain_lock_decision(
            **files,
            sick_history=SickHistory(sick_days=[_today()]),
            extended_early_bird=False,
            weekly_minimum_met=False,
            relaxed_day=False,
            now=datetime.now(tz=timezone.utc).astimezone().replace(hour=12, minute=0),
        )
        assert result.fired is False
        assert result.stage == "sick_day"

    def test_already_logged_skips(self, tmp_path: Path) -> None:
        files = self._files(tmp_path)
        files["log_file"].write_text(json.dumps({_today(): {"hmac": "sig"}}))
        with patch(
            "screen_locker._compliance_state.verify_entry_hmac", return_value=True
        ):
            result = explain_lock_decision(
                **files,
                sick_history=SickHistory(),
                extended_early_bird=False,
                weekly_minimum_met=False,
                relaxed_day=False,
                now=datetime.now(tz=timezone.utc)
                .astimezone()
                .replace(hour=12, minute=0),
            )
        assert result.fired is False
        assert result.stage == "already_logged"

    def test_wake_alarm_skip_skips(self, tmp_path: Path) -> None:
        files = self._files(tmp_path)
        result = explain_lock_decision(
            **files,
            sick_history=SickHistory(),
            extended_early_bird=False,
            weekly_minimum_met=False,
            relaxed_day=False,
            wake_skip=True,
            now=datetime.now(tz=timezone.utc).astimezone().replace(hour=12, minute=0),
        )
        assert result.fired is False
        assert result.stage == "wake_alarm_skip"

    def test_fresh_early_bird_time_skips(self, tmp_path: Path) -> None:
        files = self._files(tmp_path)
        now = datetime.now(tz=timezone.utc).astimezone().replace(hour=6, minute=0)
        result = explain_lock_decision(
            **files,
            sick_history=SickHistory(),
            extended_early_bird=False,
            weekly_minimum_met=False,
            relaxed_day=False,
            now=now,
        )
        assert result.fired is False
        assert result.stage == "early_bird_time_fresh"
        assert "08:30" in result.reason
        assert "09:00" not in result.reason

    def test_fresh_early_bird_time_names_09_00_when_extended(
        self, tmp_path: Path
    ) -> None:
        """The re-check time isn't ambiguous — it's whichever one actually applies."""
        files = self._files(tmp_path)
        now = datetime.now(tz=timezone.utc).astimezone().replace(hour=6, minute=0)
        result = explain_lock_decision(
            **files,
            sick_history=SickHistory(),
            extended_early_bird=True,
            weekly_minimum_met=False,
            relaxed_day=False,
            now=now,
        )
        assert result.fired is False
        assert result.stage == "early_bird_time_fresh"
        assert "09:00" in result.reason
        assert "08:30" not in result.reason

    def test_relaxed_day_skips(self, tmp_path: Path) -> None:
        files = self._files(tmp_path)
        result = explain_lock_decision(
            **files,
            sick_history=SickHistory(),
            extended_early_bird=False,
            weekly_minimum_met=False,
            relaxed_day=True,
            now=datetime.now(tz=timezone.utc).astimezone().replace(hour=12, minute=0),
        )
        assert result.fired is False
        assert result.stage == "relaxed_day"

    def test_weekly_minimum_met_skips(self, tmp_path: Path) -> None:
        files = self._files(tmp_path)
        result = explain_lock_decision(
            **files,
            sick_history=SickHistory(),
            extended_early_bird=False,
            weekly_minimum_met=True,
            relaxed_day=False,
            now=datetime.now(tz=timezone.utc).astimezone().replace(hour=12, minute=0),
        )
        assert result.fired is False
        assert result.stage == "weekly_minimum_met"

    def test_full_lock_when_nothing_applies(self, tmp_path: Path) -> None:
        files = self._files(tmp_path)
        result = explain_lock_decision(
            **files,
            sick_history=SickHistory(),
            extended_early_bird=False,
            weekly_minimum_met=False,
            relaxed_day=False,
            now=datetime.now(tz=timezone.utc).astimezone().replace(hour=12, minute=0),
        )
        assert result.fired is True
        assert result.stage == "full_lock_pending_heat_check"
        assert result.auto_upgrade.via == "none"
        assert result.heat_skip_evaluated is False

    def test_defaults_now_to_current_time(self, tmp_path: Path) -> None:
        """Covers the ``now is None`` branch — just needs to not raise."""
        files = self._files(tmp_path)
        result = explain_lock_decision(
            **files,
            sick_history=SickHistory(),
            extended_early_bird=False,
            weekly_minimum_met=False,
            relaxed_day=False,
        )
        assert isinstance(result.fired, bool)
