#!/usr/bin/env python3
"""Assert every lock screen fits a 1366x768 display.

A lock surface is fullscreen, grabbed and (in production) VT-locked. Content
that does not fit is only reachable by scrolling a screen that should never
have needed a scrollbar -- and the scroll that revealed it used to happen on
its own, moving the screen under a user who had touched nothing (2026-08-03).
The runtime half of this guarantee is the ``warning``
``ScrollableSurface.finalize`` logs; this script is the half that runs before
the code ships, so a layout change cannot quietly reintroduce overflow.

``StatusWindow`` is deliberately absent: it is a normal, resizable,
dismissible window rather than a lock surface, so a user who needs more of it
can resize it. Every screen that grabs the display is here.

Not a pytest test because ``screen_locker/tests/conftest.py`` replaces the
whole ``tk`` module for every test so the suite can never reach a display, and
widget heights can only be measured by really rendering them. Like
``verify_lock_popup_safety.py``, this re-executes itself under Xvfb:

    python3 ~/screen-locker/scripts/verify_screen_fits.py
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING

from gatelock import LockConfig, measure_fit, report_fit

from screen_locker._constants import MANUAL_WORKOUT_REFLECTION_MIN_CHARS
from screen_locker._heat_skip import build_heat_skip_content
from screen_locker._manual_workout_dialog import ManualWorkoutDialogMixin
from screen_locker._sick_dialog import SickDialogMixin
from screen_locker._surface_group import FrameGroup
from screen_locker._ui_flows import UIFlowsMixin
from screen_locker._ui_flows_relaxed import UIFlowsRelaxedMixin
from screen_locker._ui_widgets import UIWidgetsMixin

if TYPE_CHECKING:
    from collections.abc import Callable
    import tkinter as tk

    from gatelock import FitResult, ScrollableSurface

_logger = logging.getLogger(__name__)

INNER_ENV = "_SCREEN_FITS_CHECK_INNER"

# The panel this app has to support: the laptop it runs on. Shorter panels
# get gatelock's best-effort compaction (``gatelock._density``) but are not
# gated here -- no machine runs one, and a target nobody uses is a constraint
# that only ever costs.
SIZES: tuple[tuple[int, int], ...] = ((1366, 768),)

# Long enough to be realistic: a message that wraps to three lines is a
# different height than one that does not, and this is what the phone check
# actually hands the retry screen.
LONG_MESSAGE = (
    "✘ Workout JSON is from 2026-07-27, not today\n"
    "Neither StrongLifts nor RunnerUp found a workout today.\n"
    "Go do your workout first!"
)


def reexec_under_xvfb() -> int:
    """Re-run this script on a throwaway X display, returning its exit code."""
    xvfb_run = shutil.which("xvfb-run")
    if xvfb_run is None:
        _logger.error(
            "xvfb-run not found. Install it with: sudo pacman -S --needed "
            "xorg-server-xvfb"
        )
        return 1
    env = dict(os.environ, **{INNER_ENV: "1"})
    return subprocess.run(
        [
            xvfb_run,
            "-a",
            # Bigger than every size under test, so each surface is sized by
            # the geometry this harness sets rather than clamped by the display.
            "-s",
            "-screen 0 1600x1200x24",
            sys.executable,
            str(Path(__file__).resolve()),
        ],
        check=False,
        env=env,
    ).returncode


class ScreenHost(
    UIWidgetsMixin,
    UIFlowsMixin,
    UIFlowsRelaxedMixin,
    SickDialogMixin,
    ManualWorkoutDialogMixin,
):
    """The real screen-painting mixins, over a throwaway surface.

    Only the attributes the paint methods read are set. Nothing that reaches a
    phone, the network or a background thread is called: each screen is
    painted directly, with the message its flow would have been handed.

    The ``paint_*`` wrappers exist so the measurement list below never reaches
    into the mixins' private surface from outside the class.
    """

    def __init__(self, surface: ScrollableSurface) -> None:
        """Point the mixins at one surface's content frame."""
        self.root = surface.content.winfo_toplevel()
        self.demo_mode = False
        self.verify_only = False
        self.log_file = (
            Path(__file__).resolve().parent.parent
            / "screen_locker"
            / "workout_log.json"
        )
        self._colors = LockConfig()
        self.container = FrameGroup([surface.content])
        self.lockout_time = 1800
        self.workout_data: dict[str, str] = {}

    # -- hooks the flows call on submit/cancel; no screen here is submitted --

    def _on_manual_workout_saved(self, entry: dict[str, object]) -> None:
        """Unused: no form is submitted."""

    def _on_manual_workout_cancelled(self) -> None:
        """Unused: BACK is never pressed."""

    def unlock_screen(self) -> None:
        """Unused: nothing unlocks during a measurement."""

    def close(self) -> None:
        """Unused: no screen is closed during a measurement."""

    def _verify_phone_workout(self) -> tuple[str, str]:
        """Never reached -- present so a stray call fails loudly, not silently."""
        msg = "the fit check must not run the phone check"
        raise AssertionError(msg)

    # -- public paint wrappers, one per screen under measurement --

    def paint_retry(self) -> None:
        """Paint the "no workout found" retry screen."""
        self._show_retry_and_sick(LONG_MESSAGE)

    def paint_manual_form(self) -> None:
        """Paint the manual-workout evidence form."""
        self._show_manual_workout_form()

    def paint_manual_form_with_error(self) -> None:
        """Paint the form as it looks after a rejected submission.

        Measured separately because the validation message is a line the empty
        form does not have, and "fits until the user gets something wrong" is
        not fitting.
        """
        self._show_manual_workout_form()
        self._mw_error_label.config(
            text=(
                "Start time must look like HH:MM, and every reflection needs "
                f"at least {MANUAL_WORKOUT_REFLECTION_MIN_CHARS} characters."
            )
        )

    def paint_sick(self) -> None:
        """Paint the sick-day justification screen."""
        self._show_sick_justification()

    def paint_relaxed_retry(self) -> None:
        """Paint the relaxed-day (Tue-Thu) retry screen."""
        self._show_relaxed_retry(LONG_MESSAGE, "no_workout")

    def paint_verify_retry(self) -> None:
        """Paint the verify-mode retry screen."""
        self._show_verify_retry(LONG_MESSAGE)


