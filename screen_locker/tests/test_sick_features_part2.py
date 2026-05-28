"""Tests for sick justification submission, commitment prompt, and paste disable."""
# pylint: disable=protected-access

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker import _sick_tracker
from screen_locker._sick_tracker import SickHistory
from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


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
        import tkinter as tk

        from screen_locker._sick_dialog import _disable_paste

        widget = MagicMock()
        widget.bind.side_effect = tk.TclError("nope")
        # Should not raise.
        _disable_paste(widget)
