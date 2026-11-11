"""Screens ``verify_text_free`` paints beyond the fit check's list.

The fit check measures only the screens that can overflow. The text check has
to see every screen kuhy can look at: the verified/unlock screens, the
checking screens and the status window (resizable, so absent from the fit
check). Each build paints into ``surface.content`` like the fit check's.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from screen_locker._status_data import gather_status
from screen_locker._temperature import TemperatureCheck
from screen_locker._unlock_view import UnlockViewMixin
from screen_locker._workout_credit import WorkoutCreditResult
from screen_locker.status_view import StatusWindow
from scripts.verify_screen_fits import ScreenHost

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import SimpleNamespace


class _Host(UnlockViewMixin, ScreenHost):
    """ScreenHost plus the unlock view, with every reward line switched on."""

    def _apply_workout_credit(self) -> WorkoutCreditResult:
        return WorkoutCreditResult(
            shutdown_adjusted=True,
            extra_bonus_delta=60,
            weekly_count=5,
            already_counted_today=False,
        )

    def _verify_runnerup_workout(self) -> tuple[str, str]:
        """Stand-in for the RunnerUp check: never reads a phone.

        Blocks briefly so the waiting screen is what gets checked, not the
        failure screen a finished future would route to straight away.
        """
        threading.Event().wait(2)
        return ("not_verified", "x")

    def paint_manual_saved(self) -> None:
        """The real confirmation screen (ScreenHost stubs the hook out)."""
        super(ScreenHost, self)._on_manual_workout_saved({"source": "x"})


def _host_paint(method: str, *args: object) -> Callable[[object], None]:
    def build(surface: object) -> None:
        host = _Host(surface)
        host.root.after = lambda *_a, **_k: None  # no unlock timer, no close
        getattr(host, method)(*args)

    return build


def _status_window(surface: SimpleNamespace) -> None:
    """The real status window over today's on-disk state (read-only)."""
    StatusWindow(
        surface.content.winfo_toplevel(),
        gather_status(),
        on_refresh=lambda: None,
        temperature_fetcher=lambda _city: TemperatureCheck(
            temp_celsius=21.0, timed_out=False
        ),
    ).root.update_idletasks()


def extra_paints() -> list[tuple[str, Callable[[object], None]]]:
    """Every screen the fit check does not paint, as (name, build)."""
    return [
        ("unlock", _host_paint("unlock_screen")),
        ("verified", _host_paint("_handle_startup_phone_result", "verified", "x")),
        ("too-short", _host_paint("_handle_startup_phone_result", "too_short", "x")),
        (
            "clock-tampered",
            _host_paint("_handle_startup_phone_result", "clock_tampered", "x"),
        ),
        ("runnerup-check", _host_paint("_handle_startup_phone_result", "stale", "x")),
        ("manual-saved", _host_paint("paint_manual_saved")),
        ("status-window", _status_window),
    ]
