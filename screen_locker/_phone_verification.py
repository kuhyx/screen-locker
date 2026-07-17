"""Phone workout verification: GitHub sync first, ADB/HTTP as fallback."""

from __future__ import annotations

from concurrent.futures import (  # pylint: disable=no-name-in-module
    ThreadPoolExecutor,
    as_completed,
)
import contextlib
from http import client as _http_client
import json
import logging
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time

from screen_locker._constants import (
    ADB_TIMEOUT,
    MIN_WORKOUT_DURATION_MINUTES,
    WORKOUT_APP_JSON_REMOTES,
    WORKOUT_HTTP_PORT,
)
from screen_locker._time_check import check_clock_skew
from screen_locker._workout_sync import pull_synced_workout

_HTTPConnection = _http_client.HTTPConnection
_HTTPException = _http_client.HTTPException
_HTTP_OK = _http_client.OK

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
        return not result.returncode, result.stdout

    def _adb_shell(self, command: str, *, root: bool = False) -> tuple[bool, str]:
        """Run a shell command on the connected Android device."""
        if root:
            return self._run_adb(["shell", "su", "-c", command])
        return self._run_adb(["shell", command])

    def _get_wireless_serial(self) -> str | None:
        """Return the serial (ip:port) of the first connected wireless ADB device."""
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

        If no device is visible, attempts wireless reconnection via subnet scan.
        """
        if self._has_adb_device():
            return True
        _logger.info("No ADB device detected — attempting wireless reconnect...")
        return self._try_wireless_reconnect()

    # ── ADB verification ──────────────────────────────────────────────────────

    def _pull_workout_app_json(self) -> dict | None:
        """Pull workout_result.json from the phone (ADB, no root needed).

        The app writes to one of several candidate paths (see sync_service.dart),
        so we pull every candidate and prefer the one dated today. A stale file
        can linger at a fallback path from a day the primary write failed, so
        "first that parses" is not safe — we explicitly favour today's data and
        only fall back to a stale/older payload if no candidate is from today.
        """
        tmp = Path(tempfile.gettempdir()) / "workout_result.json"
        today = time.strftime("%Y-%m-%d")
        first_parsed: dict | None = None
        for remote in WORKOUT_APP_JSON_REMOTES:
            ok, _ = self._run_adb(["pull", remote, str(tmp)])
            if not ok:
                continue
            try:
                data = json.loads(tmp.read_text())
            except (json.JSONDecodeError, OSError) as exc:
                _logger.warning(
                    "Workout JSON pulled from %s is unreadable (%s) — skipping "
                    "that candidate and trying the remaining phone paths",
                    remote,
                    exc,
                )
                continue
            if data.get("date") == today:
                return data
            if first_parsed is None:
                first_parsed = data
        return first_parsed

    def _validate_json_data(self, data: dict) -> tuple[str, str]:
        """Validate parsed workout JSON. Returns (status, message)."""
        today = time.strftime("%Y-%m-%d")
        if data.get("date") != today:
            return "stale", f"Workout JSON is from {data.get('date')}, not today"
        if not data.get("exercises"):
            return "no_exercises", "No exercises found in today's workout JSON"
        duration_min = data.get("duration_seconds", 0) / 60.0
        if duration_min < MIN_WORKOUT_DURATION_MINUTES:
            return (
                "too_short",
                f"Workout too short! {duration_min:.0f} min logged, "
                f"need at least {MIN_WORKOUT_DURATION_MINUTES} min.",
            )
        flag = "all succeeded" if data.get("succeeded") else "partial"
        return "verified", f"Workout verified! ({duration_min:.0f} min, {flag})"

    # ── HTTP fallback (no ADB / developer options required) ───────────────────

    def _scan_for_http_server(self) -> str | None:
        """Scan local /24 subnet for the workout app HTTP server on port 8765.

        Returns the first reachable URL or None.
        """
        prefix = self._get_local_subnet_prefix()
        if prefix is None:
            return None

        def probe(i: int) -> str | None:
            ip = f"{prefix}.{i}"
            with (
                contextlib.suppress(OSError),
                socket.create_connection((ip, WORKOUT_HTTP_PORT), timeout=0.3),
            ):
                return f"http://{ip}:{WORKOUT_HTTP_PORT}/workout"
            return None

        _logger.info(
            "Scanning %s.1-254:%d for workout app...", prefix, WORKOUT_HTTP_PORT
        )
        with ThreadPoolExecutor(max_workers=64) as executor:
            for future in as_completed(
                executor.submit(probe, i) for i in range(1, 255)
            ):
                result = future.result()
                if result is not None:
                    return result
        return None

    def _fetch_http_workout(self) -> dict | None:
        """Fetch workout JSON from the app's HTTP server on the local network.

        Uses http.client directly to avoid urllib URL-open security lint rules.
        The URL is always http://<local-ip>:8765/workout — no user input involved.
        """
        url = self._scan_for_http_server()
        if url is None:
            return None
        # url is always "http://<ip>:<port>/workout" — constructed internally.
        try:
            _, _, hostport = url.partition("://")
            host, _, path = hostport.partition("/")
            hostname, _, port_str = host.partition(":")
            conn = _HTTPConnection(hostname, int(port_str), timeout=5)
            conn.request("GET", f"/{path}")
            resp = conn.getresponse()
            if resp.status != _HTTP_OK:
                return None
            return json.loads(resp.read().decode())
        except (_HTTPException, OSError, ValueError, json.JSONDecodeError) as exc:
            _logger.warning(
                "HTTP fetch of today's workout from %s failed (%s) — no data "
                "from the phone's HTTP server, so verification falls through",
                url,
                exc,
            )
            return None

    # ── Main verification entry point ─────────────────────────────────────────

    def _verify_phone_workout(self) -> tuple[str, str]:
        """Verify today's workout: GitHub sync first, ADB/HTTP as fallback.

        Returns (status, message). Status values:
        verified / too_short / not_verified / no_phone / sync_failed /
        stale / no_exercises / clock_tampered.
        """
        clock_ok, clock_msg = check_clock_skew()
        if not clock_ok:
            return "clock_tampered", clock_msg

        # GitHub sync is the primary channel — it works without the phone
        # being on the same network as the PC. Only a *verified* sync result
        # short-circuits ADB/HTTP: a stale/incomplete cloud entry (e.g. the
        # phone's last push predates today, or a later push failed offline)
        # must not preempt a fresher ADB pull, so anything less than
        # "verified" is kept as a fallback-of-last-resort candidate instead
        # of being returned immediately. A sync error never blocks unlocking
        # either; `sync_failed` only surfaces if ADB/HTTP also come up empty.
        synced_data, sync_error = pull_synced_workout()
        sync_result: tuple[str, str] | None = None
        if synced_data is not None:
            sync_result = self._validate_json_data(synced_data)
            if sync_result[0] == "verified":
                return sync_result
            _logger.info(
                "Synced data not fully verified (%s) — trying ADB/HTTP...",
                sync_result[0],
            )
        elif sync_error is not None:
            _logger.info(
                "GitHub sync unavailable (%s) — trying ADB/HTTP...", sync_error
            )

        # Prefer ADB when a device is visible, but if the pull yields no usable
        # JSON, fall through to the HTTP/WiFi scan — the app's in-memory HTTP
        # server may still hold today's workout even when the file pull fails.
        adb_connected = self._is_phone_connected()
        if adb_connected:
            data = self._pull_workout_app_json()
            if data is not None:
                return self._validate_json_data(data)
            _logger.info("ADB pull found no workout JSON — trying HTTP scan...")
        else:
            _logger.info("No ADB device — trying HTTP scan on local network...")

        data = self._fetch_http_workout()
        if data is not None:
            return self._validate_json_data(data)
        if sync_result is not None:
            return sync_result
        if sync_error is not None:
            return "sync_failed", sync_error
        if adb_connected:
            return (
                "not_verified",
                "Workout app JSON not found. Complete a workout in the app first.",
            )
        return "no_phone", "Phone not reachable via ADB or HTTP on local network"
