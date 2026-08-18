"""Tests for the relaxed_day_already_skipped early-exit branch."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

from screen_locker._log_mixin import write_signed_entry
from screen_locker.screen_lock import ScreenLocker

if TYPE_CHECKING:
    from unittest.mock import MagicMock


class TestRelaxedDayAlreadySkippedBranch:
    """RelaxedDayAlreadySkippedBranch."""

    def test_relaxed_day_already_skipped_today_stays_silent(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A same-day relaxed_day_skip entry exits quietly instead of re-showing.

        Regression test: the recurring 30-minute workout-locker.timer used to
        re-derive relaxed_day from scratch on every tick with no memory of an
        earlier "Skip -- No Penalty" click, so the prompt kept reappearing.
        """
        # Path.resolve() is patched below to always return
        # tmp_path/"screen_locker", so ScreenLocker's
        # script_dir.parent/"log.json" resolves to tmp_path/"log.json" -- NOT
        # tmp_path/"screen_locker"/"log.json".
        log_file = tmp_path / "log.json"
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        write_signed_entry(log_file, today, {"type": "relaxed_day_skip"})

        with (
            patch.object(Path, "resolve", return_value=tmp_path / "screen_locker"),
            patch.object(ScreenLocker, "_is_sick_day_today", return_value=False),
            patch.object(ScreenLocker, "_is_early_bird_pending", return_value=False),
            patch.object(ScreenLocker, "_is_early_bird_time", return_value=False),
            patch.object(
                ScreenLocker, "_try_auto_upgrade_early_bird", return_value=False
            ),
            patch(
                "screen_locker._startup_checks.is_relaxed_day",
                return_value=True,
            ),
            patch.object(ScreenLocker, "_start_phone_check"),
            patch.object(ScreenLocker, "_start_relaxed_day_flow") as mock_relaxed,
            patch.object(ScreenLocker, "_start_verify_workout_check"),
        ):
            locker = ScreenLocker(demo_mode=True)

        # sys.exit is mocked (a no-op under pytest), so __init__ keeps running
        # past the early return -- same as the existing
        # test_has_logged_today_exits_before_relaxed_check in
        # test_weekly_logic.py. The regression this guards against is real
        # duplicate UI, which _relaxed_day_mode staying False and
        # _start_relaxed_day_flow never firing both rule out.
        mock_sys_exit.assert_called_once_with(0)
        mock_relaxed.assert_not_called()
        assert locker._relaxed_day_mode is False
