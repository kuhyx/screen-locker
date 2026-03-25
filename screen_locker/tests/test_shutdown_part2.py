"""Tests for shutdown schedule adjustment coverage gaps (part 2)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from python_pkg.screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestApplyEarlierShutdown:
    """Tests for _apply_earlier_shutdown method."""

    def test_returns_false_when_no_config(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns False when config can't be read."""
        locker = create_locker(mock_tk, tmp_path)
        with patch.object(locker, "_read_shutdown_config", return_value=None):
            assert locker._apply_earlier_shutdown("2026-03-21") is False

    def test_returns_false_when_save_state_fails(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns False when saving state fails."""
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch.object(locker, "_read_shutdown_config", return_value=(21, 20, 8)),
            patch.object(locker, "_save_sick_day_state", return_value=False),
        ):
            assert locker._apply_earlier_shutdown("2026-03-21") is False

    def test_success_applies_earlier_hours(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test successful application of earlier shutdown hours."""
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch.object(locker, "_read_shutdown_config", return_value=(21, 20, 8)),
            patch.object(locker, "_save_sick_day_state", return_value=True),
            patch.object(
                locker, "_write_shutdown_config", return_value=True
            ) as mock_write,
        ):
            result = locker._apply_earlier_shutdown("2026-03-21")
        assert result is True
        mock_write.assert_called_once_with(20, 19, 8)

    def test_clamps_to_minimum_18(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test hours are clamped to minimum of 18."""
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch.object(locker, "_read_shutdown_config", return_value=(18, 18, 8)),
            patch.object(locker, "_save_sick_day_state", return_value=True),
            patch.object(
                locker, "_write_shutdown_config", return_value=True
            ) as mock_write,
        ):
            locker._apply_earlier_shutdown("2026-03-21")
        mock_write.assert_called_once_with(18, 18, 8)


class TestAdjustShutdownTimeEarlier:
    """Tests for _adjust_shutdown_time_earlier method."""

    def test_returns_false_when_sick_mode_used_today(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns False when sick mode already used today."""
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch.object(locker, "_restore_original_config_if_needed"),
            patch.object(locker, "_sick_mode_used_today", return_value=True),
        ):
            assert locker._adjust_shutdown_time_earlier() is False

    def test_success(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test successful adjustment."""
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch.object(locker, "_restore_original_config_if_needed"),
            patch.object(locker, "_sick_mode_used_today", return_value=False),
            patch.object(locker, "_apply_earlier_shutdown", return_value=True),
        ):
            assert locker._adjust_shutdown_time_earlier() is True

    def test_handles_oserror(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test handles OSError during apply."""
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch.object(locker, "_restore_original_config_if_needed"),
            patch.object(locker, "_sick_mode_used_today", return_value=False),
            patch.object(
                locker,
                "_apply_earlier_shutdown",
                side_effect=OSError("fail"),
            ),
        ):
            assert locker._adjust_shutdown_time_earlier() is False

    def test_handles_value_error(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test handles ValueError during apply."""
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch.object(locker, "_restore_original_config_if_needed"),
            patch.object(locker, "_sick_mode_used_today", return_value=False),
            patch.object(
                locker,
                "_apply_earlier_shutdown",
                side_effect=ValueError("bad"),
            ),
        ):
            assert locker._adjust_shutdown_time_earlier() is False


class TestAdjustShutdownTimeLater:
    """Tests for _adjust_shutdown_time_later method."""

    def test_returns_false_when_no_config(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns False when config is missing."""
        locker = create_locker(mock_tk, tmp_path)
        with patch.object(locker, "_read_shutdown_config", return_value=None):
            assert locker._adjust_shutdown_time_later() is False

    def test_success_applies_later_hours(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test successful later adjustment with restore flag."""
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch.object(locker, "_read_shutdown_config", return_value=(20, 19, 8)),
            patch.object(
                locker, "_write_shutdown_config", return_value=True
            ) as mock_write,
        ):
            result = locker._adjust_shutdown_time_later()
        assert result is True
        mock_write.assert_called_once_with(22, 21, 8, restore=True)

    def test_clamps_to_max_23(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test hours are clamped to maximum of 23."""
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch.object(locker, "_read_shutdown_config", return_value=(22, 23, 8)),
            patch.object(
                locker, "_write_shutdown_config", return_value=True
            ) as mock_write,
        ):
            locker._adjust_shutdown_time_later()
        mock_write.assert_called_once_with(23, 23, 8, restore=True)

    def test_handles_oserror(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test handles OSError."""
        locker = create_locker(mock_tk, tmp_path)
        with patch.object(
            locker,
            "_read_shutdown_config",
            side_effect=OSError("fail"),
        ):
            assert locker._adjust_shutdown_time_later() is False


class TestSickModeUsedToday:
    """Tests for _sick_mode_used_today method."""

    def test_returns_false_when_no_file(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns False when state file doesn't exist."""
        locker = create_locker(mock_tk, tmp_path)
        mock_file = MagicMock()
        mock_file.exists.return_value = False
        with patch(
            "python_pkg.screen_locker._shutdown.SICK_DAY_STATE_FILE",
            mock_file,
        ):
            assert locker._sick_mode_used_today() is False

    def test_returns_true_when_used_today(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns True when state matches today."""
        locker = create_locker(mock_tk, tmp_path)
        state_file = tmp_path / "state.json"
        with patch(
            "python_pkg.screen_locker._shutdown.SICK_DAY_STATE_FILE",
            state_file,
        ):
            from datetime import datetime, timezone

            today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
            state_file.write_text(json.dumps({"date": today}))
            assert locker._sick_mode_used_today() is True

    def test_returns_false_when_different_date(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns False when state is from different date."""
        locker = create_locker(mock_tk, tmp_path)
        state_file = tmp_path / "state.json"
        with patch(
            "python_pkg.screen_locker._shutdown.SICK_DAY_STATE_FILE",
            state_file,
        ):
            state_file.write_text(json.dumps({"date": "2020-01-01"}))
            assert locker._sick_mode_used_today() is False

    def test_returns_false_on_json_error(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns False on JSONDecodeError."""
        locker = create_locker(mock_tk, tmp_path)
        state_file = tmp_path / "state.json"
        with patch(
            "python_pkg.screen_locker._shutdown.SICK_DAY_STATE_FILE",
            state_file,
        ):
            state_file.write_text("not json{{{")
            assert locker._sick_mode_used_today() is False


class TestSaveSickDayState:
    """Tests for _save_sick_day_state method."""

    def test_saves_state_successfully(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test saves state file with correct content."""
        locker = create_locker(mock_tk, tmp_path)
        state_file = tmp_path / "state.json"
        with patch(
            "python_pkg.screen_locker._shutdown.SICK_DAY_STATE_FILE",
            state_file,
        ):
            result = locker._save_sick_day_state("2026-03-21", 21, 20)
        assert result is True
        data = json.loads(state_file.read_text())
        assert data["date"] == "2026-03-21"
        assert data["original_mon_wed_hour"] == 21
        assert data["original_thu_sun_hour"] == 20

    def test_returns_false_on_oserror(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns False when write fails."""
        locker = create_locker(mock_tk, tmp_path)
        mock_path = MagicMock()
        mock_path.open.side_effect = OSError("permission denied")
        with patch(
            "python_pkg.screen_locker._shutdown.SICK_DAY_STATE_FILE",
            mock_path,
        ):
            result = locker._save_sick_day_state("2026-03-21", 21, 20)
        assert result is False


class TestLoadSickDayState:
    """Tests for _load_sick_day_state method."""

    def test_loads_valid_state(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test loads state with all fields present."""
        locker = create_locker(mock_tk, tmp_path)
        state_file = tmp_path / "state.json"
        state_file.write_text(
            json.dumps(
                {
                    "date": "2026-03-20",
                    "original_mon_wed_hour": 21,
                    "original_thu_sun_hour": 20,
                }
            )
        )
        with patch(
            "python_pkg.screen_locker._shutdown.SICK_DAY_STATE_FILE",
            state_file,
        ):
            result = locker._load_sick_day_state()
        assert result == ("2026-03-20", 21, 20)

    def test_returns_none_when_fields_missing(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns None when required fields are missing."""
        locker = create_locker(mock_tk, tmp_path)
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({"date": "2026-03-20"}))
        with patch(
            "python_pkg.screen_locker._shutdown.SICK_DAY_STATE_FILE",
            state_file,
        ):
            result = locker._load_sick_day_state()
        assert result is None


class TestWriteRestoredConfig:
    """Tests for _write_restored_config method."""

    def test_restores_config_and_removes_state(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test restores config values and deletes state file."""
        locker = create_locker(mock_tk, tmp_path)
        state_file = tmp_path / "state.json"
        state_file.write_text("{}")
        with (
            patch.object(locker, "_read_shutdown_config", return_value=(20, 19, 8)),
            patch.object(
                locker, "_write_shutdown_config", return_value=True
            ) as mock_write,
            patch(
                "python_pkg.screen_locker._shutdown.SICK_DAY_STATE_FILE",
                state_file,
            ),
        ):
            locker._write_restored_config(21, 20, "2026-03-20")
        mock_write.assert_called_once_with(21, 20, 8, restore=True)
        assert not state_file.exists()

    def test_still_removes_state_when_config_read_fails(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test removes state file even when config read returns None."""
        locker = create_locker(mock_tk, tmp_path)
        state_file = tmp_path / "state.json"
        state_file.write_text("{}")
        with (
            patch.object(locker, "_read_shutdown_config", return_value=None),
            patch(
                "python_pkg.screen_locker._shutdown.SICK_DAY_STATE_FILE",
                state_file,
            ),
        ):
            locker._write_restored_config(21, 20, "2026-03-20")
        assert not state_file.exists()
