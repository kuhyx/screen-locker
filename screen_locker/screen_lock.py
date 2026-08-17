#!/usr/bin/env python3
"""Screen locker with workout verification for Arch Linux / i3wm.

Requires user to log their workout to unlock the screen.
"""

from __future__ import annotations

import logging
from pathlib import Path
import sys
import tkinter as tk
from typing import TYPE_CHECKING

from gatelock import (
    GateRoot,
    LockConfig,
    LockWindow,
)

from screen_locker._auto_upgrade import AutoUpgradeMixin
from screen_locker._constants import (
    EARLY_BIRD_END_HOUR,
    EARLY_BIRD_END_MINUTE,
    EARLY_BIRD_START_HOUR,
    HMAC_KEY_FILE,
    MAX_CLOCK_SKEW_SECONDS,
    MIN_WORKOUT_DURATION_MINUTES,
    PHONE_PENALTY_DELAY_DEMO,
    PHONE_PENALTY_DELAY_PRODUCTION,
    SCHEDULED_SKIPS_FILE,
    SICK_LOCKOUT_SECONDS,
)
from screen_locker._early_bird import EarlyBirdMixin
from screen_locker._heat_skip import HeatSkipMixin
from screen_locker._log_mixin import LogMixin
from screen_locker._manual_workout_dialog import ManualWorkoutDialogMixin
from screen_locker._phone_verification import PhoneVerificationMixin
from screen_locker._runnerup_verification import RunnerUpVerificationMixin
from screen_locker._shutdown import ShutdownMixin
from screen_locker._sick_dialog import SickDialogMixin
from screen_locker._startup_checks import StartupChecksMixin
from screen_locker._surface_group import FrameGroup
from screen_locker._ui_flows import UIFlowsMixin
from screen_locker._ui_flows_relaxed import UIFlowsRelaxedMixin
from screen_locker._ui_widgets import UIWidgetsMixin
from screen_locker._unlock_view import UnlockViewMixin
from screen_locker._weekly_check import WEEKLY_WORKOUT_MINIMUM
from screen_locker._window_setup import WindowSetupMixin
from screen_locker._workout_credit import WorkoutCreditMixin

if TYPE_CHECKING:
    from collections.abc import Callable
    from concurrent.futures import Future

__all__ = [
    "EARLY_BIRD_END_HOUR",
    "EARLY_BIRD_END_MINUTE",
    "EARLY_BIRD_START_HOUR",
    "HMAC_KEY_FILE",
    "MAX_CLOCK_SKEW_SECONDS",
    "MIN_WORKOUT_DURATION_MINUTES",
    "PHONE_PENALTY_DELAY_DEMO",
    "PHONE_PENALTY_DELAY_PRODUCTION",
    "SCHEDULED_SKIPS_FILE",
    "SICK_LOCKOUT_SECONDS",
    "WEEKLY_WORKOUT_MINIMUM",
    "ScreenLocker",
]

_logger = logging.getLogger(__name__)


def _assert_not_under_pytest() -> None:
    """Raise if the screen locker is being created inside a pytest run.

    Defence-in-depth: prevents a real fullscreen Tk window from locking
    the user's screen when tests forget to mock ``tk.Tk``.
    The check is cheap (one dict lookup) and only fires during testing.
    """
    if "pytest" in sys.modules and getattr(tk, "__name__", "") == "tkinter":
        msg = (
            "SAFETY: ScreenLocker.__init__ called under pytest with "
            "real tkinter — tk.Tk is not mocked"
        )
        raise RuntimeError(msg)


class ScreenLocker(
    AutoUpgradeMixin,
    EarlyBirdMixin,
    HeatSkipMixin,
    LogMixin,
    ManualWorkoutDialogMixin,
    WindowSetupMixin,
    WorkoutCreditMixin,
    ShutdownMixin,
    PhoneVerificationMixin,
    RunnerUpVerificationMixin,
    SickDialogMixin,
    StartupChecksMixin,
    UIFlowsMixin,
    UIFlowsRelaxedMixin,
    UIWidgetsMixin,
    UnlockViewMixin,
):
    """Screen locker that requires workout logging to unlock."""

    def __init__(
        self,
        *,
        demo_mode: bool = True,
        verify_only: bool = False,
    ) -> None:
        """Initialize screen locker with optional demo mode."""
        _assert_not_under_pytest()
        script_dir = Path(__file__).resolve().parent
        self.log_file = script_dir / "workout_log.json"
        self.verify_only = verify_only
        self.workout_data: dict[str, str] = {}
        self._relaxed_day_mode: bool = False
        self._check_early_exits(verify_only=verify_only)
        self.root = GateRoot()
        self.root.on_callback_error = self.on_callback_error
        title_suffix = (
            " [VERIFY]" if verify_only else (" [DEMO MODE]" if demo_mode else "")
        )
        self.root.title("Workout Locker" + title_suffix)
        self.demo_mode = demo_mode
        self.lockout_time = 10 if demo_mode else 1800
        self._lock: LockWindow | None = None
        # One shared token source for every window/widget this app creates,
        # lock or not -- see the `unified-design-system` skill. `mode`/`grab`/
        # `disable_vt` only matter for the fullscreen lock window itself; the
        # color/font fields apply everywhere, so this is built unconditionally.
        self._colors = LockConfig(
            mode="hard",
            grab="local" if demo_mode else "global",
            disable_vt=not demo_mode,
        )
        # Built before setup(), which calls build_surface per live output.
        self.container = FrameGroup([])
        if verify_only:
            self._setup_verify_window()
        elif self._relaxed_day_mode:
            self._setup_relaxed_day_window()
        else:
            self._lock = self._build_lock_window()
            if demo_mode:
                self._setup_demo_close_button()
        self._ensure_container()
        self._phone_future: Future[tuple[str, str]] | None = None
        self._runnerup_future: Future[tuple[str, str]] | None = None
        self._runnerup_on_failure: Callable[[], None] | None = None
        if verify_only:
            self._start_verify_workout_check()
        elif self._relaxed_day_mode:
            self._start_relaxed_day_flow()
        else:
            self._start_phone_check()
            # Always set on this branch; guard only for mypy (can't narrow
            # across two separate if/elif/else statements).
            if self._lock is not None:  # pragma: no branch
                self._lock.grab_input()

    def close(self) -> None:
        """Close the application and exit."""
        if self._lock is not None:
            self._lock.close()
        else:
            self.root.destroy()
        # The lock screen coming down is the end of enforcement for this run,
        # so it belongs in the journal next to the decision that raised it —
        # otherwise "the lock closed" and "the lock never opened" look alike.
        _logger.warning("Lock window closed — enforcement for this run is over.")
        sys.exit(0)

    def run(self) -> None:
        """Start the Tkinter main event loop."""
        if self._lock is not None:
            self._lock.run()
        else:
            self.root.mainloop()


if __name__ == "__main__":
    from screen_locker._cli import main

    main(ScreenLocker, sys.argv)
