"""Tests for submitting the manual-workout evidence form."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from screen_locker._day import today_str
from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestSubmitManualWorkoutForm:
    """Tests for _submit_manual_workout_form."""

    def _setup_locker(
        self,
        mock_tk: MagicMock,
        tmp_path: Path,
        *,
        sport_label: str = "Table tennis",
        fields: dict[str, object] | None = None,
    ) -> object:
        defaults: dict[str, object] = {
            "date": today_str(),
            "start_time": "12:00",
            "end_time": "14:00",
            "location_name": "Osrodek Solec",
            "transport_method": "bike",
            "cost": "60 PLN",
            "reservation_phone": "",
            "techniques_practiced": "",
            "warm_up_minutes": "",
            "pain_or_injury": "none",
            "racket": "pro spin",
            "balls": "nittaku",
            "activity_type_other": "squash",
            "went_well": "x" * 30,
            "to_improve": "y" * 30,
            "overall_feeling": "z" * 30,
            "activity_details": "q" * 45,
        }
        if fields:
            defaults.update(fields)

        locker = create_locker(mock_tk, tmp_path)
        locker._mw_sport_var = MagicMock()
        locker._mw_sport_var.get.return_value = sport_label
        locker._mw_rpe_var = MagicMock()
        locker._mw_rpe_var.get.return_value = 6

        locker._mw_vars = {}
        for key in (
            "start_time",
            "end_time",
            "location_name",
            "transport_method",
            "cost",
            "reservation_phone",
            "techniques_practiced",
            "warm_up_minutes",
            "pain_or_injury",
            "racket",
            "balls",
            "activity_type_other",
            "equipment",
            "date",
        ):
            var = MagicMock()
            var.get.return_value = defaults.get(key, "")
            locker._mw_vars[key] = var

        locker._mw_int_vars = {}
        for key, default_val in (
            ("matches_won", 1),
            ("matches_lost", 4),
            ("sets_won", 2),
            ("sets_lost", 9),
        ):
            var = MagicMock()
            var.get.return_value = defaults.get(key, default_val)
            locker._mw_int_vars[key] = var

        locker._mw_text_widgets = {}
        for key in ("went_well", "to_improve", "overall_feeling", "activity_details"):
            widget = MagicMock()
            widget.get.return_value = defaults[key]
            locker._mw_text_widgets[key] = widget

        locker._mw_error_label = MagicMock()
        object.__setattr__(locker, "_on_manual_workout_saved", MagicMock())
        return locker

    def test_valid_table_tennis_calls_saved_hook(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """A valid table-tennis form is passed to the saved hook with no error shown."""
        locker = self._setup_locker(mock_tk, tmp_path, sport_label="Table tennis")
        locker._submit_manual_workout_form()
        locker._on_manual_workout_saved.assert_called_once()
        entry = locker._on_manual_workout_saved.call_args.args[0]
        assert entry["sport"] == "table_tennis"
        assert entry["matches_lost"] == 4
        locker._mw_error_label.config.assert_not_called()

    def test_valid_other_sport_calls_saved_hook(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """A valid Other-sport form is saved with its free-form activity type."""
        locker = self._setup_locker(mock_tk, tmp_path, sport_label="Other")
        locker._submit_manual_workout_form()
        locker._on_manual_workout_saved.assert_called_once()
        entry = locker._on_manual_workout_saved.call_args.args[0]
        assert entry["sport"] == "other"
        assert entry["activity_type"] == "squash"

    def test_validation_failure_shows_error_and_skips_hook(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """A validation failure shows the error and does not save."""
        locker = self._setup_locker(mock_tk, tmp_path, fields={"location_name": "   "})
        locker._submit_manual_workout_form()
        locker._mw_error_label.config.assert_called_once()
        locker._on_manual_workout_saved.assert_not_called()

    def test_rpe_value_error_treated_as_invalid(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """An unreadable RPE value is reported as an error and nothing is saved."""
        locker = self._setup_locker(mock_tk, tmp_path)
        locker._mw_rpe_var.get.side_effect = ValueError("bad")
        locker._submit_manual_workout_form()
        locker._mw_error_label.config.assert_called_once()
        locker._on_manual_workout_saved.assert_not_called()

    def test_int_field_value_error_treated_as_zero(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """An unreadable match count counts as zero, tripping the zero-matches error."""
        locker = self._setup_locker(mock_tk, tmp_path)
        locker._mw_int_vars["matches_won"].get.side_effect = ValueError("bad")
        locker._mw_int_vars["matches_lost"].get.return_value = 0
        locker._submit_manual_workout_form()
        # matches_won=0 (from the ValueError fallback) and matches_lost=0
        # -> "zero matches played" validation error.
        locker._mw_error_label.config.assert_called_once()
        locker._on_manual_workout_saved.assert_not_called()
