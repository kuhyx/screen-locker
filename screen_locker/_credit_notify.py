"""Desktop notification the moment a workout earns its credit.

The reward is the point: a workout should be *felt* as paid the second the PC
credits it, not discovered at the next look at the status window. Every path
that credits a workout ends in
:meth:`~screen_locker._workout_credit.WorkoutCreditMixin._apply_credit_for_written_entry`,
which calls :func:`notify_workout_credit` once per newly earned credit slot.

The gaming figure is ``earned_time.resolve`` over screen-locker's own answers
(:func:`screen_locker._shutdown_target.gather` -- the same sum the daily reset
writes), so no budget math lives here. steam-backlog-enforcer resolves the
same registry with its own transports and holds a day's high-water mark, so
its figure can sit above this one, never below on a normal day.

A notification is a courtesy, never part of crediting: any failure (no DBus,
no notify-send, a hang) is logged at warning and swallowed.
"""

from __future__ import annotations

from datetime import date
import logging
import shutil
import subprocess
from typing import TYPE_CHECKING, Final

from screen_locker._day import today_str
from screen_locker._earned import hhmm, span
from screen_locker._grace_floor import tonight_minutes
from screen_locker._shutdown_target import gather

if TYPE_CHECKING:
    from pathlib import Path

_logger: Final = logging.getLogger(__name__)

TITLE: Final = "Workout credited \N{FLEXED BICEPS}"
_NOTIFY_TIMEOUT_SECONDS: Final = 5
_MINUTES_PER_HOUR: Final = 60.0


def gaming_minutes_today(log_file: Path | None) -> int | None:
    """Today's gaming budget per the earned_time registry, or ``None``.

    ``None`` (logged) when the inputs cannot be read; the notification then
    shows the shutdown time alone.
    """
    try:
        target = gather(date.fromisoformat(today_str()), log_file)
    except (OSError, ValueError, KeyError) as exc:
        _logger.warning(
            "Could not compute today's gaming budget for the credit "
            "notification (%s) — showing the shutdown time only",
            exc,
        )
        return None
    return int(target.resolution.gaming_minutes)


def credit_body(
    before: tuple[int, int, int] | None,
    after: tuple[int, int, int] | None,
    gaming_minutes: int | None,
) -> str:
    """``Shutdown 23:00 (+2h) · gaming 7.0h`` -- whichever parts are known.

    ``before``/``after`` are the shutdown config around the credit; the delta
    is tonight's actual move, so a capped or rest-day credit shows ``+0h``.
    """
    parts: list[str] = []
    if after is None:
        _logger.warning(
            "Shutdown config unreadable after a workout credit — the "
            "notification shows no shutdown time"
        )
    else:
        day = date.fromisoformat(today_str())
        tonight = tonight_minutes(after, day)
        text = f"Shutdown {hhmm(tonight)}"
        if before is not None:
            moved = max(0, tonight - tonight_minutes(before, day))
            text += f" (+{span(moved)})"
        parts.append(text)
    if gaming_minutes is not None:
        parts.append(f"gaming {gaming_minutes / _MINUTES_PER_HOUR:.1f}h")
    return " \N{MIDDLE DOT} ".join(parts) or "Credit applied (details unavailable)"


def send_notification(title: str, body: str) -> bool:
    """Show a desktop notification via ``notify-send``; False (logged) on failure."""
    binary = shutil.which("notify-send")
    if binary is None:
        _logger.warning("notify-send not found — no desktop notification: %s", body)
        return False
    try:
        result = subprocess.run(
            [binary, "--app-name=screen-locker", title, body],
            capture_output=True,
            text=True,
            timeout=_NOTIFY_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        _logger.warning("Desktop notification failed (%s): %s", exc, body)
        return False
    if result.returncode != 0:
        _logger.warning(
            "notify-send exited %d (%s) — no desktop notification: %s",
            result.returncode,
            result.stderr.strip() or "no stderr; is a DBus session reachable?",
            body,
        )
        return False
    _logger.info("Desktop notification: %s — %s", title, body)
    return True


def notify_workout_credit(
    before: tuple[int, int, int] | None,
    after: tuple[int, int, int] | None,
    log_file: Path | None,
) -> bool:
    """Notify a newly earned workout credit. Never raises."""
    body = credit_body(before, after, gaming_minutes_today(log_file))
    return send_notification(TITLE, body)
