"""Tests for shutdown schedule adjustment coverage gaps (part 2)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.usefixtures("pre_ladder")
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
            patch.object(
                locker, "_read_shutdown_config", return_value=(1200, 1140, 480)
            ),
            patch.object(
                locker, "_write_shutdown_config", return_value=True
            ) as mock_write,
        ):
            result = locker._adjust_shutdown_time_later()
        assert result is True
        mock_write.assert_called_once_with(1320, 1260, 480, restore=True)

    def test_clamps_to_max_23(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test hours are clamped to maximum of 23."""
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch.object(
                locker, "_read_shutdown_config", return_value=(1320, 1380, 480)
            ),
            patch.object(
                locker, "_write_shutdown_config", return_value=True
            ) as mock_write,
        ):
            locker._adjust_shutdown_time_later()
        mock_write.assert_called_once_with(1380, 1380, 480, restore=True)

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
