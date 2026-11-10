"""The phone side of the RunnerUp retirement: find it, back it up, uninstall.

Every call carries ``-s <serial>`` and goes through one ``run`` seam, so tests
never touch a device. adb's exit code is not trusted for the uninstall: it
counts only when the output says ``Success`` AND ``pm list packages`` no
longer lists the package.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import shutil
import subprocess
from typing import TYPE_CHECKING, Any, NoReturn, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable

_logger = logging.getLogger(__name__)

PHONE_SERIAL = "23181JEGR08034"
PACKAGE = "org.runnerup.free"
REMOTE_DIR = "/sdcard/Documents/RunnerUp"
_ADB_TIMEOUT_S = 50
# The whole export history (TCX + GPX) over wifi adb; the oneshot unit has no
# start timeout, so a slow pull is allowed to finish.
_PULL_TIMEOUT_S = 900


class AdbError(RuntimeError):
    """An adb call failed; the message says what and why."""


def _fail(message: str) -> NoReturn:
    raise AdbError(message)


@dataclass(frozen=True)
class Device:
    """Outcome of looking for the phone: the adb serial to use, or why not."""

    serial: str | None
    reason: str


class PhoneLike(Protocol):
    """What the retirement needs from a phone (tests substitute a fake)."""

    def available(self) -> bool:
        """Whether adb can be run at all."""

    def find_device(self) -> Device:
        """The attached phone, or why there is none."""

    def installed(self, dev: str, *, hidden: bool = True) -> bool:
        """Whether RunnerUp is on the phone."""

    def backup(self, dev: str, final: Path) -> tuple[Path, int]:
        """Pull the exports to ``final``."""

    def uninstall(self, dev: str) -> None:
        """Uninstall RunnerUp or raise ``AdbError``."""


class Phone:
    """adb calls against one phone, with the process runner injectable."""

    def __init__(
        self,
        serial: str = PHONE_SERIAL,
        *,
        which: Callable[[str], str | None] = shutil.which,
        run: Callable[..., Any] = subprocess.run,
    ) -> None:
        """Pin the phone's serial; ``which``/``run`` are the test seams."""
        self.serial = serial
        self._which = which
        self._run = run

    def available(self) -> bool:
        """Whether an ``adb`` binary is on PATH."""
        return self._which("adb") is not None

    def _adb(self, *args: str, timeout: int = _ADB_TIMEOUT_S) -> str:
        cmd = ["adb", *args]
        try:
            done = self._run(
                cmd, capture_output=True, text=True, timeout=timeout, check=False
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            msg = f"{' '.join(cmd)} did not run: {exc}"
            raise AdbError(msg) from exc
        if done.returncode:
            detail = (done.stdout + done.stderr).strip()
            _fail(f"{' '.join(cmd)} exited {done.returncode}: {detail}")
        return str(done.stdout)

    def _is_phone(self, serial: str) -> bool:
        """Whether an ``adb devices`` entry is the phone.

        USB and mDNS serials embed the phone's serial; a plain ``ip:port``
        wifi entry does not, so that one is asked for its ``ro.serialno``.
        """
        if self.serial in serial:
            return True
        if ":" not in serial:
            return False
        try:
            asked = self._adb("-s", serial, "shell", "getprop", "ro.serialno")
        except AdbError as exc:
            _logger.warning("Could not read the serial of %s (%s)", serial, exc)
            return False
        return asked.strip() == self.serial

    def find_device(self) -> Device:
        """The attached phone, over USB or wifi (a wireless serial embeds it)."""
        listing = self._adb("devices")
        states: list[str] = []
        for line in listing.splitlines()[1:]:
            serial, _, state = line.partition("\t")
            if not self._is_phone(serial):
                continue
            if state.strip() == "device":
                return Device(serial, "attached")
            states.append(state.strip())
        if states:
            return Device(None, f"phone is {'/'.join(states)}, not ready")
        return Device(None, f"phone {self.serial} is not attached")

    def installed(self, dev: str, *, hidden: bool = True) -> bool:
        """Whether the package is on the phone (exact ``package:`` line).

        ``hidden`` adds ``-u`` so an app that focus mode hides or disables
        still counts as present; it must not be mistaken for an uninstall.
        """
        flag = ["-u"] if hidden else []
        out = self._adb("-s", dev, "shell", "pm", "list", "packages", *flag, PACKAGE)
        return f"package:{PACKAGE}" in out.split()

    def backup(self, dev: str, final: Path) -> tuple[Path, int]:
        """Pull the phone's export folder next to ``final``; return (dir, tcx count).

        Pulled into a staging dir and renamed only once every phone ``.tcx``
        is on disk, so a half backup never looks like a finished one. The
        result is a subfolder, never top-level: a top-level ``*.tcx`` would be
        credited by runnerup-watch.
        """
        listing = self._adb("-s", dev, "shell", "ls", REMOTE_DIR)
        wanted = sum(1 for n in listing.split() if n.endswith(".tcx"))
        staging = final.with_name(final.name + ".partial")
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True)
        self._adb("-s", dev, "pull", REMOTE_DIR, str(staging), timeout=_PULL_TIMEOUT_S)
        pulled = staging / Path(REMOTE_DIR).name
        got = len(list(pulled.rglob("*.tcx"))) if pulled.is_dir() else -1
        if got < wanted:
            _fail(f"backup pulled {got} of {wanted} TCX files into {staging}")
        target, n = final, 1
        while target.exists():
            n += 1
            target = final.with_name(f"{final.name}-{n}")
        pulled.rename(target)
        staging.rmdir()
        return target, got

    def uninstall(self, dev: str) -> None:
        """Uninstall the package and prove it is gone, or raise ``AdbError``."""
        try:
            out = self._adb("-s", dev, "uninstall", PACKAGE)
        except AdbError as exc:
            # adb exits 1 with "Failure [DELETE_FAILED_...]": keep that reason
            # (a device-owner policy can block it) in the error.
            msg = f"uninstall refused: {exc}"
            raise AdbError(msg) from exc
        if "Success" not in out:
            _fail(f"uninstall did not report Success: {out.strip()!r}")
        if self.installed(dev, hidden=False):
            _fail(f"{PACKAGE} is still listed after uninstall")
        _logger.info("Uninstalled %s from %s", PACKAGE, dev)
