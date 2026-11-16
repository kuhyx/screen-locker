"""Desktop notification the moment a workout earns its credit.

The reward is the point: a workout should be *felt* as paid the second the PC
credits it, not discovered at the next look at the status window. Every path
that credits a workout ends in
:meth:`~screen_locker._workout_credit.WorkoutCreditMixin._apply_credit_for_written_entry`,
which calls :func:`notify_workout_credit` once per newly earned credit slot.

The body shows the shutdown only: the gaming budget is gone (earned_time
0.22.0), so there is no second figure to feel.

A notification is a courtesy, never part of crediting: any failure (no DBus,
no notify-send, a hang) is logged at warning and swallowed.
"""

from __future__ import annotations

from datetime import date
import logging
import shutil
import subprocess
from typing import Final

from screen_locker._day import today_str
from screen_locker._earned import hhmm, span
from screen_locker._grace_floor import tonight_minutes

_logger: Final = logging.getLogger(__name__)

# textgate: glyphs + numbers (colour emoji are safe in the notification
# daemon, unlike Tk). Was "Workout credited 💪" / "Shutdown 23:00 (+2h)" /
# "Credit applied (details unavailable)".
TITLE: Final = "\N{FLEXED BICEPS} \N{CHECK MARK}"
_SHUTDOWN: Final = "\N{POWER SYMBOL}"
_NOTIFY_TIMEOUT_SECONDS: Final = 5


def credit_body(
    before: tuple[int, int, int] | None,
    after: tuple[int, int, int] | None,
) -> str:
    """``⏻ 23:00 (+2h)`` -- whichever parts are known.

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
        text = f"{_SHUTDOWN} {hhmm(tonight)}"
        if before is not None:
            moved = max(0, tonight - tonight_minutes(before, day))
            text += f" (+{span(moved)})"
        parts.append(text)
    return " \N{MIDDLE DOT} ".join(parts) or "\N{CHECK MARK}"


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
    if result.returncode:
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
) -> bool:
    """Notify a newly earned workout credit. Never raises."""
    body = credit_body(before, after)
    return send_notification(TITLE, body)
