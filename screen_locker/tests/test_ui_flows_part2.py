"""Tests for UI flows coverage gaps (part 2)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from python_pkg.screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestUpdateSickCountdownAtZero:
    """Tests for _update_sick_countdown at zero remaining."""

    def test_records_sick_day_and_unlocks_at_zero(
        self,
        mock_tk: MagicMock,
        _mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test countdown at zero records sick day and calls unlock."""
        locker = create_locker(mock_tk, tmp_path)
        locker.sick_remaining_time = 0
        locker.sick_countdown_label = MagicMock()
        locker.workout_data = {}
        locker.log_file = tmp_path / "workout_log.json"
        object.__setattr__(locker, "unlock_screen", MagicMock())

        locker._update_sick_countdown()

        assert locker.workout_data["type"] == "sick_day"
        assert locker.workout_data["note"] == "Sick day - shutdown moved earlier"
        locker.unlock_screen.assert_called_once()
