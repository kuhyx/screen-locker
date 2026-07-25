"""Tests for post-sick-day workout verification (--verify-workout)."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestIsSickDayToday:
    """Tests for _is_sick_day_today method.

    sick_day is tracked in sick_history.json (via _sick_tracker.py) as the
    sole source of truth -- not in workout_log.json. The autouse
    _isolate_sick_history fixture redirects SICK_HISTORY_FILE to
    tmp_path/sick_history.json for every test.
    """

    def test_no_history_file(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Return False when sick_history.json does not exist."""
        locker = create_locker(mock_tk, tmp_path)
        assert locker._is_sick_day_today() is False

    def test_today_not_sick_day(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Return False when today is not in sick_history's sick_days list."""
        locker = create_locker(mock_tk, tmp_path)
        history_file = tmp_path / "sick_history.json"
        history_file.write_text(json.dumps({"sick_days": ["2020-01-01"]}))
        assert locker._is_sick_day_today() is False

    def test_today_is_sick_day(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Return True when today is in sick_history's sick_days list."""
        locker = create_locker(mock_tk, tmp_path)
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        history_file = tmp_path / "sick_history.json"
        history_file.write_text(json.dumps({"sick_days": [today]}))
        assert locker._is_sick_day_today() is True


class TestVerifyOnlyInit:
    """Tests for ScreenLocker initialization with verify_only=True."""

    def test_verify_only_exits_when_no_sick_day(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Exit when verify_only but no sick day logged today."""
        mock_sys_exit.side_effect = SystemExit(0)
        with pytest.raises(SystemExit):
            create_locker(
                mock_tk,
                tmp_path,
                verify_only=True,
                is_sick_day_log=False,
            )
        mock_sys_exit.assert_called_once_with(0)

    def test_verify_only_starts_when_sick_day(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Start verification window when sick day is logged."""
        locker = create_locker(
            mock_tk,
            tmp_path,
            verify_only=True,
            is_sick_day_log=True,
        )
        assert locker.verify_only is True
        mock_sys_exit.assert_not_called()

    def test_verify_only_sets_title(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Verify window title includes [VERIFY]."""
        locker = create_locker(
            mock_tk,
            tmp_path,
            verify_only=True,
            is_sick_day_log=True,
        )
        locker.root.title.assert_called_with("Workout Locker [VERIFY]")

    def test_close_and_run_use_root_directly(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """No LockWindow is built for verify_only; close()/run() use root."""
        locker = create_locker(
            mock_tk,
            tmp_path,
            verify_only=True,
            is_sick_day_log=True,
        )
        assert locker._lock is None

        locker.run()
        locker.root.mainloop.assert_called_once()

        locker.close()
        locker.root.destroy.assert_called_once()


class TestSetupVerifyWindow:
    """Tests for _setup_verify_window."""

    def test_sets_geometry_and_protocol(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Verify window uses 600x400 geometry and WM_DELETE_WINDOW."""
        locker = create_locker(
            mock_tk,
            tmp_path,
            verify_only=True,
            is_sick_day_log=True,
        )
        locker.root.geometry.assert_called_with("600x400")
        locker.root.configure.assert_called_with(
            bg=locker._colors.bg,
            cursor="arrow",
        )
        locker.root.protocol.assert_called_with(
            "WM_DELETE_WINDOW",
            locker.close,
        )


class TestStartVerifyWorkoutCheck:
    """Tests for _start_verify_workout_check."""

    def test_starts_phone_check_and_polls(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Start phone verification and begin polling."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_verify_phone_workout",
            MagicMock(return_value=("verified", "ok")),
        )
        object.__setattr__(
            locker,
            "_poll_verify_workout_check",
            MagicMock(),
        )

        locker._start_verify_workout_check()

        assert locker._phone_future is not None
        locker._poll_verify_workout_check.assert_called_once()


class TestPollVerifyWorkoutCheck:
    """Tests for _poll_verify_workout_check."""

    def test_schedules_retry_when_not_done(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Re-schedule polling when future is not done."""
        locker = create_locker(mock_tk, tmp_path)
        mock_future = MagicMock()
        mock_future.done.return_value = False
        locker._phone_future = mock_future

        locker._poll_verify_workout_check()

        locker.root.after.assert_called_with(
            500,
            locker._poll_verify_workout_check,
        )

    def test_handles_result_when_done(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Route to result handler when future is done."""
        locker = create_locker(mock_tk, tmp_path)
        mock_future = MagicMock()
        mock_future.done.return_value = True
        mock_future.result.return_value = ("verified", "Found workout")
        locker._phone_future = mock_future
        object.__setattr__(
            locker,
            "_handle_verify_workout_result",
            MagicMock(),
        )

        locker._poll_verify_workout_check()

        locker._handle_verify_workout_result.assert_called_once_with(
            "verified",
            "Found workout",
        )


class TestHandleVerifyWorkoutResult:
    """Tests for _handle_verify_workout_result."""

    def test_verified_adjusts_shutdown_and_saves(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """On verified: adjust shutdown, save log, show success."""
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = tmp_path / "workout_log.json"
        object.__setattr__(
            locker,
            "_adjust_shutdown_time_later",
            MagicMock(return_value=True),
        )

        locker._handle_verify_workout_result("verified", "1 session found")

        assert locker.workout_data["type"] == "phone_verified"
        assert locker.workout_data["after_sick_day"] == "true"
        locker._adjust_shutdown_time_later.assert_called_once()
        locker.root.after.assert_called()

    def test_verified_without_adjustment(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """On verified but adjustment fails: still saves and shows success."""
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = tmp_path / "workout_log.json"
        object.__setattr__(
            locker,
            "_adjust_shutdown_time_later",
            MagicMock(return_value=False),
        )

        locker._handle_verify_workout_result("verified", "1 session found")

        assert locker.workout_data["type"] == "phone_verified"
        locker.root.after.assert_called()

    def test_not_verified_shows_retry(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """On not_verified: show retry screen."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_show_verify_retry",
            MagicMock(),
        )

        locker._handle_verify_workout_result(
            "not_verified",
            "No workout today",
        )

        locker._show_verify_retry.assert_called_once_with(
            "No workout today",
        )

    def test_error_shows_retry(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """On error: show retry screen."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_show_verify_retry",
            MagicMock(),
        )

        locker._handle_verify_workout_result("error", "ADB failed")

        locker._show_verify_retry.assert_called_once_with("ADB failed")


class TestShowVerifyRetry:
    """Tests for _show_verify_retry."""

    def test_shows_retry_and_close_buttons(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Show TRY AGAIN and Close buttons."""
        locker = create_locker(mock_tk, tmp_path)

        locker._show_verify_retry("No workout found")

        # Verify container was cleared and buttons were packed
        locker.container.first.winfo_children.return_value = []
