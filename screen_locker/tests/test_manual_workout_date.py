"""Tests for the workout-date field and the future-dated submit path."""
# pylint: disable=protected-access

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker._day import today_str
from screen_locker._manual_schedule import ScheduleResult
from screen_locker.tests import test_manual_workout_dialog as dialog_tests
from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path

_MOD = "screen_locker._manual_workout_date"


def _plus(days: int) -> str:
    """Return the local ISO date ``days`` from today."""
    return (date.fromisoformat(today_str()) + timedelta(days=days)).isoformat()


def _locker(mock_tk: MagicMock, tmp_path: Path, day: str) -> MagicMock:
    """A locker whose form already holds ``day`` in its date variable."""
    locker = create_locker(mock_tk, tmp_path)
    locker._mw_vars = {"date": MagicMock()}
    locker._mw_vars["date"].get.return_value = day
    locker._mw_error_label = MagicMock()
    locker._show_manual_workout_scheduled = MagicMock()
    return locker


class TestBudgetClosed:
    """The button gate reads the local ledger only (no network)."""

    def test_open_with_an_empty_log(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        assert locker._mw_budget_closed() is False


class TestDateInRow:
    """The date entry rides in the sport row, prefilled with today."""

    def test_prefills_today_and_registers_the_var(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        locker._mw_vars = {}
        locker._mw_date_in_row(MagicMock())
        assert locker._mw_vars["date"] is mock_tk.StringVar.return_value
        assert mock_tk.StringVar.call_args.kwargs["value"] == today_str()


class TestHandledByDate:
    """Date and budget rules applied at submit."""

    def test_a_garbled_date_shows_the_error(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = _locker(mock_tk, tmp_path, "soon")
        assert locker._mw_handled_by_date(MagicMock()) is True
        locker._mw_error_label.config.assert_called_once()
        locker._show_manual_workout_scheduled.assert_not_called()

    def test_a_past_date_shows_the_error(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = _locker(mock_tk, tmp_path, _plus(-1))
        assert locker._mw_handled_by_date(MagicMock()) is True
        assert "past" in locker._mw_error_label.config.call_args.kwargs["text"]

    def test_today_over_budget_shows_the_error(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = _locker(mock_tk, tmp_path, today_str())
        with patch(f"{_MOD}.budget_error", return_value="budget full"):
            assert locker._mw_handled_by_date(MagicMock()) is True
        locker._mw_error_label.config.assert_called_once_with(text="budget full")

    def test_today_within_budget_is_left_to_the_host(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = _locker(mock_tk, tmp_path, today_str())
        with patch(f"{_MOD}.budget_error", return_value=None):
            assert locker._mw_handled_by_date(MagicMock()) is False
        locker._mw_error_label.config.assert_not_called()

    def test_a_refused_future_entry_shows_why(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = _locker(mock_tk, tmp_path, _plus(2))
        refused = ScheduleResult(scheduled=False, record_id="r", reason="no room")
        with patch(f"{_MOD}.schedule_future_workout", return_value=refused):
            assert locker._mw_handled_by_date(MagicMock()) is True
        locker._mw_error_label.config.assert_called_once_with(text="no room")
        locker._show_manual_workout_scheduled.assert_not_called()

    def test_a_scheduled_future_entry_shows_the_confirmation(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = _locker(mock_tk, tmp_path, _plus(2))
        draft = MagicMock()
        done = ScheduleResult(scheduled=True, record_id="r", reason="scheduled")
        with patch(f"{_MOD}.schedule_future_workout", return_value=done) as schedule:
            assert locker._mw_handled_by_date(draft) is True
        schedule.assert_called_once_with(locker.log_file, draft, _plus(2))
        locker._show_manual_workout_scheduled.assert_called_once_with("scheduled")
        locker._mw_error_label.config.assert_not_called()


class TestScheduledConfirmation:
    """The confirmation must go BACK, never through the unlocking save hook."""

    def test_ok_returns_via_the_cancelled_hook_and_never_unlocks(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        saved = MagicMock()
        cancelled = MagicMock()
        object.__setattr__(locker, "_on_manual_workout_saved", saved)
        object.__setattr__(locker, "_on_manual_workout_cancelled", cancelled)
        mock_tk.Button.reset_mock()

        locker._show_manual_workout_scheduled("scheduled for tomorrow")

        buttons = {
            c.kwargs.get("text"): c.kwargs for c in mock_tk.Button.call_args_list
        }
        assert set(buttons) == {"OK"}
        buttons["OK"]["command"]()
        cancelled.assert_called_once_with()
        saved.assert_not_called()
        texts = [c.kwargs.get("text", "") for c in mock_tk.Label.call_args_list]
        assert any("Workout Scheduled" in t for t in texts)
        assert any("scheduled for tomorrow" in t for t in texts)


class TestSubmitRoutesThroughTheDateRules:
    """The dialog's submit stops when the date rules handled the entry."""

    def test_a_handled_entry_never_reaches_the_host_save_hook(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = dialog_tests.TestSubmitManualWorkoutForm()._setup_locker(
            mock_tk, tmp_path
        )
        locker._mw_handled_by_date = MagicMock(return_value=True)
        locker._submit_manual_workout_form()
        locker._mw_handled_by_date.assert_called_once()
        locker._on_manual_workout_saved.assert_not_called()
