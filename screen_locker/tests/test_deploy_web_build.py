"""scripts/deploy.sh --web-only: rebuild web/dist when web/ changed.

The web server serves the built bundle at web/dist, which git ignores. A
deploy that only pulled and restarted kept serving whatever bundle was last
built by hand, so a merged web change (the kuhy credit footer) never went
live. The build keys on the git tree of web/ recorded after the last good
build, like the phone step, so a PC-only change does not pay for a rebuild.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "scripts" / "deploy.sh"
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
    """A throwaway 'live clone' with one committed web file."""
    repo = tmp_path / "live"
    (repo / "web").mkdir(parents=True)
    (repo / "web" / "package.json").write_text("{}\n")
    _git(repo, "init", "-q")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "add", ".")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "c")
    return repo


def _fake_pnpm(tmp_path: Path, rc: int) -> tuple[Path, Path]:
    """A stand-in pnpm exiting ``rc``; returns (script, call log)."""
    calls = tmp_path / "pnpm_calls"
    script = tmp_path / "pnpm"
    script.write_text(f'#!/bin/bash\necho "$@" >> "{calls}"\nexit {rc}\n')
    script.chmod(0o755)
    return script, calls


def _run(live: Path, pnpm: Path, marker: Path) -> subprocess.CompletedProcess[str]:
    """Run ``deploy.sh --web-only`` against ``live`` with a fake pnpm."""
    env = {
        **os.environ,
        "SCREEN_LOCKER_LIVE": str(live),
        "WEB_PNPM": str(pnpm),
        "WEB_BUILD_MARKER": str(marker),
    }
    env.pop("GIT_DIR", None)
    return _real_run(
        ["bash", str(DEPLOY), "--web-only"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_changed_web_is_built_and_recorded(live: Path, tmp_path: Path) -> None:
    """No record yet: install + build run and the web tree is recorded."""
    pnpm, calls = _fake_pnpm(tmp_path, 0)
    marker = tmp_path / "state" / "web_tree"
    result = _run(live, pnpm, marker)
    assert not result.returncode, result.stderr
    lines = calls.read_text().splitlines()
    assert lines[0].endswith("install --frozen-lockfile")
    assert lines[1].endswith("run build")
    assert marker.read_text().strip() == _git(live, "rev-parse", "HEAD:web")


def test_unchanged_web_skips_the_build(live: Path, tmp_path: Path) -> None:
    """Recorded tree == current tree: exit 0 without running pnpm."""
    pnpm, calls = _fake_pnpm(tmp_path, 0)
    marker = tmp_path / "web_tree"
    marker.write_text(_git(live, "rev-parse", "HEAD:web") + "\n")
    result = _run(live, pnpm, marker)
    assert not result.returncode, result.stderr
    assert "unchanged" in result.stdout
    assert not calls.exists()


def test_failed_build_fails_and_records_nothing(live: Path, tmp_path: Path) -> None:
    """pnpm fails: the deploy fails loudly and the next one retries the build."""
    pnpm, _ = _fake_pnpm(tmp_path, 1)
    marker = tmp_path / "web_tree"
    result = _run(live, pnpm, marker)
    assert result.returncode == 1
    assert "web" in result.stderr
    assert not marker.exists()
