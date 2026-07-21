"""Tests for manual-workout integration in status_view.py."""
# pylint: disable=protected-access

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker import _manual_workout
from screen_locker._workout_credit import WorkoutCreditResult
from screen_locker.tests._status_view_helpers import (
    _button_texts,
    _make_window,
    _manual_workout_budget,
    _snapshot,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestSectionManualWorkoutBudget:
    """Tests for StatusWindow._section_manual_workout_budget."""

    def test_exhausted_uses_warning_color(self, mock_tk: MagicMock) -> None:
        snap = _snapshot(
            manual_workout_budget=_manual_workout_budget(used_7d=2, exhausted=True)
        )
        window = _make_window(mock_tk, snap)
        calls = [
            c
            for c in mock_tk.Label.call_args_list
            if "week" in c.kwargs.get("text", "")
        ]
        assert any(c.kwargs.get("fg") == window._colors.danger for c in calls)

    def test_not_exhausted_uses_normal_color(self, mock_tk: MagicMock) -> None:
        snap = _snapshot(
            manual_workout_budget=_manual_workout_budget(used_7d=0, exhausted=False)
        )
        window = _make_window(mock_tk, snap)
        calls = [
            c
            for c in mock_tk.Label.call_args_list
            if "week" in c.kwargs.get("text", "")
        ]
        assert any(c.kwargs.get("fg") == window._colors.muted for c in calls)


class TestManualWorkoutButtonVisibility:
    """Tests for the "Log Manual Workout" button in StatusWindow.render."""

    def test_shown_when_budget_available(
        self, mock_tk: MagicMock, temp_log_file: Path
    ) -> None:
        _make_window(mock_tk, _snapshot(), log_file=temp_log_file)
        assert "Log Manual Workout" in _button_texts(mock_tk)

    def test_hidden_when_budget_exhausted(
        self, mock_tk: MagicMock, temp_log_file: Path
    ) -> None:
        with patch.object(_manual_workout, "is_budget_exhausted", return_value=True):
            _make_window(mock_tk, _snapshot(), log_file=temp_log_file)
        assert "Log Manual Workout" not in _button_texts(mock_tk)


class TestOnManualWorkoutSaved:
    """Tests for StatusWindow._on_manual_workout_saved."""

    def _make_fake_verifier(self, credit: WorkoutCreditResult) -> MagicMock:
        fake_verifier = MagicMock()
        fake_verifier._apply_workout_credit = MagicMock(return_value=credit)
        return fake_verifier

    def test_saves_via_bare_verifier_and_shows_shutdown_message(
        self, mock_tk: MagicMock, temp_log_file: Path
    ) -> None:
        credit = WorkoutCreditResult(
            shutdown_adjusted=True,
            new_debt=None,
            extra_bonus_delta=0,
            weekly_count=2,
            already_counted_today=False,
        )
        fake_verifier = self._make_fake_verifier(credit)
        window = _make_window(
            mock_tk,
            _snapshot(),
            log_file=temp_log_file,
            verifier_factory=lambda _log_file: fake_verifier,
        )
        entry = {"type": "manual_workout", "source": "table tennis at Solec"}
        with patch("screen_locker.status_view.gather_status", return_value=_snapshot()):
            window._on_manual_workout_saved(entry)

        assert fake_verifier.workout_data == entry
        fake_verifier._apply_workout_credit.assert_called_once()
        message = window._credit_message
        assert message is not None
        assert "table tennis at Solec" in message
        assert "Shutdown time +2h later!" in message

    def test_shows_debt_and_extra_bonus_lines(
        self, mock_tk: MagicMock, temp_log_file: Path
    ) -> None:
        credit = WorkoutCreditResult(
            shutdown_adjusted=False,
            new_debt=1,
            extra_bonus_delta=1,
            weekly_count=5,
            already_counted_today=False,
        )
        fake_verifier = self._make_fake_verifier(credit)
        window = _make_window(
            mock_tk,
            _snapshot(),
            log_file=temp_log_file,
            verifier_factory=lambda _log_file: fake_verifier,
        )
        with patch("screen_locker.status_view.gather_status", return_value=_snapshot()):
            window._on_manual_workout_saved({"type": "manual_workout", "source": "x"})

        message = window._credit_message
        assert message is not None
        assert "Extra workout today! +1h tonight" in message
        assert "Workout debt: 1" in message

    def test_already_counted_today_shows_no_extra_credit_note(
        self, mock_tk: MagicMock, temp_log_file: Path
    ) -> None:
        credit = WorkoutCreditResult(
            shutdown_adjusted=False,
            new_debt=None,
            extra_bonus_delta=0,
            weekly_count=3,
            already_counted_today=True,
        )
        fake_verifier = self._make_fake_verifier(credit)
        window = _make_window(
            mock_tk,
            _snapshot(),
            log_file=temp_log_file,
            verifier_factory=lambda _log_file: fake_verifier,
        )
        with patch("screen_locker.status_view.gather_status", return_value=_snapshot()):
            window._on_manual_workout_saved({"type": "manual_workout", "source": "x"})

        message = window._credit_message
        assert message is not None
        assert "no additional credit" in message
        assert "Shutdown time" not in message


class TestOnManualWorkoutCancelled:
    """Tests for StatusWindow._on_manual_workout_cancelled."""

    def test_rerenders_current_snapshot(
        self, mock_tk: MagicMock, temp_log_file: Path
    ) -> None:
        window = _make_window(mock_tk, _snapshot(), log_file=temp_log_file)
        with patch(
            "screen_locker.status_view.gather_status", return_value=_snapshot()
        ) as mock_gather:
            window._on_manual_workout_cancelled()
        mock_gather.assert_called_once()


class TestManualWorkoutSavedMessageDisplay:
    """Tests for the saved-message line in StatusWindow.render."""

    def test_shown_when_present(self, mock_tk: MagicMock, temp_log_file: Path) -> None:
        window = _make_window(mock_tk, _snapshot(), log_file=temp_log_file)
        window._credit_message = "Manual workout logged: test"
        window.render(_snapshot())
        texts = [c.kwargs.get("text", "") for c in mock_tk.Label.call_args_list]
        assert any("Manual workout logged: test" in t for t in texts)

    def test_absent_when_none(self, mock_tk: MagicMock, temp_log_file: Path) -> None:
        _make_window(mock_tk, _snapshot(), log_file=temp_log_file)
        texts = [c.kwargs.get("text", "") for c in mock_tk.Label.call_args_list]
        assert not any("Manual workout logged" in t for t in texts)
