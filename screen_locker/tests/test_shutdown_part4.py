"""Tests for sick-day state save/load and config restoration."""

from __future__ import annotations

import logging
from pathlib import Path
import re
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import earned_time

from screen_locker._ceiling import HARD_CEILING_MINUTES
from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    import pytest


def test_hard_ceiling_matches_the_helpers_restore_ceiling() -> None:
    """The Python bound and adjust_shutdown_schedule.sh's must not drift."""
    script = Path(__file__).parents[1] / "adjust_shutdown_schedule.sh"
    match = re.search(
        r"^readonly RESTORE_CEILING=(\d+)", script.read_text(), re.MULTILINE
    )
    assert match is not None
    assert int(match.group(1)) == HARD_CEILING_MINUTES


class TestAdjustShutdownTimeBy:
    """Tests for _adjust_shutdown_time_by method (extra-workout bonus)."""

    def test_adjusts_time_successfully(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Normal path: reads config, increments both hours, writes back."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker, "_read_shutdown_config", MagicMock(return_value=(1260, 1260, 300))
        )
        object.__setattr__(
            locker, "_write_shutdown_config", MagicMock(return_value=True)
        )
        assert locker._adjust_shutdown_time_by(60) is True
        locker._write_shutdown_config.assert_called_once_with(
            1320, 1320, 300, restore=True
        )

    def test_caps_at_the_day_ceiling(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Times are capped at the day's ceiling (23:00 today), not midnight."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker, "_read_shutdown_config", MagicMock(return_value=(1380, 1380, 300))
        )
        object.__setattr__(
            locker, "_write_shutdown_config", MagicMock(return_value=True)
        )
        locker._adjust_shutdown_time_by(120)
        locker._write_shutdown_config.assert_called_once_with(
            1380, 1380, 300, restore=True
        )

    def test_caps_at_a_ceiling_below_23(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """If WAKE_MINUTES moves the ceiling to 21:00 no bonus passes it."""
        monkeypatch.setattr(earned_time, "shutdown_ceiling_for", lambda _d: 21 * 60)
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker, "_read_shutdown_config", MagicMock(return_value=(1200, 1200, 300))
        )
        object.__setattr__(
            locker, "_write_shutdown_config", MagicMock(return_value=True)
        )
        locker._adjust_shutdown_time_by(120)
        locker._write_shutdown_config.assert_called_once_with(
            1260, 1260, 300, restore=True
        )

    def test_failed_ceiling_lookup_falls_back_to_23_loudly(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """earned_time raising must not lift the cap: 23:00, logged at warning."""

        def boom(_day: object) -> int:
            msg = "registry unreadable"
            raise ValueError(msg)

        monkeypatch.setattr(earned_time, "shutdown_ceiling_for", boom)
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker, "_read_shutdown_config", MagicMock(return_value=(1380, 1380, 300))
        )
        object.__setattr__(
            locker, "_write_shutdown_config", MagicMock(return_value=True)
        )
        with caplog.at_level(logging.WARNING):
            locker._adjust_shutdown_time_by(120)
        locker._write_shutdown_config.assert_called_once_with(
            1380, 1380, 300, restore=True
        )
        assert "ceiling" in caplog.text

    def test_returns_false_when_config_is_none(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """_read_shutdown_config returns None → return False immediately."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker, "_read_shutdown_config", MagicMock(return_value=None)
        )
        assert locker._adjust_shutdown_time_by(1) is False

    def test_returns_false_on_oserror(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """OSError during read is caught; returns False."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_read_shutdown_config",
            MagicMock(side_effect=OSError("permission denied")),
        )
        assert locker._adjust_shutdown_time_by(1) is False

    def test_returns_false_on_value_error(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """ValueError during processing is caught; returns False."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_read_shutdown_config",
            MagicMock(side_effect=ValueError("bad value")),
        )
        assert locker._adjust_shutdown_time_by(1) is False
