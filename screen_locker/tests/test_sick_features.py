"""Tests for sick-budget UI integration, finalize, debt-clear, and dialogs."""
# pylint: disable=protected-access

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from python_pkg.screen_locker import _sick_tracker
from python_pkg.screen_locker._sick_tracker import SickHistory
from python_pkg.screen_locker.tests.conftest import create_locker

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
        locker = create_locker(mock_tk, tmp_path)
        locker.workout_data = {"type": "sick_day"}
        assert locker._clear_debt_on_verified_workout() is None

    def test_returns_zero_when_no_debt(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        locker.workout_data = {"type": "phone_verified"}
        with patch.object(
            _sick_tracker, "load_history", return_value=SickHistory(debt=0)
        ):
            assert locker._clear_debt_on_verified_workout() == 0

    def test_decrements_when_debt_positive(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
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


class TestShowSickJustification:
    """Tests for the structured sick justification dialog."""

    def test_renders_form_without_commitment(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        with patch.object(_sick_tracker, "load_history", return_value=SickHistory()):
            locker._show_sick_justification()
        assert locker._sick_history_cache.sick_days == []
        assert hasattr(locker, "_sick_submit_button")
        # Submit button starts enabled (no commitment).
        # config(state="disabled") only called for commitment path.
        for call in locker._sick_submit_button.config.call_args_list:
            assert call.kwargs.get("state") != "disabled"

    def test_renders_form_with_commitment_disables_submit(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        history = SickHistory(commitments={"2026-05-10": True})
        with (
            patch.object(_sick_tracker, "load_history", return_value=history),
            patch.object(_sick_tracker, "had_commitment_for_today", return_value=True),
        ):
            locker._show_sick_justification()
        # Submit button was disabled and forced-delay started.
        states = [
            call.kwargs.get("state")
            for call in locker._sick_submit_button.config.call_args_list
        ]
        assert "disabled" in states

    def test_renders_recent_history_when_present(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        history = SickHistory(
            justifications=[
                {"date": "2026-05-01", "symptom": "fever", "severity": 7},
            ],
        )
        with patch.object(_sick_tracker, "load_history", return_value=history):
            locker._show_sick_justification()
        labels = [call.kwargs.get("text", "") for call in mock_tk.Label.call_args_list]
        assert any("Recent sick days" in t for t in labels)


class TestUpdateCommitmentForcedDelay:
    """Tests for _update_commitment_forced_delay."""

    def test_ticks_down(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        locker._sick_submit_button = MagicMock()
        locker._commitment_forced_remaining = 3
        locker._update_commitment_forced_delay()
        assert locker._commitment_forced_remaining == 2
        locker.root.after.assert_called()

    def test_enables_when_done(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        locker._sick_submit_button = MagicMock()
        locker._commitment_forced_remaining = 0
        locker._update_commitment_forced_delay()
        locker._sick_submit_button.config.assert_called_with(
            text="SUBMIT", state="normal"
        )


class TestSubmitSickJustification:
    """Tests for _submit_sick_justification validation + persistence."""

    def _setup_locker(
        self,
        mock_tk: MagicMock,
        tmp_path: Path,
        *,
        fields: dict[str, object] | None = None,
    ) -> object:
        defaults: dict[str, object] = {
            "symptom": "fever",
            "onset": "last night",
            "severity": 7,
            "text": "x" * 200,
        }
        if fields:
            defaults.update(fields)
        locker = create_locker(mock_tk, tmp_path)
        locker._sick_history_cache = SickHistory()
        locker._sick_symptom_var = MagicMock()
        locker._sick_symptom_var.get.return_value = defaults["symptom"]
        locker._sick_onset_var = MagicMock()
        locker._sick_onset_var.get.return_value = defaults["onset"]
        locker._sick_severity_var = MagicMock()
        locker._sick_severity_var.get.return_value = defaults["severity"]
        locker._sick_text_widget = MagicMock()
        locker._sick_text_widget.get.return_value = defaults["text"]
        locker._sick_error_label = MagicMock()
        object.__setattr__(locker, "_proceed_to_sick_countdown", MagicMock())
        return locker

    def test_validation_failure_displays_error(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = self._setup_locker(mock_tk, tmp_path, fields={"symptom": ""})
        locker._submit_sick_justification()
        locker._sick_error_label.config.assert_called_once()
        locker._proceed_to_sick_countdown.assert_not_called()

    def test_severity_tcl_error_treated_as_invalid(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = self._setup_locker(mock_tk, tmp_path)
        locker._sick_severity_var.get.side_effect = ValueError("bad")
        locker._submit_sick_justification()
        locker._sick_error_label.config.assert_called_once()

    def test_save_failure_displays_error(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = self._setup_locker(mock_tk, tmp_path)
        with patch.object(_sick_tracker, "save_history", return_value=False):
            locker._submit_sick_justification()
        locker._sick_error_label.config.assert_called_once()
        locker._proceed_to_sick_countdown.assert_not_called()

    def test_success_proceeds_to_countdown(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = self._setup_locker(mock_tk, tmp_path)
        with patch.object(_sick_tracker, "save_history", return_value=True):
            locker._submit_sick_justification()
        locker._proceed_to_sick_countdown.assert_called_once()


class TestCommitmentPrompt:
    """Tests for _show_commitment_prompt + _tick_commitment_timeout + answer."""

    def test_show_prompt_renders_buttons(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        on_done = MagicMock()
        locker._show_commitment_prompt(on_done=on_done)
        assert locker._commitment_done_fn is on_done
        assert locker._commitment_remaining > 0

    def test_tick_decrements(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        locker._commitment_remaining = 2
        locker._commitment_timer_label = MagicMock()
        locker._tick_commitment_timeout()
        assert locker._commitment_remaining == 1
        locker.root.after.assert_called()

    def test_tick_zero_auto_answers_no(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        on_done = MagicMock()
        locker._commitment_done_fn = on_done
        locker._commitment_remaining = 0
        locker._commitment_timer_label = MagicMock()
        locker._tick_commitment_timeout()
        on_done.assert_called_once()

    def test_answer_yes_persists_commitment(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        on_done = MagicMock()
        locker._commitment_done_fn = on_done
        history = SickHistory()
        with (
            patch.object(_sick_tracker, "load_history", return_value=history),
            patch.object(_sick_tracker, "save_history", return_value=True) as mock_save,
        ):
            locker._answer_commitment(commit=True)
        mock_save.assert_called_once()
        on_done.assert_called_once()
        assert locker._commitment_done_fn is None

    def test_answer_no_skips_persistence(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        on_done = MagicMock()
        locker._commitment_done_fn = on_done
        with patch.object(_sick_tracker, "save_history") as mock_save:
            locker._answer_commitment(commit=False)
        mock_save.assert_not_called()
        on_done.assert_called_once()

    def test_answer_with_no_done_fn_is_safe(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        # No _commitment_done_fn attribute set.
        locker._answer_commitment(commit=False)


class TestDisablePaste:
    """Tests for the _disable_paste helper."""

    def test_swallows_tcl_error(self) -> None:
        from python_pkg.screen_locker._sick_dialog import _disable_paste

        widget = MagicMock()
        import tkinter as tk

        widget.bind.side_effect = tk.TclError("nope")
        # Should not raise.
        _disable_paste(widget)
