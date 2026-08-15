"""Tests for sick-budget UI integration, finalize, debt-clear, and dialogs."""
# pylint: disable=protected-access

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker import _sick_tracker
from screen_locker._sick_tracker import SickHistory
from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# _ui_flows.py — branches added for sick budget + finalize
# ---------------------------------------------------------------------------


class TestShowRetryAndSickBudget:
    """Tests for budget-aware _show_retry_and_sick."""

    def test_shows_sick_button_when_budget_available(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Shows sick button when budget available."""
        locker = create_locker(mock_tk, tmp_path)
        with patch.object(_sick_tracker, "load_history", return_value=SickHistory()):
            locker._show_retry_and_sick("nope")
        button_texts = {
            call.args[1] for call in mock_tk.Button.call_args_list if len(call.args) > 1
        }
        # Buttons are created via the helper which sets text via kwarg "text".
        button_texts |= {
            call.kwargs.get("text") for call in mock_tk.Button.call_args_list
        }
        assert "I'm sick" in button_texts

    def test_hides_sick_button_when_budget_exhausted(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Hides sick button when budget exhausted."""
        locker = create_locker(mock_tk, tmp_path)
        full = SickHistory(sick_days=["2026-05-09"] * 99)
        with (
            patch.object(_sick_tracker, "load_history", return_value=full),
            patch.object(_sick_tracker, "is_budget_exhausted", return_value=True),
        ):
            locker._show_retry_and_sick("nope")
        button_texts: set[str] = set()
        for call in mock_tk.Button.call_args_list:
            button_texts.add(call.kwargs.get("text", ""))
        assert "I'm sick" not in button_texts


class TestProceedToSickCountdownLoadsHistory:
    """Covers the no-cache branch of _proceed_to_sick_countdown."""

    def test_loads_history_when_cache_missing(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Loads history when cache missing."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(locker, "clear_container", MagicMock())
        object.__setattr__(
            locker, "_sick_mode_used_today", MagicMock(return_value=False)
        )
        object.__setattr__(
            locker,
            "_adjust_shutdown_time_earlier",
            MagicMock(return_value=True),
        )
        with patch.object(
            _sick_tracker, "load_history", return_value=SickHistory()
        ) as mock_load:
            locker._proceed_to_sick_countdown()
        mock_load.assert_called_once()
        assert hasattr(locker, "_sick_history_cache")


class TestFinalizeSickDay:
    """Covers _finalize_sick_day branches including commitment penalty."""

    def test_marks_commitment_broken_and_writes_debt(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Marks commitment broken and writes debt."""
        locker = create_locker(mock_tk, tmp_path)
        locker.workout_data = {}
        history = SickHistory(commitments={"2026-05-10": True})
        locker._sick_history_cache = history
        object.__setattr__(locker, "unlock_screen", MagicMock())
        with (
            patch.object(_sick_tracker, "had_commitment_for_today", return_value=True),
            patch.object(_sick_tracker, "save_history", return_value=True),
        ):
            locker._finalize_sick_day()
        assert locker.workout_data["broke_commitment"] == "true"
        assert locker.workout_data["type"] == "sick_day"
        assert "debt" in locker.workout_data
        locker.unlock_screen.assert_called_once()

    def test_loads_history_when_cache_missing(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Loads history when cache missing."""
        locker = create_locker(mock_tk, tmp_path)
        locker.workout_data = {}
        object.__setattr__(locker, "unlock_screen", MagicMock())
        with (
            patch.object(
                _sick_tracker, "load_history", return_value=SickHistory()
            ) as mock_load,
            patch.object(_sick_tracker, "save_history", return_value=True),
        ):
            locker._finalize_sick_day()
        mock_load.assert_called_once()
        locker.unlock_screen.assert_called_once()


# ---------------------------------------------------------------------------
# screen_lock.py — _clear_debt_on_verified_workout branches
# ---------------------------------------------------------------------------


class TestClearDebtOnVerifiedWorkout:
    """Tests for _clear_debt_on_verified_workout."""

    def test_returns_none_when_not_phone_verified(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Returns none when not phone verified."""
        locker = create_locker(mock_tk, tmp_path)
        locker.workout_data = {"type": "sick_day"}
        assert locker._clear_debt_on_verified_workout() is None

    def test_returns_zero_when_no_debt(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Returns zero when no debt."""
        locker = create_locker(mock_tk, tmp_path)
        locker.workout_data = {"type": "phone_verified"}
        with patch.object(
            _sick_tracker, "load_history", return_value=SickHistory(debt=0)
        ):
            assert locker._clear_debt_on_verified_workout() == 0

    def test_decrements_when_debt_positive(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Decrements when debt positive."""
        locker = create_locker(mock_tk, tmp_path)
        locker.workout_data = {"type": "phone_verified"}
        history = SickHistory(debt=2)
        with (
            patch.object(_sick_tracker, "load_history", return_value=history),
            patch.object(_sick_tracker, "save_history", return_value=True) as mock_save,
        ):
            assert locker._clear_debt_on_verified_workout() == 1
        mock_save.assert_called_once()


class TestUnlockScreenCommitmentPrompt:
    """Tests for unlock_screen branches around commitment prompt + debt label."""

    def test_phone_verified_schedules_commitment_prompt(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Phone verified schedules commitment prompt."""
        locker = create_locker(mock_tk, tmp_path)
        locker.workout_data = {"type": "phone_verified"}
        locker.log_file = tmp_path / "log.json"
        object.__setattr__(locker, "save_workout_log", MagicMock())
        object.__setattr__(
            locker,
            "_try_adjust_shutdown_for_workout",
            MagicMock(return_value=False),
        )
        object.__setattr__(
            locker,
            "_clear_debt_on_verified_workout",
            MagicMock(return_value=0),
        )
        locker.unlock_screen()
        # The last after() call schedules the commitment prompt closure.
        last_call = locker.root.after.call_args_list[-1]
        assert last_call.args[0] == 1500

    def test_non_verified_schedules_close_directly(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Non verified schedules close directly."""
        locker = create_locker(mock_tk, tmp_path)
        locker.workout_data = {"type": "sick_day"}
        locker.log_file = tmp_path / "log.json"
        object.__setattr__(locker, "save_workout_log", MagicMock())
        object.__setattr__(
            locker,
            "_try_adjust_shutdown_for_workout",
            MagicMock(return_value=False),
        )
        object.__setattr__(
            locker,
            "_clear_debt_on_verified_workout",
            MagicMock(return_value=None),
        )
        locker.unlock_screen()
        # close() goes through root.after directly.
        locker.root.after.assert_called_with(1500, locker.close)

    def test_renders_debt_label_when_positive(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Renders debt label when positive."""
        locker = create_locker(mock_tk, tmp_path)
        locker.workout_data = {"type": "phone_verified"}
        locker.log_file = tmp_path / "log.json"
        object.__setattr__(locker, "save_workout_log", MagicMock())
        object.__setattr__(
            locker,
            "_try_adjust_shutdown_for_workout",
            MagicMock(return_value=True),
        )
        object.__setattr__(
            locker,
            "_clear_debt_on_verified_workout",
            MagicMock(return_value=2),
        )
        locker.unlock_screen()
        # _text was called via mock_tk.Label; just assert a Label call mentions debt.
        labels = [call.kwargs.get("text", "") for call in mock_tk.Label.call_args_list]
        assert any("Workout debt: 2" in t for t in labels)


# ---------------------------------------------------------------------------
# _sick_dialog.py — UI mixin
# ---------------------------------------------------------------------------
