"""RunnerUp retirement: the adb wrapper and the state file (no real adb)."""

from __future__ import annotations

from pathlib import Path
import subprocess
from types import SimpleNamespace
from typing import Any

import pytest

from screen_locker import _runnerup_retire_adb as ra

SERIAL = ra.PHONE_SERIAL
PKG_LINE = f"package:{ra.PACKAGE}\n"


class FakeAdb:
    """A ``subprocess.run`` stand-in: replies by the adb sub-command."""

    def __init__(self, replies: dict[str, Any] | None = None) -> None:
        """Init  ."""
        self.replies = replies or {}
        self.calls: list[list[str]] = []

    def __call__(self, cmd: list[str], **_: object) -> SimpleNamespace:
        """Call  ."""
        self.calls.append(cmd)
        for key, reply in self.replies.items():
            if key in " ".join(cmd):
                if isinstance(reply, BaseException):
                    raise reply
                code, out, err = reply(cmd) if callable(reply) else reply
                return SimpleNamespace(returncode=code, stdout=out, stderr=err)
        return SimpleNamespace(returncode=0, stdout="", stderr="")


def phone(fake: FakeAdb, adb: str | None = "/usr/bin/adb") -> ra.Phone:
    """Phone."""
    return ra.Phone(run=fake, which=lambda _name: adb)


def test_available_follows_which() -> None:
    """Test available follows which."""
    assert phone(FakeAdb()).available() is True
    assert phone(FakeAdb(), adb=None).available() is False


@pytest.mark.parametrize(
    "boom", [FileNotFoundError("adb"), subprocess.TimeoutExpired("adb", 1)]
)
def test_adb_failing_to_run_is_an_adb_error(boom: BaseException) -> None:
    """Test adb failing to run is an adb error."""
    with pytest.raises(ra.AdbError, match="did not run"):
        phone(FakeAdb({"devices": boom})).find_device()


def test_nonzero_exit_carries_the_output() -> None:
    """Test nonzero exit carries the output."""
    fake = FakeAdb({"devices": (1, "", "daemon not running")})
    with pytest.raises(ra.AdbError, match="daemon not running"):
        phone(fake).find_device()


@pytest.mark.parametrize(
    ("listing", "serial", "reason"),
    [
        (f"List of devices attached\n{SERIAL}\tdevice\n", SERIAL, "attached"),
        (
            f"List of devices attached\nadb-{SERIAL}-x._adb-tls-connect._tcp\tdevice\n",
            f"adb-{SERIAL}-x._adb-tls-connect._tcp",
            "attached",
        ),
        (f"List of devices attached\n{SERIAL}\tunauthorized\n", None, "unauthorized"),
        ("List of devices attached\nOTHER\tdevice\n", None, "not attached"),
        ("List of devices attached\n", None, "not attached"),
    ],
)
def test_find_device(listing: str, serial: str | None, reason: str) -> None:
    """Test find device."""
    device = phone(FakeAdb({"devices": (0, listing, "")})).find_device()
    assert device.serial == serial
    assert reason in device.reason


def test_wifi_entry_is_asked_for_its_hardware_serial() -> None:
    """Test wifi entry is asked for its hardware serial."""
    listing = "List of devices attached\n192.168.1.5:5555\tdevice\n"
    fake = FakeAdb({"devices": (0, listing, ""), "getprop": (0, f"{SERIAL}\n", "")})
    device = phone(fake).find_device()
    assert device.serial == "192.168.1.5:5555"
    assert ["adb", "-s", "192.168.1.5:5555", "shell", "getprop", "ro.serialno"] in (
        fake.calls
    )


def test_wifi_entry_of_another_phone_is_not_ours() -> None:
    """Test wifi entry of another phone is not ours."""
    listing = "List of devices attached\n10.0.0.2:5555\tdevice\n"
    fake = FakeAdb({"devices": (0, listing, ""), "getprop": (0, "OTHER\n", "")})
    assert phone(fake).find_device().serial is None


