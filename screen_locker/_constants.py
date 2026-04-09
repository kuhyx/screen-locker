"""Constants for the screen locker module."""

from __future__ import annotations

from pathlib import Path

SICK_LOCKOUT_SECONDS = 120  # 2 minutes wait when sick
PHONE_PENALTY_DELAY_DEMO = 10
PHONE_PENALTY_DELAY_PRODUCTION = 100
ADB_TIMEOUT = 15
STRONGLIFTS_DB_REMOTE = (
    "/data/data/com.stronglifts.app/databases/StrongLifts-Database-3"
)
MIN_WORKOUT_DURATION_MINUTES = 50
MAX_CLOCK_SKEW_SECONDS = 300  # 5 minutes max time skew from NTP
SHUTDOWN_CONFIG_FILE = Path("/etc/shutdown-schedule.conf")
# HMAC key for signing workout log entries (root-owned, 0600)
HMAC_KEY_FILE = Path("/etc/workout-locker/hmac.key")
# Helper script path (relative to this file)
ADJUST_SHUTDOWN_SCRIPT = Path(__file__).resolve().parent / "adjust_shutdown_schedule.sh"
# State file to track sick day usage and original config values
SICK_DAY_STATE_FILE = Path(__file__).resolve().parent / "sick_day_state.json"
