"""Phone workout verification mixin using ADB and StrongLifts."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import contextlib
import logging
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import time

from python_pkg.screen_locker._constants import (
    ADB_TIMEOUT,
    MIN_WORKOUT_DURATION_MINUTES,
    STRONGLIFTS_DB_REMOTE,
)
from python_pkg.screen_locker._time_check import check_clock_skew

_logger = logging.getLogger(__name__)


class PhoneVerificationMixin:
    """Mixin providing phone-based workout verification via ADB."""

    def _run_adb(self, args: list[str]) -> tuple[bool, str]:
        """Run an ADB command and return success flag and stdout."""
        adb = shutil.which("adb") or "adb"
        # When multiple devices are connected (e.g. USB + wireless), pin to
        # the wireless device's serial to avoid "more than one device" errors.
        _discovery_cmds = {"devices", "connect", "disconnect", "kill-server"}
        serial = (
            self._get_wireless_serial()
            if args and args[0] not in _discovery_cmds
            else None
        )
        serial_args = ["-s", serial] if serial else []
        try:
            result = subprocess.run(
                [adb, *serial_args, *args],
                capture_output=True,
                text=True,
                timeout=ADB_TIMEOUT,
                check=False,
            )
        except (FileNotFoundError, OSError) as exc:
            _logger.warning("ADB not available: %s", exc)
            return False, ""
        except subprocess.TimeoutExpired:
            _logger.warning("ADB command timed out: %s", args)
            return False, ""
        return result.returncode == 0, result.stdout

    def _adb_shell(
        self,
        command: str,
        *,
        root: bool = False,
    ) -> tuple[bool, str]:
        """Run a shell command on the connected Android device."""
        if root:
            return self._run_adb(["shell", "su", "-c", command])
        return self._run_adb(["shell", command])

    def _get_wireless_serial(self) -> str | None:
        """Return the serial (ip:port) of the first connected wireless ADB device.

        Used to pin ADB commands to the wireless device when multiple devices
        (e.g. USB cable + wireless debugging) are simultaneously connected.
        """
        success, output = self._run_adb(["devices"])
        if not success:
            return None
        for line in output.strip().split("\n")[1:]:
            parts = line.split()
            if parts and ":" in parts[0] and "device" in line and "offline" not in line:
                return parts[0]
        return None

    def _has_adb_device(self) -> bool:
        """Return True if adb devices shows at least one connected device."""
        success, output = self._run_adb(["devices"])
        if not success:
            return False
        lines = output.strip().split("\n")[1:]
        return any("device" in line and "offline" not in line for line in lines)

    def _try_adb_connect(self, address: str) -> bool:
        """Run adb connect to address. Returns True on success."""
        _, output = self._run_adb(["connect", address])
        lower = output.lower()
        return "connected" in lower and "unable" not in lower and "failed" not in lower

    def _get_local_subnet_prefix(self) -> str | None:
        """Detect the local /24 network prefix (e.g. '192.168.1')."""
        with (
            contextlib.suppress(OSError),
            socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock,
        ):
            sock.connect(("8.8.8.8", 80))
            return ".".join(sock.getsockname()[0].split(".")[:3])
        return None

    def _try_wireless_reconnect(self) -> bool:
        """Scan local /24 subnet on port 5555 and attempt ADB connect to phone."""
        prefix = self._get_local_subnet_prefix()
        if prefix is None:
            _logger.info("Could not determine local subnet for wireless scan")
            return False

        def probe(i: int) -> bool:
            ip = f"{prefix}.{i}"
            with (
                contextlib.suppress(OSError),
                socket.create_connection((ip, 5555), timeout=0.5),
            ):
                if self._try_adb_connect(f"{ip}:5555"):
                    return self._has_adb_device()
            return False

        _logger.info("Scanning %s.1-254:5555 for phone...", prefix)
        with ThreadPoolExecutor(max_workers=64) as executor:
            for future in as_completed(
                executor.submit(probe, i) for i in range(1, 255)
            ):
                if future.result():
                    return True
        return False

    def _is_phone_connected(self) -> bool:
        """Check if an Android device is connected via ADB.

        If no device is visible, attempts wireless reconnection using the
        stored phone IP/port config. USB-connected devices are detected
        automatically by adb devices without any extra steps.
        """
        if self._has_adb_device():
            return True
        _logger.info("No ADB device detected — attempting wireless reconnect...")
        return self._try_wireless_reconnect()

    def _pull_stronglifts_db(self) -> Path | None:
        """Pull StrongLifts database from phone to a local temp file.

        Returns:
            Path to the local copy, or None on failure.
        """
        tmp = Path(tempfile.gettempdir()) / "stronglifts_check.db"
        success, _ = self._adb_shell(
            f"cat '{STRONGLIFTS_DB_REMOTE}' > /sdcard/_sl_tmp.db",
            root=True,
        )
        if not success:
            return None
        ok, _ = self._run_adb(["pull", "/sdcard/_sl_tmp.db", str(tmp)])
        if not ok:
            return None
        return tmp

    def _count_today_workouts(self, db_path: Path) -> int:
        """Count today's workouts in a local copy of StrongLifts DB.

        Args:
            db_path: Path to the locally-pulled StrongLifts database.

        Returns:
            Number of workouts started today (local time).
        """
        try:
            conn = sqlite3.connect(str(db_path))
            try:
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM workouts "
                    "WHERE date(start / 1000, 'unixepoch', 'localtime') "
                    "= date('now', 'localtime')",
                )
                row = cursor.fetchone()
                return int(row[0]) if row else 0
            finally:
                conn.close()
        except (sqlite3.Error, ValueError, TypeError):
            _logger.warning("Failed to query StrongLifts database")
            return 0

    def _get_today_workout_duration_minutes(self, db_path: Path) -> float:
        """Get the total duration in minutes of today's workouts.

        Args:
            db_path: Path to the locally-pulled StrongLifts database.

        Returns:
            Total duration in minutes of all workouts started today.
            Returns 0.0 on any error or if no workouts found.
        """
        try:
            conn = sqlite3.connect(str(db_path))
            try:
                cursor = conn.execute(
                    "SELECT SUM((finish - start) / 1000.0 / 60.0) "
                    "FROM workouts "
                    "WHERE date(start / 1000, 'unixepoch', 'localtime') "
                    "= date('now', 'localtime') "
                    "AND finish > start",
                )
                row = cursor.fetchone()
                return float(row[0]) if row and row[0] is not None else 0.0
            finally:
                conn.close()
        except (sqlite3.Error, ValueError, TypeError):
            _logger.warning("Failed to query workout duration")
            return 0.0

    def _get_today_exercise_count(self, db_path: Path) -> int:
        """Count distinct exercises in today's workouts.

        Uses the StrongLifts 'exercises' table joined with 'workouts' to
        verify that actual exercises were logged, not just empty sessions.

        Args:
            db_path: Path to the locally-pulled StrongLifts database.

        Returns:
            Number of distinct exercises in today's workouts.
            Returns 0 on any error.
        """
        try:
            conn = sqlite3.connect(str(db_path))
            try:
                cursor = conn.execute(
                    "SELECT COUNT(DISTINCT e.exercise) "
                    "FROM exercises e "
                    "JOIN workouts w ON e.workout = w.id "
                    "WHERE date(w.start / 1000, 'unixepoch', 'localtime') "
                    "= date('now', 'localtime')",
                )
                row = cursor.fetchone()
                return int(row[0]) if row else 0
            finally:
                conn.close()
        except (sqlite3.Error, ValueError, TypeError):
            _logger.warning("Failed to query exercise count")
            return 0

    def _is_workout_finish_recent(self, db_path: Path) -> bool:
        """Check if the latest workout's finish time is recent.

        A fresh workout should have finished within the last few hours.
        This prevents using an old pre-prepared database dump.

        Args:
            db_path: Path to the locally-pulled StrongLifts database.

        Returns:
            True if the latest finish time is within 4 hours of now.
        """
        max_age_seconds = 4 * 3600
        try:
            conn = sqlite3.connect(str(db_path))
            try:
                cursor = conn.execute(
                    "SELECT MAX(finish) FROM workouts "
                    "WHERE date(start / 1000, 'unixepoch', 'localtime') "
                    "= date('now', 'localtime') "
                    "AND finish > start",
                )
                row = cursor.fetchone()
                if not row or row[0] is None:
                    return False
                finish_epoch = int(row[0]) / 1000.0
                return (time.time() - finish_epoch) < max_age_seconds
            finally:
                conn.close()
        except (sqlite3.Error, ValueError, TypeError):
            _logger.warning("Failed to query workout finish time")
            return False

    def _validate_workout_db(
        self,
        local_db: Path,
    ) -> tuple[str, str] | None:
        """Validate workout database has a recent, real workout.

        Returns:
            A (status, message) tuple if validation fails, or None if OK.
        """
        count = self._count_today_workouts(local_db)
        if count <= 0:
            return "not_verified", "No workout found on phone today"
        if not self._is_workout_finish_recent(local_db):
            return (
                "stale",
                "Workout finish time is too old. Did you actually work out today?",
            )
        exercise_count = self._get_today_exercise_count(local_db)
        if exercise_count < 1:
            return (
                "no_exercises",
                "No exercises found in today's workout. "
                "Log actual exercises in StrongLifts!",
            )
        return None

    def _verify_phone_workout(self) -> tuple[str, str]:
        """Verify workout was recorded in StrongLifts on the phone.

        Returns:
            Tuple of (status, message) where status is one of:
            - "verified": Workout confirmed and >= minimum duration.
            - "too_short": Workout found but shorter than minimum.
            - "not_verified": Phone connected but no workout found.
            - "no_phone": No phone connected via ADB.
            - "error": Could not access StrongLifts database.
            - "stale": Workout finish time is not recent.
            - "no_exercises": Workout has no logged exercises.
            - "clock_tampered": System clock skew exceeds threshold.
        """
        clock_ok, clock_msg = check_clock_skew()
        if not clock_ok:
            return "clock_tampered", clock_msg
        if not self._is_phone_connected():
            return "no_phone", "No phone connected via ADB"
        local_db = self._pull_stronglifts_db()
        if local_db is None:
            return "error", "StrongLifts database not found on phone"
        db_error = self._validate_workout_db(local_db)
        if db_error is not None:
            return db_error
        duration = self._get_today_workout_duration_minutes(local_db)
        if duration < MIN_WORKOUT_DURATION_MINUTES:
            return (
                "too_short",
                f"Workout too short! {duration:.0f} min logged, "
                f"need at least {MIN_WORKOUT_DURATION_MINUTES} min.",
            )
        exercise_count = self._get_today_exercise_count(local_db)
        return (
            "verified",
            f"Workout verified! ({self._count_today_workouts(local_db)}"
            f" session(s), {duration:.0f} min, "
            f"{exercise_count} exercise(s))",
        )
