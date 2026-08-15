"""Constructors for a ``ScreenLocker`` under test.

Split out of ``conftest`` (and re-exported from it) so neither file
exceeds the repo's 400-line limit. Every early-exit path a real start-up
would take is patched here, so a test gets a locker that is built but has
not run any of its flows.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker.screen_lock import ScreenLocker

if TYPE_CHECKING:
    from typing import Literal


def _make_locker(
    log_file: Path,
    *,
    n_filled: int = 0,
    bonus_applied: bool = False,
    cfg: tuple | None = (22, 22, 5),
):
    """Build a minimal locker-like namespace for _status.run_status()."""
    locker = SimpleNamespace(
        log_file=log_file,
        workout_data={},
    )
    locker._scan_and_fill_week_runnerup = MagicMock(return_value=n_filled)
    locker._adjust_shutdown_time_by = MagicMock(return_value=bonus_applied)
    locker._read_shutdown_config = MagicMock(return_value=cfg)
    return locker


def create_locker(
    _mock_tk: MagicMock,
    tmp_path: Path,
    *,
    demo_mode: bool = True,
    has_logged: bool = False,
    verify_only: bool = False,
    is_sick_day_log: bool = False,
) -> ScreenLocker:
    """Create a ScreenLocker instance with early bird paths disabled."""
    with (
        patch.object(Path, "resolve", return_value=tmp_path / "screen_locker"),
        patch.object(ScreenLocker, "has_logged_today", return_value=has_logged),
        patch.object(
            ScreenLocker,
            "_is_sick_day_today",
            return_value=is_sick_day_log,
        ),
        patch.object(ScreenLocker, "_is_early_bird_pending", return_value=False),
        patch.object(ScreenLocker, "_is_early_bird_time", return_value=False),
        patch.object(
            ScreenLocker,
            "_try_auto_upgrade_early_bird",
            return_value=False,
        ),
        patch.object(ScreenLocker, "_start_phone_check"),
        patch.object(ScreenLocker, "_start_relaxed_day_flow"),
        patch.object(ScreenLocker, "_start_verify_workout_check"),
        patch.object(ScreenLocker, "_scan_and_fill_week_runnerup", return_value=0),
    ):
        return ScreenLocker(
            demo_mode=demo_mode,
            verify_only=verify_only,
        )


def create_locker_relaxed_day(
    _mock_tk: MagicMock,
    tmp_path: Path,
    *,
    demo_mode: bool = True,
    has_logged: bool = False,
) -> ScreenLocker:
    """Create a ScreenLocker in relaxed-day mode (Tue/Wed/Thu).

    ``is_relaxed_day`` returns True so ``_relaxed_day_mode`` is set and
    ``_start_relaxed_day_flow`` is called instead of ``_start_phone_check``.
    The autouse ``_mock_weekly_logic`` fixture is overridden here.
    """
    with (
        patch.object(Path, "resolve", return_value=tmp_path / "screen_locker"),
        patch.object(ScreenLocker, "has_logged_today", return_value=has_logged),
        patch.object(ScreenLocker, "_is_sick_day_today", return_value=False),
        patch.object(ScreenLocker, "_is_early_bird_pending", return_value=False),
        patch.object(ScreenLocker, "_is_early_bird_time", return_value=False),
        patch.object(ScreenLocker, "_try_auto_upgrade_early_bird", return_value=False),
        patch("screen_locker._startup_checks.is_relaxed_day", return_value=True),
        patch(
            "screen_locker._startup_checks.has_weekly_minimum",
            return_value=False,
        ),
        patch.object(ScreenLocker, "_start_phone_check"),
        patch.object(ScreenLocker, "_start_relaxed_day_flow"),
        patch.object(ScreenLocker, "_start_verify_workout_check"),
    ):
        return ScreenLocker(demo_mode=demo_mode)


def create_locker_early_bird(
    _mock_tk: MagicMock,
    tmp_path: Path,
    *,
    state: Literal["none", "log_active", "log_expired"] = "none",
    has_logged: bool = False,
    demo_mode: bool = True,
) -> ScreenLocker:
    """Create a ScreenLocker configured for early bird path testing.

    Args:
        state: One of:
            - "none": outside early bird window, no early bird log.
            - "log_active": early bird log exists, still in window.
            - "log_expired": early bird log exists, past 8:30 AM.
        has_logged: Return value for has_logged_today mock.
        demo_mode: Passed to ScreenLocker constructor.
    """
    is_early_bird_log = state in ("log_active", "log_expired")
    is_early_bird_time = state == "log_active"
    with (
        patch.object(Path, "resolve", return_value=tmp_path / "screen_locker"),
        patch.object(ScreenLocker, "has_logged_today", return_value=has_logged),
        patch.object(ScreenLocker, "_is_sick_day_today", return_value=False),
        patch.object(
            ScreenLocker, "_is_early_bird_pending", return_value=is_early_bird_log
        ),
        patch.object(
            ScreenLocker, "_is_early_bird_time", return_value=is_early_bird_time
        ),
        patch.object(ScreenLocker, "_try_auto_upgrade_early_bird", return_value=False),
        patch.object(ScreenLocker, "_start_phone_check"),
        patch.object(ScreenLocker, "_start_relaxed_day_flow"),
        patch.object(ScreenLocker, "_start_verify_workout_check"),
    ):
        return ScreenLocker(demo_mode=demo_mode)