@dataclass(frozen=True)
class Screen:
    """One screen to measure, named by the paint call that produces it."""

    name: str
    paint: Callable[[ScreenHost], None]


def _build_heat_skip(surface: ScrollableSurface) -> tk.Misc:
    """Paint the heat-skip screen and return the frame to measure.

    Built through its extracted content builder because in production it owns
    a fullscreen ``tk.Tk()`` of its own, which this harness cannot measure.
    """
    return build_heat_skip_content(
        surface.content, 34.0, on_skip=lambda: None, on_decline=lambda: None
    )


SCREENS: tuple[Screen, ...] = (
    Screen("phone-check", ScreenHost.paint_phone_check),
    Screen("no-workout-retry", ScreenHost.paint_retry),
    Screen("manual-workout-form", ScreenHost.paint_manual_form),
    Screen("manual-workout-form+error", ScreenHost.paint_manual_form_with_error),
    Screen("sick-justification", ScreenHost.paint_sick),
    Screen("lockout", ScreenHost.lockout),
    Screen("relaxed-day-retry", ScreenHost.paint_relaxed_retry),
    Screen("verify-retry", ScreenHost.paint_verify_retry),
)

# Screens built without a ScreenHost, measured through their own builder.
EXTRA_SCREENS: tuple[tuple[str, object], ...] = (("heat-skip", _build_heat_skip),)


def measure_all() -> list[FitResult]:
    """Measure every screen at every supported size."""
    results: list[FitResult] = []
    for width, height in SIZES:
        for screen in SCREENS:

            def build(surface: ScrollableSurface, paint: Screen = screen) -> None:
                paint.paint(ScreenHost(surface))

            results.append(measure_fit(screen.name, build, width=width, height=height))
        results.extend(
            measure_fit(name, build, width=width, height=height)
            for name, build in EXTRA_SCREENS
        )
    return results


def main() -> int:
    """Measure every screen and fail if any of them overflows."""
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    if os.environ.get(INNER_ENV) != "1":
        return reexec_under_xvfb()

    _logger.info("Measuring every lock screen against every supported panel:")
    results = measure_all()
    if report_fit(results):
        _logger.info("\nOK: every screen fits without scrolling.")
        return 0
    _logger.error(
        "\nAt least one screen needs a scrollbar to be usable. Shrink the "
        "layout (design-system tokens, gatelock._density) rather than "
        "accepting the scroll -- a lock screen the user has to scroll is the "
        "defect this check exists to prevent."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
