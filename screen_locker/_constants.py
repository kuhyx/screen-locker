"""Constants for the screen locker module."""

from __future__ import annotations

from pathlib import Path

# Validation limits for workout data
MAX_DISTANCE_KM = 100
MAX_TIME_MINUTES = 600
MAX_PACE_MIN_PER_KM = 20
MIN_EXERCISE_NAME_LEN = 3
MAX_SETS = 20
MAX_REPS = 100
MAX_WEIGHT_KG = 500
SICK_LOCKOUT_SECONDS = 120  # 2 minutes wait when sick
SUBMIT_DELAY_DEMO = 30
SUBMIT_DELAY_PRODUCTION = 180
PHONE_PENALTY_DELAY_DEMO = 10
PHONE_PENALTY_DELAY_PRODUCTION = 600
ADB_TIMEOUT = 15
STRONGLIFTS_DB_REMOTE = (
    "/data/data/com.stronglifts.app/databases/StrongLifts-Database-3"
)
SHUTDOWN_CONFIG_FILE = Path("/etc/shutdown-schedule.conf")
# Helper script path (relative to this file)
ADJUST_SHUTDOWN_SCRIPT = Path(__file__).resolve().parent / "adjust_shutdown_schedule.sh"
# State file to track sick day usage and original config values
SICK_DAY_STATE_FILE = Path(__file__).resolve().parent / "sick_day_state.json"

STRENGTH_FIELDS: list[tuple[str, int]] = [
    ("Exercises (comma-separated):", 50),
    ("Sets per exercise (comma-separated):", 20),
    ("Reps (comma-sep, + for variable: 12+11+12):", 30),
    ("Weight per exercise kg (comma-separated):", 20),
    ("Total weight lifted (kg):", 15),
]