def test_wifi_entry_that_will_not_answer_is_warned_about(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test wifi entry that will not answer is warned about."""
    listing = "List of devices attached\n10.0.0.2:5555\tdevice\n"
    fake = FakeAdb({"devices": (0, listing, ""), "getprop": (1, "", "offline")})
    with caplog.at_level("WARNING"):
        assert phone(fake).find_device().serial is None
    assert "Could not read the serial" in caplog.text


def test_presence_probe_sees_hidden_packages_but_the_final_check_does_not() -> None:
    """Test presence probe sees hidden packages but the final check does not."""
    fake = FakeAdb({"pm list": (0, PKG_LINE, "")})
    phone(fake).installed("dev")
    phone(fake).installed("dev", hidden=False)
    assert "-u" in fake.calls[0]
    assert "-u" not in fake.calls[1]


def test_pull_gets_a_long_timeout_and_other_calls_the_short_one(
    tmp_path: Path,
) -> None:
    """Test pull gets a long timeout and other calls the short one."""
    timeouts: dict[str, object] = {}
    make = _pull_creates(1)

    def run(cmd: list[str], **kw: object) -> SimpleNamespace:
        """Run."""
        timeouts[cmd[3]] = kw["timeout"]
        code, out, err = make(cmd) if cmd[3] == "pull" else (0, "a.tcx\n", "")
        return SimpleNamespace(returncode=code, stdout=out, stderr=err)

    ra.Phone(run=run, which=lambda _n: "adb").backup("dev", tmp_path / "b")
    assert timeouts == {"shell": 50, "pull": 900}


def test_installed_needs_the_exact_package_line() -> None:
    """Test installed needs the exact package line."""
    yes = FakeAdb({"pm list": (0, PKG_LINE, "")})
    assert phone(yes).installed("dev") is True
    assert yes.calls[0][:3] == ["adb", "-s", "dev"]
    other = FakeAdb({"pm list": (0, f"package:{ra.PACKAGE}.pro\n", "")})
    assert phone(other).installed("dev") is False


def _pull_creates(count: int, root: str = "RunnerUp"):
    """Pull creates."""

    def make(cmd: list[str]) -> tuple[int, str, str]:
        """Make."""
        folder = Path(cmd[-1]) / root
        folder.mkdir(parents=True)
        for i in range(count):
            (folder / f"r{i}.tcx").write_text("x")
        return 0, "", ""

    return make


def test_backup_stages_then_renames_and_counts(tmp_path: Path) -> None:
    """Test backup stages then renames and counts."""
    fake = FakeAdb({"ls": (0, "a.tcx\nb.tcx\nb.gpx\n", ""), "pull": _pull_creates(2)})
    final = tmp_path / "backup_2026"
    target, count = phone(fake).backup("dev", final)
    assert (target, count) == (final, 2)
    assert len(list(final.glob("*.tcx"))) == 2
    assert not (tmp_path / "backup_2026.partial").exists()


def test_backup_never_overwrites_an_existing_folder(tmp_path: Path) -> None:
    """Test backup never overwrites an existing folder."""
    final = tmp_path / "backup"
    final.mkdir()
    (tmp_path / "backup.partial").mkdir()  # a stale half-pull is cleared
    fake = FakeAdb({"ls": (0, "a.tcx\n", ""), "pull": _pull_creates(1)})
    target, _ = phone(fake).backup("dev", final)
    assert target == tmp_path / "backup-2"


def test_backup_short_pull_is_an_error_and_not_renamed(tmp_path: Path) -> None:
    """Test backup short pull is an error and not renamed."""
    fake = FakeAdb({"ls": (0, "a.tcx\nb.tcx\n", ""), "pull": _pull_creates(1)})
    with pytest.raises(ra.AdbError, match="pulled 1 of 2"):
        phone(fake).backup("dev", tmp_path / "b")
    assert not (tmp_path / "b").exists()


def test_backup_pull_that_creates_nothing_is_an_error(tmp_path: Path) -> None:
    """Test backup pull that creates nothing is an error."""
    fake = FakeAdb({"ls": (0, "a.tcx\n", "")})
    with pytest.raises(ra.AdbError, match="pulled -1 of 1"):
        phone(fake).backup("dev", tmp_path / "b")


def test_uninstall_succeeds_only_when_the_package_is_gone() -> None:
    """Test uninstall succeeds only when the package is gone."""
    fake = FakeAdb({"uninstall": (0, "Success\n", ""), "pm list": (0, "", "")})
    phone(fake).uninstall("dev")
    assert ["adb", "-s", "dev", "uninstall", ra.PACKAGE] in fake.calls


def test_uninstall_refusal_keeps_adbs_reason() -> None:
    """Test uninstall refusal keeps adbs reason."""
    fail = "Failure [DELETE_FAILED_DEVICE_POLICY_MANAGER]"
    fake = FakeAdb({"uninstall": (1, fail, "")})
    with pytest.raises(ra.AdbError, match="DELETE_FAILED_DEVICE_POLICY_MANAGER"):
        phone(fake).uninstall("dev")


def test_uninstall_without_success_text_is_an_error() -> None:
    """Test uninstall without success text is an error."""
    fake = FakeAdb({"uninstall": (0, "weird\n", "")})
    with pytest.raises(ra.AdbError, match="did not report Success"):
        phone(fake).uninstall("dev")


def test_uninstall_that_leaves_the_package_is_an_error() -> None:
    """Test uninstall that leaves the package is an error."""
    fake = FakeAdb({"uninstall": (0, "Success\n", ""), "pm list": (0, PKG_LINE, "")})
    with pytest.raises(ra.AdbError, match="still listed"):
        phone(fake).uninstall("dev")
