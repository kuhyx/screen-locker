"""Tests for shutdown schedule adjustment coverage gaps (part 3)."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestWriteShutdownConfig:
    """Tests for _write_shutdown_config method."""

    def test_returns_false_when_script_missing(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns False when adjust script doesn't exist."""
        locker = create_locker(mock_tk, tmp_path)
        mock_script = MagicMock()
        mock_script.exists.return_value = False
        with patch(
            "screen_locker._shutdown.ADJUST_SHUTDOWN_SCRIPT",
            mock_script,
        ):
            result = locker._write_shutdown_config(21, 20, 8)
        assert result is False

    def test_success_calls_run_shutdown_cmd(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test successful config write delegates to _run_shutdown_cmd."""
        locker = create_locker(mock_tk, tmp_path)
        mock_script = MagicMock()
        mock_script.exists.return_value = True
        with (
            patch(
                "screen_locker._shutdown.ADJUST_SHUTDOWN_SCRIPT",
                mock_script,
            ),
            patch.object(locker, "_run_shutdown_cmd", return_value=True) as mock_run,
        ):
            result = locker._write_shutdown_config(21, 20, 8)
        assert result is True
        mock_run.assert_called_once()


class TestRunShutdownCmd:
    """Tests for _run_shutdown_cmd method."""

    def test_success(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test successful command execution."""
        locker = create_locker(mock_tk, tmp_path)
        mock_result = MagicMock(stdout="OK\n")
        with patch(
            "screen_locker._shutdown.subprocess.run",
            return_value=mock_result,
        ):
            result = locker._run_shutdown_cmd(["cmd"], 21, 20)
        assert result is True

    def test_returns_false_on_subprocess_error(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns False on SubprocessError."""
        locker = create_locker(mock_tk, tmp_path)
        with patch(
            "screen_locker._shutdown.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "cmd"),
        ):
            result = locker._run_shutdown_cmd(["cmd"], 21, 20)
        assert result is False
