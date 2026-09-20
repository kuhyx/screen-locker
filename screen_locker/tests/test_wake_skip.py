"""The wake-alarm carrot in the lock's startup ladder (``_check_today_state_exits``)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from screen_locker._morning_session import MorningSkip
from screen_locker.screen_lock import ScreenLocker
from screen_locker.tests.conftest import create_locker

_SKIP = MorningSkip(outcome="completed", exempt_until=datetime(2099, 1, 1).astimezone())


def _locker(
    tmp_path: Path, *, carrot: MorningSkip | None, has_logged: bool = False
) -> None:
    """Build a locker whose early-bird window is the given carrot verdict."""
    with (
        patch.object(Path, "resolve", return_value=tmp_path / "screen_locker"),
        patch.object(ScreenLocker, "has_logged_today", return_value=has_logged),
        patch.object(ScreenLocker, "_is_sick_day_today", return_value=False),
        patch.object(ScreenLocker, "_is_early_bird_pending", return_value=False),
        patch("screen_locker._early_bird.morning_skip_today", return_value=carrot),
        patch.object(ScreenLocker, "_try_auto_upgrade_early_bird", return_value=False),
        patch.object(ScreenLocker, "_start_phone_check"),
        patch.object(ScreenLocker, "_start_relaxed_day_flow"),
        patch.object(ScreenLocker, "_start_verify_workout_check"),
        patch.object(ScreenLocker, "_scan_and_fill_week_runnerup", return_value=0),
    ):
        ScreenLocker(demo_mode=True)


class TestWakeSkipIntegration:
    def test_exits_and_banks_the_marker_while_the_carrot_is_in_force(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        with (
            patch.object(ScreenLocker, "_save_early_bird_pending") as save,
            patch("screen_locker._auto_upgrade.record_decision") as record,
        ):
            _locker(tmp_path, carrot=_SKIP)
        mock_sys_exit.assert_called_once_with(0)
        save.assert_called_once()
        decision = record.call_args.args[0]
        assert decision.reason == "wake_alarm_skip"
        assert decision.extra["exempt_until"] == _SKIP.exempt_until.isoformat()
        assert "no lock until" in decision.detail

    def test_does_not_exit_without_a_carrot(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        _locker(tmp_path, carrot=None)
        mock_sys_exit.assert_not_called()

    def test_logged_today_takes_precedence(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        with patch("screen_locker._auto_upgrade.record_decision") as record:
            _locker(tmp_path, carrot=_SKIP, has_logged=True)
        mock_sys_exit.assert_called_once_with(0)
        assert record.call_args.args[0].reason == "workout_logged_today"

    def test_verify_only_mode_ignores_wake_skip(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        with patch("screen_locker._early_bird.morning_skip_today", return_value=_SKIP):
            create_locker(mock_tk, tmp_path, verify_only=True, is_sick_day_log=True)
        mock_sys_exit.assert_not_called()
