"""Tests for shutdown schedule adjustment coverage gaps (part 2)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker.tests.conftest import create_locker

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
