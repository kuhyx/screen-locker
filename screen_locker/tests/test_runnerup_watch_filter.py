"""scripts/runnerup_watch.sh starts workout-sync only for a FRESH upload.

endurain-import's adb fallback re-pulls every export it already moved into
``processed/`` and renames each into place, so one import fired ~27 events
and as many workout-sync starts (~370 on 2026-10-09). The script runs as a
black box here: ``inotifywait`` and ``systemctl`` are shims on PATH, the
first replaying a fixed event list, the second recording what was started.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "runnerup_watch.sh"
_UNIT = "workout-sync.service"
# conftest replaces subprocess.run process-wide for every test; this module
# needs the real one, captured at import time before any fixture runs.
_REAL_RUN = subprocess.run


def _shim(path: Path, body: str) -> None:
    path.write_text(f"#!/bin/bash\n{body}\n", encoding="utf-8")
    path.chmod(0o755)


def _run(
    tmp_path: Path, events: list[str], *, processed: list[str]
) -> tuple[list[str], str, int]:
    """Replay ``events`` through the watcher; return systemctl calls, stderr, rc."""
    watch = tmp_path / "RunnerUp"
    (watch / "processed").mkdir(parents=True)
    for name in processed:
        (watch / "processed" / name).write_text("<tcx/>", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    events_file = tmp_path / "events"
    events_file.write_text("".join(f"{e}\n" for e in events), encoding="utf-8")
    calls = tmp_path / "systemctl.calls"
    _shim(bin_dir / "inotifywait", f'cat "{events_file}"')
    _shim(
        bin_dir / "systemctl",
        f'echo "$*" >>"{calls}"\n[[ $2 == is-active ]] && echo inactive\nexit 0',
    )
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "RUNNERUP_WATCH_DIR": str(watch),
        "RUNNERUP_SYNC_UNIT": _UNIT,
    }
    done = _REAL_RUN(
        ["bash", str(_SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    lines = calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []
    return lines, done.stderr, done.returncode


def _starts(calls: list[str]) -> list[str]:
    return [c for c in calls if c.startswith("--user start")]


def test_a_fresh_upload_starts_the_sync(tmp_path: Path) -> None:
    """A new top-level TCX is credited at once."""
    calls, err, rc = _run(tmp_path, ["2026-10-09-run.tcx"], processed=[])
    assert _starts(calls) == [f"--user start {_UNIT}"]
    assert "RunnerUp upload finished: 2026-10-09-run.tcx" in err
    # inotifywait ending is a failure systemd must restart.
    assert rc == 1


def test_a_re_pulled_burst_starts_nothing_and_logs_once(tmp_path: Path) -> None:
    """Names already in processed/ are skipped, with one line per burst."""
    old = [f"2026-10-0{d}-run.tcx" for d in range(1, 6)]
    calls, err, _ = _run(tmp_path, old, processed=old)
    assert _starts(calls) == []
    assert err.count("Ignoring re-pulled") == 1


@pytest.mark.parametrize("name", [".2026-10-09-run.tcx", "notes.txt", "x.tcx.part"])
def test_partials_and_non_tcx_are_ignored(tmp_path: Path, name: str) -> None:
    """Dotfiles are partial transfers; anything not *.tcx is not a run."""
    calls, _, _ = _run(tmp_path, [name], processed=[])
    assert _starts(calls) == []


def test_fresh_upload_inside_a_re_pull_burst_still_counts(tmp_path: Path) -> None:
    """The filter must not swallow the one real upload among the re-pulls."""
    calls, _, _ = _run(
        tmp_path,
        ["old-a.tcx", "new.tcx", "old-b.tcx"],
        processed=["old-a.tcx", "old-b.tcx"],
    )
    assert _starts(calls) == [f"--user start {_UNIT}"]
