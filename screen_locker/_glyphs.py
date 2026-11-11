"""The locker's pictograms: one place, so a glyph means one thing everywhere.

textgate (kuhy, 2026-11-08): nothing he sees carries words. Every screen is
built from these plus numbers, each paired with a palette colour as the
second channel (success / warning / danger / muted). Plain geometric
characters only: a colour-emoji fallback font can crash Tk 8.6, so no
U+1Fxxx and nothing with an emoji presentation by default.
"""

from __future__ import annotations

from typing import Final

LIFT: Final = "●━━●"  # a barbell: the StrongLifts workout / "go work out"
RUN: Final = "⇝"  # a RunnerUp run
PHONE: Final = "▯"  # the phone (adb)
WAIT: Final = "⋯"  # checking / unlocking in progress
OK: Final = "✓"
FAIL: Final = "✗"
RETRY: Final = "↻"
CLOSE: Final = "✕"
BACK: Final = "↩"
GO: Final = "▶"
SKIP: Final = "↷"
SYNC: Final = "⇅"  # a sync backend (Firebase)
CLOCK: Final = "◷"  # time, the system clock
SHORT: Final = "◔"  # a session shorter than the minimum
FORM: Final = "≡"  # the manual-workout evidence form
SICK: Final = "✚"  # a sick day
SHUTDOWN: Final = "⏻"  # the PC's shutdown time
STREAK: Final = "▰"  # one week of the streak
WEEK_DONE: Final = "●"  # a counted day
WEEK_SICK: Final = "✚"  # a sick day in the week row
WEEK_EMPTY: Final = "○"  # a day with nothing counted
HEAT: Final = "▲"  # the outdoor temperature
LOCK: Final = "■"  # the lock fired
UNLOCK: Final = "□"  # the lock stood down
OPTIONAL: Final = "◇"  # Tue-Thu: a workout is optional today
GIFT: Final = "+"  # an earned reward, always followed by its amount

# Startup phone-check status -> the glyph that replaces its sentence.
STATUS_GLYPH: Final[dict[str, str]] = {
    "too_short": SHORT,
    "clock_tampered": f"{CLOCK}{FAIL}",
    "stale": f"{CLOCK}{FAIL}",
    "no_exercises": f"{LIFT} 0",
    "not_verified": FAIL,
    "no_phone": f"{PHONE}{FAIL}",
    "error": f"{PHONE}{FAIL}",
}


# log.json entry ``type`` -> glyph, for the status window's day cells.
ENTRY_GLYPH: Final[dict[str, str]] = {
    "phone_verified": LIFT,
    "strength": LIFT,
    "pc_workout_verified": LIFT,
    "runnerup_verified": RUN,
    "running": RUN,
    "manual_workout": FORM,
    "heat_skip": HEAT,
    "relaxed_day_skip": SKIP,
    "early_bird": OK,
}


# Lock-decision stage (``_compliance_state._STEPS`` names) -> glyph. A stage
# not listed shows only the lock/unlock square and its colour.
STAGE_GLYPH: Final[dict[str, str]] = {
    "scheduled_skip": SKIP,
    "early_bird_pending_expired": CLOCK,
    "early_bird_window_open": CLOCK,
    "sick_day": SICK,
    "already_logged": OK,
    "wake_alarm_skip": CLOCK,
    "test_hold_active": WAIT,
    "relaxed_day_already_skipped": f"{OPTIONAL}{SKIP}",
    "relaxed_day": OPTIONAL,
    "weekly_minimum_met": WEEK_DONE,
    "evening_lockdown_today": SHUTDOWN,
    "would_lock": LIFT,
}


def entry_glyphs(types: tuple[str, ...]) -> str:
    """Glyphs for a day's entry types; an unknown type shows as ``OK``."""
    return " ".join(ENTRY_GLYPH.get(t, OK) for t in types)


def dots(done: int, total: int) -> str:
    """``●●○○ 2/4``: progress as filled dots plus the numbers (two channels)."""
    filled = max(0, min(done, total))
    return f"{WEEK_DONE * filled}{WEEK_EMPTY * (total - filled)} {done}/{total}"


def status_glyph(status: str) -> str:
    """Return the glyph for a phone-check *status* (``FAIL`` if unknown)."""
    return STATUS_GLYPH.get(status, FAIL)
