"""RunnerUp retirement CLI: ``--status`` is read-only, exit codes follow outcomes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from screen_locker import runnerup_retire as cli
from screen_locker._runnerup_retire import Outcome, Paths, RetireResult
from screen_locker._runnerup_retire_adb import AdbError, Device
from screen_locker._runnerup_retire_state import RetireState, save_state
from screen_locker.tests._retire_helpers import put_marker
from screen_locker.tests.test_runnerup_retire import ANCHOR, DUE, RUN, FakePhone, world

if TYPE_CHECKING:
    from pathlib import Path


def _tree(root: Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*")}


def test_status_without_anchor(tmp_path: Path) -> None:
    paths = world(tmp_path, anchored=False, marker=False)
    lines = cli.status_lines(paths, FakePhone(), DUE)  # type: ignore[arg-type]
    assert lines[0].startswith("anchor: none")
    assert lines[1] == "due: never"
    assert "INVALID" in lines[2]
    assert lines[3] == "done: no"
    assert "not queried" in lines[4]


def test_status_is_strictly_read_only_and_marks_a_derived_anchor(
    tmp_path: Path,
) -> None:
    paths = world(tmp_path)
    before = _tree(tmp_path)
    lines = cli.status_lines(paths, FakePhone(), DUE - timedelta(days=1))  # type: ignore[arg-type]
    assert _tree(tmp_path) == before
    assert not paths.state_file.parent.exists()
    assert "derived, not yet stored" in lines[0]
    assert "2026-11-08 10:45 (+1.0 days)" in lines[1]
    assert lines[2] == "marker: valid (1 runs match)"


def test_status_with_stored_anchor_and_done(tmp_path: Path) -> None:
    paths = world(tmp_path, anchored=False)
    save_state(
        paths.state_file,
        RetireState(anchor_at=ANCHOR.isoformat(), done_at="2026-11-09T00:00:00+00:00"),
    )
    lines = cli.status_lines(paths, FakePhone(), DUE)  # type: ignore[arg-type]
    assert "(stored)" in lines[0]
    assert lines[3] == "done: 2026-11-09T00:00:00+00:00"


@pytest.mark.parametrize(
    ("phone", "expected"),
    [
        (FakePhone(present=True), "installed: yes"),
        (FakePhone(present=False), "installed: no"),
        (
            FakePhone(device=Device(None, "phone S is not attached")),
            "installed: unknown (phone S is not attached)",
        ),
        (FakePhone(ask_error=AdbError("boom")), "installed: unknown (boom)"),
    ],
)
def test_status_query_phone(tmp_path: Path, phone: FakePhone, expected: str) -> None:
    paths = world(tmp_path)
    lines = cli.status_lines(paths, phone, DUE, query_phone=True)  # type: ignore[arg-type]
    assert lines[4] == expected


def test_main_status_prints_and_exits_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["--status"]) == 0  # the isolated defaults: an empty world
    out = capsys.readouterr().out
    assert "anchor: none" in out
    assert "not queried" in out


def test_main_status_query_phone_uses_the_serial(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[str] = []

    def fake_phone(serial: str) -> FakePhone:
        seen.append(serial)
        return FakePhone()

    monkeypatch.setattr(cli, "Phone", fake_phone)
    assert cli.main(["--status", "--query-phone", "--serial", "XYZ"]) == 0
    assert seen == ["XYZ"]
    assert "installed: yes" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("outcome", "code"),
    [(Outcome.NOT_DUE, 0), (Outcome.DEVICE_ABSENT, 0), (Outcome.UNINSTALL_FAILED, 1)],
)
def test_main_exit_code_follows_the_outcome(
    monkeypatch: pytest.MonkeyPatch, outcome: Outcome, code: int
) -> None:
    calls: list[bool] = []

    def fake_run(paths: Paths, phone: object, *, dry_run: bool) -> RetireResult:
        calls.append(dry_run)
        return RetireResult(outcome, "why")

    monkeypatch.setattr(cli, "run_retire", fake_run)
    assert cli.main(["--dry-run"]) == code
    assert calls == [True]


def test_main_with_nothing_to_retire_is_a_clean_noop() -> None:
    assert cli.main([]) == 0


def test_status_marker_line_for_a_valid_marker_uses_real_files(
    tmp_path: Path,
) -> None:
    paths = world(tmp_path, marker=False)
    put_marker(paths.watch_dir, [RUN])
    now = datetime.now(UTC)
    assert cli.status_lines(paths, FakePhone(), now)[2].startswith("marker: valid")  # type: ignore[arg-type]
