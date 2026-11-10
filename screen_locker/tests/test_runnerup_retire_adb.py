"""RunnerUp retirement: the adb wrapper and the state file (no real adb)."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
from typing import Any

import pytest

from screen_locker import _runnerup_retire_adb as ra
from screen_locker._runnerup_retire_state import RetireState, load_state, save_state

SERIAL = ra.PHONE_SERIAL
PKG_LINE = f"package:{ra.PACKAGE}\n"


class FakeAdb:
    """A ``subprocess.run`` stand-in: replies by the adb sub-command."""

    def __init__(self, replies: dict[str, Any] | None = None) -> None:
        self.replies = replies or {}
        self.calls: list[list[str]] = []

    def __call__(self, cmd: list[str], **_: object) -> SimpleNamespace:
        self.calls.append(cmd)
        for key, reply in self.replies.items():
            if key in " ".join(cmd):
                if isinstance(reply, BaseException):
                    raise reply
                code, out, err = reply(cmd) if callable(reply) else reply
                return SimpleNamespace(returncode=code, stdout=out, stderr=err)
        return SimpleNamespace(returncode=0, stdout="", stderr="")


def phone(fake: FakeAdb, adb: str | None = "/usr/bin/adb") -> ra.Phone:
    return ra.Phone(run=fake, which=lambda _name: adb)


def test_available_follows_which() -> None:
    assert phone(FakeAdb()).available() is True
    assert phone(FakeAdb(), adb=None).available() is False


@pytest.mark.parametrize(
    "boom", [FileNotFoundError("adb"), subprocess.TimeoutExpired("adb", 1)]
)
def test_adb_failing_to_run_is_an_adb_error(boom: BaseException) -> None:
    with pytest.raises(ra.AdbError, match="did not run"):
        phone(FakeAdb({"devices": boom})).find_device()


def test_nonzero_exit_carries_the_output() -> None:
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
    device = phone(FakeAdb({"devices": (0, listing, "")})).find_device()
    assert device.serial == serial
    assert reason in device.reason


def test_installed_needs_the_exact_package_line() -> None:
    yes = FakeAdb({"pm list": (0, PKG_LINE, "")})
    assert phone(yes).installed("dev") is True
    assert yes.calls[0][:3] == ["adb", "-s", "dev"]
    other = FakeAdb({"pm list": (0, f"package:{ra.PACKAGE}.pro\n", "")})
    assert phone(other).installed("dev") is False


def _pull_creates(count: int, root: str = "RunnerUp"):
    def make(cmd: list[str]) -> tuple[int, str, str]:
        folder = Path(cmd[-1]) / root
        folder.mkdir(parents=True)
        for i in range(count):
            (folder / f"r{i}.tcx").write_text("x")
        return 0, "", ""

    return make


def test_backup_stages_then_renames_and_counts(tmp_path: Path) -> None:
    fake = FakeAdb({"ls": (0, "a.tcx\nb.tcx\nb.gpx\n", ""), "pull": _pull_creates(2)})
    final = tmp_path / "backup_2026"
    target, count = phone(fake).backup("dev", final)
    assert (target, count) == (final, 2)
    assert len(list(final.glob("*.tcx"))) == 2
    assert not (tmp_path / "backup_2026.partial").exists()


def test_backup_never_overwrites_an_existing_folder(tmp_path: Path) -> None:
    final = tmp_path / "backup"
    final.mkdir()
    (tmp_path / "backup.partial").mkdir()  # a stale half-pull is cleared
    fake = FakeAdb({"ls": (0, "a.tcx\n", ""), "pull": _pull_creates(1)})
    target, _ = phone(fake).backup("dev", final)
    assert target == tmp_path / "backup-2"


def test_backup_short_pull_is_an_error_and_not_renamed(tmp_path: Path) -> None:
    fake = FakeAdb({"ls": (0, "a.tcx\nb.tcx\n", ""), "pull": _pull_creates(1)})
    with pytest.raises(ra.AdbError, match="pulled 1 of 2"):
        phone(fake).backup("dev", tmp_path / "b")
    assert not (tmp_path / "b").exists()


def test_backup_pull_that_creates_nothing_is_an_error(tmp_path: Path) -> None:
    fake = FakeAdb({"ls": (0, "a.tcx\n", "")})
    with pytest.raises(ra.AdbError, match="pulled -1 of 1"):
        phone(fake).backup("dev", tmp_path / "b")


def test_uninstall_succeeds_only_when_the_package_is_gone() -> None:
    fake = FakeAdb({"uninstall": (0, "Success\n", ""), "pm list": (0, "", "")})
    phone(fake).uninstall("dev")
    assert ["adb", "-s", "dev", "uninstall", ra.PACKAGE] in fake.calls


def test_uninstall_refusal_keeps_adbs_reason() -> None:
    fail = "Failure [DELETE_FAILED_DEVICE_POLICY_MANAGER]"
    fake = FakeAdb({"uninstall": (1, fail, "")})
    with pytest.raises(ra.AdbError, match="DELETE_FAILED_DEVICE_POLICY_MANAGER"):
        phone(fake).uninstall("dev")


def test_uninstall_without_success_text_is_an_error() -> None:
    fake = FakeAdb({"uninstall": (0, "weird\n", "")})
    with pytest.raises(ra.AdbError, match="did not report Success"):
        phone(fake).uninstall("dev")


def test_uninstall_that_leaves_the_package_is_an_error() -> None:
    fake = FakeAdb({"uninstall": (0, "Success\n", ""), "pm list": (0, PKG_LINE, "")})
    with pytest.raises(ra.AdbError, match="still listed"):
        phone(fake).uninstall("dev")


def test_state_roundtrip_and_anchor(tmp_path: Path) -> None:
    path = tmp_path / "deep" / "s.json"
    assert load_state(path) == RetireState()
    save_state(path, RetireState(anchor_at="2026-11-01T10:45:00+00:00"))
    assert load_state(path).anchor is not None
    assert RetireState().anchor is None


@pytest.mark.parametrize(
    "body", ["{nope", "[]", json.dumps({"anchor_at": "not a date"})]
)
def test_bad_state_is_loud_and_ignored(
    tmp_path: Path, body: str, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "s.json"
    path.write_text(body)
    with caplog.at_level("WARNING"):
        assert load_state(path) == RetireState()
    assert "Retire state" in caplog.text


def test_unreadable_state_is_loud(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("WARNING"):
        assert load_state(tmp_path) == RetireState()
    assert "unreadable" in caplog.text


def test_state_ignores_unknown_and_non_string_fields(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"done_at": 5, "extra": "x", "backup_path": "/b"}))
    assert load_state(path) == RetireState(backup_path="/b")
