"""The gatelock version gate install.sh runs (scripts/gatelock_pin.py)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from scripts import gatelock_pin as gp

if TYPE_CHECKING:
    from pathlib import Path

PIN = "gatelock @ git+https://github.com/kuhyx/utils@gatelock-v0.16.2#subdirectory=gatelock"


def _repo(root: Path, dep: str = PIN) -> Path:
    path = root / "pyproject.toml"
    path.write_text(f'[project]\ndependencies = [\n    "{dep}",\n]\n', encoding="utf-8")
    return path


def _clone(root: Path, version: str) -> Path:
    clone = root / "gatelock"
    clone.mkdir()
    (clone / "pyproject.toml").write_text(
        f'[project]\nname = "gatelock"\nversion = "{version}"\n', encoding="utf-8"
    )
    return clone


def test_pinned_version_reads_the_tag(tmp_path: Path) -> None:
    """The pin's tag is the version."""
    assert gp.pinned_version(_repo(tmp_path)) == (0, 16, 2)


def test_pinned_version_without_a_gatelock_pin(tmp_path: Path) -> None:
    """No gatelock dependency is an error, not a pass."""
    with pytest.raises(gp.PinError, match="no gatelock"):
        gp.pinned_version(_repo(tmp_path, "requests==2.0.0"))


@pytest.mark.parametrize(
    ("version", "code"), [("0.16.0", 1), ("0.16.2", 0), ("0.17.0", 0)]
)
def test_clone_ok_compares_against_the_pin(
    tmp_path: Path, version: str, code: int, caplog: pytest.LogCaptureFixture
) -> None:
    """A clone older than the pin must not be made editable."""
    # 2026-11-27: a stale ~/src/utils clone (0.16.0) was re-asserted over the
    # 0.16.2 pin, and the fix never reached the lock.
    repo, clone = _repo(tmp_path), _clone(tmp_path, version)
    assert gp.main(["clone-ok", str(repo), str(clone)]) == code
    if code:
        assert "older than the pin" in caplog.text


def test_clone_ok_unreadable_clone(tmp_path: Path) -> None:
    """A missing clone fails closed."""
    repo = _repo(tmp_path)
    assert gp.main(["clone-ok", str(repo), str(tmp_path / "missing")]) == gp.EXIT_ERROR


def test_installed_ok(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The imported gatelock is checked against the pin."""
    repo = _repo(tmp_path)
    monkeypatch.setattr(gp, "installed_version", lambda: (0, 16, 2))
    assert gp.main(["installed-ok", str(repo)]) == gp.EXIT_OK
    monkeypatch.setattr(gp, "installed_version", lambda: (0, 16, 0))
    assert gp.main(["installed-ok", str(repo)]) == 1


def test_installed_version_is_the_running_one() -> None:
    """The real metadata lookup returns a version."""
    assert gp.installed_version() >= (0, 1, 0)


def test_spec_prints_the_pin(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Spec prints the exact pinned dependency for pip."""
    assert gp.main(["spec", str(_repo(tmp_path))]) == gp.EXIT_OK
    assert capsys.readouterr().out.strip() == PIN


def test_bad_usage(tmp_path: Path) -> None:
    """Unknown or short commands are usage errors."""
    assert gp.main(["nope"]) == gp.EXIT_ERROR
    assert gp.main(["clone-ok", str(_repo(tmp_path))]) == gp.EXIT_ERROR


def test_bad_version_text(tmp_path: Path) -> None:
    """A non-numeric version fails closed."""
    repo, clone = _repo(tmp_path), _clone(tmp_path, "abc")
    assert gp.main(["clone-ok", str(repo), str(clone)]) == gp.EXIT_ERROR
