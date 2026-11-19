"""scripts/deploy.sh --phone-only: skip the phone when its app is unchanged.

A PC-only change (CI config, a Python pin) must deploy with the phone
unplugged: the workout app installed last time is byte-for-byte the same
source. The skip keys on the git tree of the app directory recorded after the
last successful phone install, so an app change is never skipped.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "scripts" / "deploy.sh"
APP_DIR = "stronglift_replacement/workout_app"
# conftest replaces subprocess.run process-wide for every test; this module
# needs the real one, captured at import time before any fixture runs.
_real_run = subprocess.run


def _git(repo: Path, *args: str) -> str:
    """Run git in ``repo`` and return its stripped stdout."""
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull}
    env.pop("GIT_DIR", None)
    out = _real_run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return out.stdout.strip()


@pytest.fixture(name="live")
def _live_repo(tmp_path: Path) -> Path:
    """A throwaway 'live clone' with one committed app file."""
    repo = tmp_path / "live"
    (repo / APP_DIR).mkdir(parents=True)
    (repo / APP_DIR / "pubspec.yaml").write_text("name: workout_app\n")
    _git(repo, "init", "-q")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "add", ".")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "c")
    return repo


def _fake_phone(tmp_path: Path, rc: int) -> tuple[Path, Path]:
    """A stand-in phone_deploy.sh exiting ``rc``; returns (script, call log)."""
    calls = tmp_path / "phone_calls"
    script = tmp_path / "phone_deploy.sh"
    script.write_text(f'#!/bin/bash\necho "$@" >> "{calls}"\nexit {rc}\n')
    return script, calls


def _run(live: Path, phone: Path, marker: Path) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "SCREEN_LOCKER_LIVE": str(live),
        "PHONE_DEPLOY": str(phone),
        "PHONE_APP_MARKER": str(marker),
    }
    env.pop("GIT_DIR", None)
    return _real_run(
        ["bash", str(DEPLOY), "--phone-only"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_unchanged_app_skips_unreachable_phone(live: Path, tmp_path: Path) -> None:
    """Recorded tree == current tree: exit 0 without touching the phone."""
    phone, calls = _fake_phone(tmp_path, 30)
    marker = tmp_path / "state" / "phone_app_tree"
    marker.parent.mkdir()
    marker.write_text(_git(live, "rev-parse", f"HEAD:{APP_DIR}") + "\n")
    result = _run(live, phone, marker)
    assert not result.returncode, result.stderr
    assert "unchanged" in result.stdout
    assert not calls.exists()


def test_changed_app_still_needs_the_phone(live: Path, tmp_path: Path) -> None:
    """A different recorded tree: phone_deploy runs and its exit 30 fails."""
    phone, calls = _fake_phone(tmp_path, 30)
    marker = tmp_path / "phone_app_tree"
    marker.write_text("0" * 40 + "\n")
    result = _run(live, phone, marker)
    assert result.returncode == 1
    assert calls.exists()
    assert "exited 30" in result.stderr


def test_no_marker_fails_closed(live: Path, tmp_path: Path) -> None:
    """No record of an install: the phone is required, not skipped."""
    phone, calls = _fake_phone(tmp_path, 30)
    result = _run(live, phone, tmp_path / "missing" / "phone_app_tree")
    assert result.returncode == 1
    assert calls.exists()


def test_install_records_the_tree(live: Path, tmp_path: Path) -> None:
    """A successful install writes the app tree, so the next deploy can skip."""
    phone, calls = _fake_phone(tmp_path, 0)
    marker = tmp_path / "state" / "phone_app_tree"
    result = _run(live, phone, marker)
    assert not result.returncode, result.stderr
    assert calls.exists()
    assert marker.read_text().strip() == _git(live, "rev-parse", f"HEAD:{APP_DIR}")
