"""Tests for UI flows coverage gaps (part 2)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestUpdateSickCountdownAtZero:
    """Tests for _update_sick_countdown at zero remaining."""

    def test_records_sick_day_and_unlocks_at_zero(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test countdown at zero records sick day and calls unlock."""
        locker = create_locker(mock_tk, tmp_path)
        locker.sick_remaining_time = 0
        locker.sick_countdown_label = MagicMock()
        locker.workout_data = {}
        locker.log_file = tmp_path / "log.json"
        object.__setattr__(locker, "unlock_screen", MagicMock())

        locker._update_sick_countdown()

        assert locker.workout_data["type"] == "sick_day"
        assert locker.workout_data["note"] == "Sick day - shutdown moved earlier"
        locker.unlock_screen.assert_called_once()


class TestStartRunnerupFallback:
    """Tests for _start_runnerup_fallback (lines 114-121)."""

    def test_submits_verify_and_stores_future(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Fallback sets up future and on_failure, then calls _poll_runnerup_fallback."""
        locker = create_locker(mock_tk, tmp_path)
        on_failure = MagicMock()

        mock_future = MagicMock()
        mock_executor = MagicMock()
        mock_executor.submit.return_value = mock_future

        object.__setattr__(
            locker,
            "_verify_runnerup_workout",
            MagicMock(return_value=("not_verified", "no")),
        )

        with (
            patch(
                "screen_locker._ui_flows.ThreadPoolExecutor",
                return_value=mock_executor,
            ),
            patch.object(locker, "_poll_runnerup_fallback"),
        ):
            locker._start_runnerup_fallback(on_failure)

        assert locker._runnerup_future is mock_future
        assert locker._runnerup_on_failure is on_failure


class TestPollRunnerupFallback:
    """Tests for _poll_runnerup_fallback (lines 125-139)."""

    def test_routes_to_unlock_when_verified(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Future done + verified → sets workout_data and schedules unlock (lines 127-135)."""
        locker = create_locker(mock_tk, tmp_path)
        mock_future = MagicMock()
        mock_future.done.return_value = True
        mock_future.result.return_value = ("verified", "Running: 6.0 km in 40 min")
        locker._runnerup_future = mock_future
        locker._runnerup_on_failure = MagicMock()
        locker.workout_data = {}
        object.__setattr__(locker, "unlock_screen", MagicMock())

        locker._poll_runnerup_fallback()

        assert locker.workout_data["type"] == "runnerup_verified"
        assert locker.workout_data["source"] == "Running: 6.0 km in 40 min"
        locker.root.after.assert_called()

    def test_calls_on_failure_when_not_verified(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Future done + non-verified → on_failure callback invoked (lines 136-137)."""
        locker = create_locker(mock_tk, tmp_path)
        mock_future = MagicMock()
        mock_future.done.return_value = True
        mock_future.result.return_value = ("no_phone", "no phone connected")
        on_failure = MagicMock()
        locker._runnerup_future = mock_future
        locker._runnerup_on_failure = on_failure

        locker._poll_runnerup_fallback()

        on_failure.assert_called_once()

    def test_schedules_retry_when_future_not_done(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Future still running → schedule next poll after 500 ms (lines 138-139)."""
        locker = create_locker(mock_tk, tmp_path)
        mock_future = MagicMock()
        mock_future.done.return_value = False
        locker._runnerup_future = mock_future

        locker._poll_runnerup_fallback()

        locker.root.after.assert_called_with(500, locker._poll_runnerup_fallback)

    def test_schedules_retry_when_future_is_none(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """None future (not started yet) → poll again in 500 ms."""
        locker = create_locker(mock_tk, tmp_path)
        locker._runnerup_future = None

        locker._poll_runnerup_fallback()

        locker.root.after.assert_called_with(500, locker._poll_runnerup_fallback)
