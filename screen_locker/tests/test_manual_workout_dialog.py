"""Tests for the manual-workout evidence-form dialog mixin."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker import _manual_workout
from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path

_CLOSED = "screen_locker._manual_workout_date.budget_closed_for_all_days"


class TestShowManualWorkoutForm:
    """Tests for _show_manual_workout_form."""

    def test_renders_form_when_budget_available(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """With budget left the form offers both SUBMIT and BACK."""
        locker = create_locker(mock_tk, tmp_path)
        with patch(_CLOSED, return_value=False):
            locker._show_manual_workout_form()
        button_texts = {c.kwargs.get("text") for c in mock_tk.Button.call_args_list}
        assert "SUBMIT" in button_texts
        assert "BACK" in button_texts

    def test_shows_exhausted_message_and_hides_submit(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """With no budget left an exhausted notice and BACK show, but no SUBMIT."""
        locker = create_locker(mock_tk, tmp_path)
        with patch(_CLOSED, return_value=True):
            locker._show_manual_workout_form()
        button_texts = {c.kwargs.get("text") for c in mock_tk.Button.call_args_list}
        assert "BACK" in button_texts
        assert "SUBMIT" not in button_texts
        text_calls = [c.kwargs.get("text", "") for c in mock_tk.Label.call_args_list]
        assert any("exhausted" in t for t in text_calls)


class TestSportToggle:
    """Tests for _on_mw_sport_changed and _current_mw_sport."""

    def test_selecting_other_shows_other_frame(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Choosing Other hides the table-tennis fields and shows the free-form ones."""
        locker = create_locker(mock_tk, tmp_path)
        locker._mw_tt_frame = MagicMock()
        locker._mw_other_frame = MagicMock()
        locker._mw_sport_var = MagicMock()
        locker._on_mw_sport_changed("Other")
        locker._mw_tt_frame.grid_remove.assert_called_once()
        locker._mw_other_frame.grid.assert_called_once_with()

    def test_selecting_table_tennis_shows_tt_frame(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Choosing Table tennis hides the free-form fields and shows the table-tennis ones."""
        locker = create_locker(mock_tk, tmp_path)
        locker._mw_tt_frame = MagicMock()
        locker._mw_other_frame = MagicMock()
        locker._mw_sport_var = MagicMock()
        locker._on_mw_sport_changed("Table tennis")
        locker._mw_other_frame.grid_remove.assert_called_once()
        locker._mw_tt_frame.grid.assert_called_once_with()

    def test_unknown_label_defaults_to_table_tennis(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """An unrecognised sport label falls back to table tennis."""
        locker = create_locker(mock_tk, tmp_path)
        locker._mw_tt_frame = MagicMock()
        locker._mw_other_frame = MagicMock()
        locker._mw_sport_var = MagicMock()
        locker._mw_sport_var.get.return_value = "not a real label"
        assert locker._current_mw_sport() == _manual_workout.SPORT_TABLE_TENNIS


class TestGridCursor:
    """Tests for the two-column grid cursor helper _mw_next_full_row."""

    def test_full_row_from_even_cursor_advances_by_a_row(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """A full-width item from a fresh cursor takes row 0 and the next takes row 1."""
        locker = create_locker(mock_tk, tmp_path)
        locker._mw_grid_counters = {}
        parent = object()
        # Fresh (even) cursor: reserves row 0, then row 1 on the next call.
        assert not locker._mw_next_full_row(parent)
        assert locker._mw_next_full_row(parent) == 1

    def test_full_row_from_odd_cursor_bumps_to_next_row(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """A full-width item after a lone half-width cell moves to a fresh row."""
        locker = create_locker(mock_tk, tmp_path)
        parent = object()
        # An odd cursor (a half-width cell already placed on the left) must be
        # bumped to a fresh row before a full-width item is placed.
        locker._mw_grid_counters = {id(parent): 1}
        assert locker._mw_next_full_row(parent) == 1


class TestInitialKeyboardFocus:
    """Exactly one field takes focus when a typed-input screen is built."""

    def test_manual_workout_form_focuses_one_entry(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Building the form gives keyboard focus to exactly one entry."""
        locker = create_locker(mock_tk, tmp_path)
        with patch(_CLOSED, return_value=False):
            locker._show_manual_workout_form()
        focused = mock_tk.Entry.return_value.focus_set.call_count
        assert focused == 1, f"expected exactly one focused entry, got {focused}"
