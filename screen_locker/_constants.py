"""Constants for the screen locker module."""

from __future__ import annotations

from pathlib import Path

from gatelock.log_integrity import DEFAULT_HMAC_KEY_FILE

# Single-sourced from gatelock so the literal key path can't drift.
HMAC_KEY_FILE = DEFAULT_HMAC_KEY_FILE
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
# Manual (unverified) workout rate-limiting — looser than sick days since
# activities like table tennis recur more often than illness. Once either
# window is exhausted the "Log Manual Workout" option disappears entirely.
MANUAL_WORKOUT_BUDGET_PER_7_DAYS = 2
MANUAL_WORKOUT_BUDGET_PER_30_DAYS = 5
# Minimum start-to-end duration for a manual entry to be accepted.
MANUAL_WORKOUT_MIN_DURATION_MINUTES = 20
# Minimum chars for the "what was done" activity-details field.
MANUAL_WORKOUT_DESCRIPTION_MIN_CHARS = 40
# Minimum chars for each reflection field (what went well / to improve / feeling).
MANUAL_WORKOUT_REFLECTION_MIN_CHARS = 20
MANUAL_WORKOUT_RPE_MIN = 1
MANUAL_WORKOUT_RPE_MAX = 10
ADB_TIMEOUT = 15
# Workout app JSON candidate paths on the phone, in the order the app prefers
# when writing (see sync_service.dart). The app writes to the primary /sdcard/
# path first and only falls back to its app-external files dir if /sdcard/ is
# not writable, so the locker must check both — primary first.
WORKOUT_APP_JSON_REMOTES = (
    "/sdcard/workout_result.json",
    "/storage/emulated/0/Android/data/com.kuhy.workout_app/files/workout_result.json",
)
# Port the workout app's HTTP server listens on (no ADB/developer-options needed).
WORKOUT_HTTP_PORT = 8765
MIN_WORKOUT_DURATION_MINUTES = 60
RUNNERUP_PACKAGES = ("org.runnerup", "org.runnerup.free")
RUNNERUP_DB_SDCARD_TMP = "/sdcard/.runnerup_tmp_verification.db"
MIN_RUN_DURATION_MINUTES = 30
MIN_RUN_DISTANCE_KM = 5.0
RUNNERUP_ACCEPTED_SPORTS: frozenset[int] = frozenset({0, 3, 5})
# 0=RUNNING, 3=ORIENTEERING, 5=TREADMILL
MAX_CLOCK_SKEW_SECONDS = 300  # 5 minutes max time skew from NTP
EARLY_BIRD_START_HOUR = 5
EARLY_BIRD_END_HOUR = 8
EARLY_BIRD_END_MINUTE = 30
HEAT_SKIP_TEMP_THRESHOLD: int = 33  # °C — above this the heat-skip dialog is offered
HEAT_SKIP_CITY: str = "Warsaw"
SHUTDOWN_CONFIG_FILE = Path("/etc/shutdown-schedule.conf")
# Helper script path (relative to this file)
ADJUST_SHUTDOWN_SCRIPT = Path(__file__).resolve().parent / "adjust_shutdown_schedule.sh"
# State file to track sick day usage and original config values
SICK_DAY_STATE_FILE = Path(__file__).resolve().parent / "sick_day_state.json"
# Persistent sick-day history (rate-limit, debt, commitments, justifications).
# Distinct from SICK_DAY_STATE_FILE which is a one-day shutdown-config snapshot.
SICK_HISTORY_FILE = Path(__file__).resolve().parent / "sick_history.json"
# JSON list of ISO date strings ("YYYY-MM-DD") for which the screen lock is skipped.
SCHEDULED_SKIPS_FILE = Path(__file__).resolve().parent / "scheduled_skips.json"
# State file tracking streak, skip credits, and early-bird extension weeks.
EXTRA_BENEFITS_FILE = Path(__file__).resolve().parent / "extra_benefits_state.json"
# State file storing the base (pre-bonus) shutdown hours and last reset date.
SHUTDOWN_BASE_FILE = Path(__file__).resolve().parent / "shutdown_base.json"
# Self-expiring marker: "logged in during today's early-bird window, still
# waiting to see if a real workout shows up." Not a workout_log.json entry —
# it's a same-day pending flag, checked against its own "date" field.
EARLY_BIRD_PENDING_FILE = Path(__file__).resolve().parent / "early_bird_pending.json"

# ---------------------------------------------------------------------------
# Wake-alarm integration (originally from wake_alarm._constants / _state).
# These must match the values used by the companion wake_alarm service.
# ---------------------------------------------------------------------------
# Days on which the wake alarm fires (0=Mon … 6=Sun).
ALARM_DAYS: frozenset[int] = frozenset({0, 4, 5, 6})
# How many hours after midnight the alarm triggers (configurable in wake_alarm).
WAKE_AFTER_HOURS: int = 8
# Path to the rtcwake binary.
RTCWAKE_BIN: str = "/usr/sbin/rtcwake"
# State file written by wake_alarm; read here to check for workout skip.
WAKE_STATE_FILE = (
    Path(__file__).resolve().parent.parent / "wake_alarm" / "wake_state.json"
)

# Directories where RunnerUp writes per-activity TCX exports (File Synchronizer).
# Listed in preference order; both resolve to the same path on most devices.
RUNNERUP_EXPORT_DIRS: tuple[str, ...] = (
    "/sdcard/Documents/RunnerUp",
    "/storage/emulated/0/Documents/RunnerUp",
)

# ---------------------------------------------------------------------------
# Sync (phone workout data) — Workstream C, built on the shared crdt-sync
# library. GitHub is used purely as dumb file storage via the REST Contents
# API (not a git clone), same pattern as diet_guard's cross-device sync. The
# phone app pushes to devices/<SYNC_PHONE_DEVICE_ID>/log.json; the PC reads
# every device's log and pushes its OWN manual workouts to devices/pc/log.json
# (see _manual_push) — which needs a token with contents:write, not read-only.
# ---------------------------------------------------------------------------
SYNC_REPO_OWNER: str = "kuhyx"
SYNC_REPO_NAME: str = "syncs"
SYNC_PHONE_DEVICE_ID: str = "phone"
# A fine-grained GitHub PAT, scoped to just SYNC_REPO_NAME's contents. The
# user creates this once via github.com and saves it here, mode 600. Never
# committed — this path is outside the repo entirely. Unlike diet_guard,
# this file being absent is a normal, expected state (sync is optional here).
SYNC_TOKEN_FILE: Path = Path.home() / ".config" / "screen_locker" / "sync_token"
SYNC_TIMEOUT_SECONDS: float = 10.0
