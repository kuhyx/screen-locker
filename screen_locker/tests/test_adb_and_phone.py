"""Tests for ADB commands, phone connection, and database operations."""
# pylint: disable=protected-access,unused-argument

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker.screen_lock import STRONGLIFTS_DB_REMOTE
from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestRunAdb:
    """Tests for _run_adb ADB command execution."""

    def test_run_adb_success(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test successful ADB command."""
        locker = create_locker(mock_tk, tmp_path)
        mock_result = MagicMock(returncode=0, stdout="ok\n")
        with patch(
            "screen_locker._phone_verification.subprocess.run",
            return_value=mock_result,
        ) as mock_run:
            success, output = locker._run_adb(["devices"])

        assert success is True
        assert output == "ok\n"
        mock_run.assert_called_once()

    def test_run_adb_failure(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test failed ADB command."""
        locker = create_locker(mock_tk, tmp_path)
        mock_result = MagicMock(returncode=1, stdout="")
        with patch(
            "screen_locker._phone_verification.subprocess.run",
            return_value=mock_result,
        ):
            success, _output = locker._run_adb(["devices"])

        assert success is False

    def test_run_adb_not_found(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test ADB binary not found."""
        locker = create_locker(mock_tk, tmp_path)
        with patch(
            "screen_locker._phone_verification.subprocess.run",
            side_effect=FileNotFoundError("adb not found"),
        ):
            success, output = locker._run_adb(["devices"])

        assert success is False
        assert not output

    def test_run_adb_oserror(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test ADB OSError."""
        locker = create_locker(mock_tk, tmp_path)
        with patch(
            "screen_locker._phone_verification.subprocess.run",
            side_effect=OSError("permission denied"),
        ):
            success, output = locker._run_adb(["devices"])

        assert success is False
        assert not output

    def test_run_adb_timeout(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test ADB command timeout."""
        locker = create_locker(mock_tk, tmp_path)
        with patch(
            "screen_locker._phone_verification.subprocess.run",
            side_effect=subprocess.TimeoutExpired("adb", 15),
        ):
            success, output = locker._run_adb(["devices"])

        assert success is False
        assert not output


class TestAdbShell:
    """Tests for _adb_shell method."""

    def test_adb_shell_no_root(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test ADB shell without root."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_run_adb",
            MagicMock(
                return_value=(True, "output"),
            ),
        )

        success, output = locker._adb_shell("ls /sdcard")

        locker._run_adb.assert_called_once_with(["shell", "ls /sdcard"])
        assert success is True
        assert output == "output"

    def test_adb_shell_with_root(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test ADB shell with root."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_run_adb",
            MagicMock(
                return_value=(True, "output"),
            ),
        )

        success, _output = locker._adb_shell("ls /data", root=True)

        locker._run_adb.assert_called_once_with(
            ["shell", "su", "-c", "ls /data"],
        )
        assert success is True


class TestIsPhoneConnected:
    """Tests for _is_phone_connected method."""

    def test_phone_connected(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test phone detected as connected."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_run_adb",
            MagicMock(
                return_value=(
                    True,
                    "List of devices attached\nABC123\tdevice\n\n",
                ),
            ),
        )

        assert locker._is_phone_connected() is True

    def test_phone_not_connected(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test no phone connected."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_run_adb",
            MagicMock(
                return_value=(True, "List of devices attached\n\n"),
            ),
        )
        object.__setattr__(
            locker,
            "_try_wireless_reconnect",
            MagicMock(
                return_value=False,
            ),
        )

        assert locker._is_phone_connected() is False

    def test_phone_offline(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test phone connected but offline."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_run_adb",
            MagicMock(
                return_value=(
                    True,
                    "List of devices attached\nABC123\toffline\n\n",
                ),
            ),
        )
        object.__setattr__(
            locker,
            "_try_wireless_reconnect",
            MagicMock(
                return_value=False,
            ),
        )

        assert locker._is_phone_connected() is False

    def test_adb_command_fails(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test ADB command failure."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_run_adb",
            MagicMock(
                return_value=(False, ""),
            ),
        )
        object.__setattr__(
            locker,
            "_try_wireless_reconnect",
            MagicMock(
                return_value=False,
            ),
        )

        assert locker._is_phone_connected() is False


class TestFindHealthConnectDb:
    """Tests for _pull_stronglifts_db method."""

    def test_db_pulled_successfully(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test StrongLifts DB pulled from device."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_adb_shell",
            MagicMock(
                return_value=(True, ""),
            ),
        )
        object.__setattr__(
            locker,
            "_run_adb",
            MagicMock(
                return_value=(True, ""),
            ),
        )

        result = locker._pull_stronglifts_db()

        assert result is not None
        locker._adb_shell.assert_called_once()
        locker._run_adb.assert_called_once()
        call_args = locker._run_adb.call_args[0][0]
        assert call_args[0] == "pull"

    def test_db_cat_fails(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns None when cat command fails."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_adb_shell",
            MagicMock(
                return_value=(False, ""),
            ),
        )

        assert locker._pull_stronglifts_db() is None

    def test_db_pull_fails(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns None when adb pull fails."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_adb_shell",
            MagicMock(
                return_value=(True, ""),
            ),
        )
        object.__setattr__(
            locker,
            "_run_adb",
            MagicMock(
                return_value=(False, ""),
            ),
        )

        assert locker._pull_stronglifts_db() is None

    def test_db_uses_correct_remote_path(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test uses the correct StrongLifts DB remote path."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_adb_shell",
            MagicMock(
                return_value=(True, ""),
            ),
        )
        object.__setattr__(
            locker,
            "_run_adb",
            MagicMock(
                return_value=(True, ""),
            ),
        )

        locker._pull_stronglifts_db()

        shell_cmd = locker._adb_shell.call_args[0][0]
        assert STRONGLIFTS_DB_REMOTE in shell_cmd
