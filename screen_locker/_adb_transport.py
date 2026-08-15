"""ADB transport for phone verification: connect, reconnect, run commands.

Split out of :mod:`screen_locker._phone_verification` to keep every file under
the 250-line cap. Composed back into ``PhoneVerificationMixin`` there, so
callers see no change.

Everything here is plumbing: reaching the phone and running a command on it.
Deciding whether what came back counts as a workout stays in
``_phone_verification``.
"""

from __future__ import annotations

from concurrent.futures import (  # pylint: disable=no-name-in-module
    ThreadPoolExecutor,
    as_completed,
)
import contextlib
import logging
import shutil
import socket
import subprocess

from screen_locker._constants import ADB_TIMEOUT

_logger = logging.getLogger(__name__)


class AdbTransportMixin:
    """Finds the phone over USB or wifi and runs adb commands against it."""

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
