"""Slot-based live workout credit: one slot pays once, a new slot pays again.

The two StrongLifts ingestion paths of ONE session used to earn +2h and then
+1h (2026-10-09). These tests drive the real shutdown arithmetic over a fake
config so the minute figures, not just the branch taken, are pinned.
"""
# pylint: disable=protected-access

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker import _credit_slot
from screen_locker._credit_slot import CreditSlot, credit_slot, locked_shutdown_state
from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from screen_locker._workout_credit import WorkoutCreditResult
    from screen_locker.screen_lock import ScreenLocker

_START = (1200, 1200, 300)  # 20:00 / 20:00 / 05:00 -- well under the ceiling


def _entry(wtype: str) -> dict[str, dict[str, str]]:
    return {"workout_data": {"type": wtype}}


class TestCreditSlot:
    """credit_slot classifies the new entry against the day before it."""

    def test_first_counted_entry_of_the_day(self) -> None:
        """An empty day: the first counted workout opens the first slot."""
        assert credit_slot([], {"type": "phone_verified"}) is CreditSlot.FIRST

    def test_second_stronglifts_path_shares_the_slot(self) -> None:
        """pc_workout_verified then phone_verified: one session, one slot."""
        prior = [_entry("pc_workout_verified")]
        assert credit_slot(prior, {"type": "phone_verified"}) is CreditSlot.OCCUPIED

    def test_a_run_after_stronglifts_is_a_further_slot(self) -> None:
        """A RunnerUp run is a separate session from the StrongLifts one."""
        prior = [_entry("phone_verified")]
        assert credit_slot(prior, {"type": "runnerup_verified"}) is CreditSlot.FURTHER

    def test_uncounted_type_earns_nothing(self) -> None:
        """early_bird is not a counted workout type at all."""
        assert credit_slot([], {"type": "early_bird"}) is CreditSlot.NONE

    def test_non_dict_prior_entries_are_ignored(self) -> None:
        """A corrupt prior entry neither crashes nor occupies a slot."""
        prior: list = ["garbage", None]
        assert credit_slot(prior, {"type": "phone_verified"}) is CreditSlot.FIRST


class TestLockedShutdownState:
    """The credit takes bonus_lock, and degrades loudly when it cannot."""

    def test_lock_failure_warns_and_still_runs_the_body(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """An unlockable state file must not drop the credit -- only warn."""
        ran: list[bool] = []
        with (
            patch.object(_credit_slot, "bonus_lock", side_effect=OSError("ro fs")),
            caplog.at_level(logging.WARNING, logger=_credit_slot.__name__),
            locked_shutdown_state(tmp_path / "base.json"),
        ):
            ran.append(True)
        assert ran == [True]
        assert any(
            r.levelno == logging.WARNING and "ro fs" in r.getMessage()
            for r in caplog.records
        )

    def test_lock_success_runs_the_body(self, tmp_path: Path) -> None:
        """The happy path holds the real lock around the body."""
        ran: list[bool] = []
        with locked_shutdown_state(tmp_path / "base.json"):
            ran.append(True)
        assert ran == [True]


def _wired_locker(mock_tk: MagicMock, tmp_path: Path, wtype: str) -> ScreenLocker:
    """A locker over an in-memory shutdown config, real adjust arithmetic."""
    locker = create_locker(mock_tk, tmp_path)
    locker.workout_data = {"type": wtype}
    config = {"value": _START}

    def write(mw: int, ts: int, morning: int, *, restore: bool) -> bool:
        assert restore
        config["value"] = (mw, ts, morning)
        return True

    object.__setattr__(
        locker, "_read_shutdown_config", MagicMock(side_effect=lambda: config["value"])
    )
    object.__setattr__(locker, "_write_shutdown_config", MagicMock(side_effect=write))
    object.__setattr__(
        locker, "_clear_debt_on_verified_workout", MagicMock(return_value=None)
    )
    return locker


def _credit(locker: ScreenLocker, prior: list) -> tuple[WorkoutCreditResult, MagicMock]:
    with (
        patch("screen_locker._shutdown.plan_absorb", side_effect=lambda m: (m, 0)),
        patch("screen_locker._shutdown.save_lift"),
        patch("screen_locker._workout_credit.is_rest_day", return_value=False),
        patch("screen_locker._workout_credit.count_weekly_workouts", return_value=3),
        patch(
            "screen_locker._workout_credit._credit_notify.notify_workout_credit"
        ) as notify,
    ):
        result = locker._apply_credit_for_written_entry(prior)
    return result, notify


class TestSlotCreditMinutes:
    """The minutes each slot class actually moves the shutdown."""

    def test_first_slot_earns_two_hours(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """First counted workout of the day: shutdown +120 min, notified."""
        locker = _wired_locker(mock_tk, tmp_path, "phone_verified")
        result, notify = _credit(locker, [])
        assert result.shutdown_adjusted is True
        assert locker._read_shutdown_config() == (1320, 1320, 300)
        notify.assert_called_once_with(_START, (1320, 1320, 300), locker.log_file)

    def test_distinct_slot_earns_one_hour(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """A run after StrongLifts: +60 min, reported as the extra delta."""
        locker = _wired_locker(mock_tk, tmp_path, "runnerup_verified")
        result, notify = _credit(locker, [_entry("phone_verified")])
        assert result.extra_bonus_delta == 60
        assert locker._read_shutdown_config() == (1260, 1260, 300)
        notify.assert_called_once()

    def test_same_slot_earns_nothing_and_warns(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """The second StrongLifts path: 0 min, a WARNING, no notification."""
        locker = _wired_locker(mock_tk, tmp_path, "phone_verified")
        with caplog.at_level(logging.WARNING, logger="screen_locker._workout_credit"):
            result, notify = _credit(locker, [_entry("pc_workout_verified")])
        assert result.already_counted_today is True
        assert result.extra_bonus_delta == 0
        assert locker._read_shutdown_config() == _START  # untouched
        notify.assert_not_called()
        assert any(
            r.levelno == logging.WARNING and "shares its credit slot" in r.getMessage()
            for r in caplog.records
        )
