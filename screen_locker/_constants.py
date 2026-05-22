"""Constants for the screen locker module."""

from __future__ import annotations

from pathlib import Path

SICK_LOCKOUT_SECONDS = 120  # base 2 minutes wait when sick (escalates with usage)
PHONE_PENALTY_DELAY_DEMO = 10
PHONE_PENALTY_DELAY_PRODUCTION = 100
# Penalty added to phone-penalty timer when ADB / phone unavailable
# (so unplugging phone does not become an easy escape into sick mode).
NO_PHONE_EXTRA_LOCKOUT_SECONDS = 480  # extra 8 minutes on top of base
# Sick day rate-limiting (rolling windows). Once any window is exhausted
# the "I'm sick" button disappears entirely.
SICK_BUDGET_PER_7_DAYS = 1
SICK_BUDGET_PER_30_DAYS = 3
SICK_BUDGET_PER_90_DAYS = 10
# Each sick day in the trailing 30 days doubles the wait countdown.
SICK_LOCKOUT_MULTIPLIER_PER_RECENT = 2
# Minimum chars in the freeform sick justification.
SICK_JUSTIFICATION_MIN_CHARS = 120
# How many past sick justifications to show on the dialog (read-only).
SICK_HISTORY_REVIEW_COUNT = 10
# Forced read-only delay before SUBMIT enables when a commitment was made.
SICK_COMMITMENT_FORCED_READ_SECONDS = 5
# Breaking a commitment counts as this many sick budget days.
SICK_COMMITMENT_PENALTY_DAYS = 2
# How long the commitment prompt stays visible after a workout unlock.
COMMITMENT_PROMPT_TIMEOUT_SECONDS = 15
ADB_TIMEOUT = 15
STRONGLIFTS_DB_REMOTE = (
    "/data/data/com.stronglifts.app/databases/StrongLifts-Database-3"
)
MIN_WORKOUT_DURATION_MINUTES = 50
MAX_CLOCK_SKEW_SECONDS = 300  # 5 minutes max time skew from NTP
EARLY_BIRD_START_HOUR = 5
EARLY_BIRD_END_HOUR = 8
EARLY_BIRD_END_MINUTE = 30
SHUTDOWN_CONFIG_FILE = Path("/etc/shutdown-schedule.conf")
# HMAC key for signing workout log entries (root-owned, 0600)
HMAC_KEY_FILE = Path("/etc/workout-locker/hmac.key")
# Helper script path (relative to this file)
ADJUST_SHUTDOWN_SCRIPT = Path(__file__).resolve().parent / "adjust_shutdown_schedule.sh"
# State file to track sick day usage and original config values
SICK_DAY_STATE_FILE = Path(__file__).resolve().parent / "sick_day_state.json"
# Persistent sick-day history (rate-limit, debt, commitments, justifications).
# Distinct from SICK_DAY_STATE_FILE which is a one-day shutdown-config snapshot.
SICK_HISTORY_FILE = Path(__file__).resolve().parent / "sick_history.json"
# JSON list of ISO date strings ("YYYY-MM-DD") for which the screen lock is skipped.
SCHEDULED_SKIPS_FILE = Path(__file__).resolve().parent / "scheduled_skips.json"
