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


class TestShowSickJustification:
    """Tests for the structured sick justification dialog."""

    def test_renders_form_without_commitment(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Renders form without commitment."""
        locker = create_locker(mock_tk, tmp_path)
        with patch.object(_sick_tracker, "load_history", return_value=SickHistory()):
            locker._show_sick_justification()
        assert locker._sick_history_cache.sick_days == []
        assert hasattr(locker, "_sick_submit_button")
        # Submit button starts enabled (no commitment).
        # config(state="disabled") only called for commitment path.
        for call in locker._sick_submit_button.first.configure.call_args_list:
            assert call.kwargs.get("state") != "disabled"

    def test_renders_form_with_commitment_disables_submit(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Renders form with commitment disables submit."""
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
            for call in locker._sick_submit_button.first.configure.call_args_list
        ]
        assert "disabled" in states

    def test_renders_recent_history_when_present(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Renders recent history when present."""
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
        """Ticks down."""
        locker = create_locker(mock_tk, tmp_path)
        locker._sick_submit_button = MagicMock()
        locker._commitment_forced_remaining = 3
        locker._update_commitment_forced_delay()
        assert locker._commitment_forced_remaining == 2
        locker.root.after.assert_called()

    def test_enables_when_done(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Enables when done."""
        locker = create_locker(mock_tk, tmp_path)
        locker._sick_submit_button = MagicMock()
        locker._commitment_forced_remaining = 0
        locker._update_commitment_forced_delay()
        locker._sick_submit_button.config.assert_called_with(
            text="SUBMIT", state="normal"
        )
