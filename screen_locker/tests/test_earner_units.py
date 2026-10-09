"""Tests for the ledger watch (``_earner_units``) and the bonus lock."""

from __future__ import annotations

import fcntl
import subprocess
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from screen_locker import _earner_units
from screen_locker._bonus_lock import bonus_lock
from screen_locker._earned import flat_earners, ledger_file, watched_earners
from screen_locker._shutdown_base import (
    apply_flat_bonuses_if_new,
    reset_to_base_if_new_day,
)

if TYPE_CHECKING:
    from pathlib import Path


def _installed(unit_dir: Path, text: str) -> Path:
    """Write *text* as the installed path unit and return its path."""
    unit_dir.mkdir(parents=True, exist_ok=True)
    unit = unit_dir / _earner_units.PATH_UNIT_NAME
    unit.write_text(text, encoding="utf-8")
    return unit


class TestRenderPathUnit:
    """The unit watches exactly the registry's flat ledgers."""

    def test_one_path_changed_per_flat_earner(self) -> None:
        """Every flat earner's ledger is watched, in registry order."""
        lines = _earner_units.render_path_unit().splitlines()
        watched = [ln.removeprefix("PathChanged=") for ln in lines if "=" in ln]
        expected = [str(ledger_file(e)) for e in flat_earners()]
        assert [w for w in watched if w in expected] == expected

    def test_one_path_changed_per_gate_ledger_of_every_registry(self) -> None:
        """Today's and the cutover's gates (the tutor), each ledger once."""
        lines = _earner_units.render_path_unit().splitlines()
        watched = [ln.removeprefix("PathChanged=") for ln in lines if "=" in ln]
        expected = list(dict.fromkeys(str(ledger_file(e)) for e in watched_earners()))
        assert [w for w in watched if w.startswith("/")] == expected
        assert sum(ln.startswith("PathChanged=") for ln in lines) == len(expected)

    def test_never_path_modified(self) -> None:
        """PathModified would fire on a half-written ledger."""
        assert "PathModified" not in _earner_units.render_path_unit()

    def test_is_installable(self) -> None:
        """An [Install] section, so `enable` has a target."""
        assert "[Install]\nWantedBy=default.target" in _earner_units.render_path_unit()


class TestSyncPathUnit:
    """The sync pass repairs a drifted unit and leaves an absent one alone."""

    def test_absent_unit_is_not_installed(self, tmp_path: Path) -> None:
        """Removed on purpose stays removed."""
        with patch.object(_earner_units.subprocess, "run") as run:
            assert _earner_units.sync_path_unit(tmp_path) is False
        run.assert_not_called()
        assert not (tmp_path / _earner_units.PATH_UNIT_NAME).exists()

    def test_defaults_to_the_patched_user_unit_dir(self) -> None:
        """No argument reads USER_UNIT_DIR at call time (conftest: empty)."""
        assert _earner_units.sync_path_unit() is False

    def test_current_unit_is_left_alone(self, tmp_path: Path) -> None:
        """No drift, no write, no daemon-reload."""
        _installed(tmp_path, _earner_units.render_path_unit())
        with patch.object(_earner_units.subprocess, "run") as run:
            assert _earner_units.sync_path_unit(tmp_path) is False
        run.assert_not_called()

    def test_drifted_unit_is_rewritten_and_reloaded(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A missing watch is restored, systemd reloaded, and it says so."""
        unit = _installed(tmp_path, "[Path]\nPathChanged=/old\n")
        with patch.object(_earner_units.subprocess, "run") as run:
            assert _earner_units.sync_path_unit(tmp_path) is True
        assert unit.read_text(encoding="utf-8") == _earner_units.render_path_unit()
        run.assert_called_once_with(
            ["/usr/bin/systemctl", "--user", "daemon-reload"],
            check=True,
            capture_output=True,
        )
        assert "out of date" in caplog.text

    def test_failed_reload_is_loud(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A reload that fails is a warning, not a silent False."""
        _installed(tmp_path, "stale")
        err = subprocess.CalledProcessError(1, "systemctl")
        with patch.object(_earner_units.subprocess, "run", side_effect=err):
            assert _earner_units.sync_path_unit(tmp_path) is False
        assert "could not be refreshed" in caplog.text

    def test_unreadable_unit_is_loud(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """An OSError reading the unit is a warning too."""
        _installed(tmp_path, "stale")
        with patch.object(
            _earner_units.Path, "read_text", side_effect=OSError("denied")
        ):
            assert _earner_units.sync_path_unit(tmp_path) is False
        assert "denied" in caplog.text


class TestBonusLock:
    """Both bonus writers hold one exclusive lock beside the state file."""

    def test_takes_and_releases_an_exclusive_lock(self, tmp_path: Path) -> None:
        """LOCK_EX for the body, LOCK_UN afterwards, on the .lock file."""
        state = tmp_path / "shutdown_base.json"
        with patch.object(fcntl, "flock") as flock:
            with bonus_lock(state):
                assert flock.call_args.args[1] == fcntl.LOCK_EX
            assert flock.call_args.args[1] == fcntl.LOCK_UN
        assert (tmp_path / "shutdown_base.lock").exists()

    def test_released_when_the_body_raises(self, tmp_path: Path) -> None:
        """An exception inside still unlocks."""
        with patch.object(fcntl, "flock") as flock:
            with pytest.raises(RuntimeError), bonus_lock(tmp_path / "s.json"):
                raise RuntimeError
            assert flock.call_args.args[1] == fcntl.LOCK_UN

    def test_held_by_the_live_pass(self, tmp_path: Path) -> None:
        """apply_flat_bonuses_if_new runs under the lock."""
        state = tmp_path / "s.json"
        seen: list[bool] = []
        with (
            patch(
                "screen_locker._shutdown_base.bonus_lock",
                return_value=MagicMock(__enter__=lambda _s: seen.append(True)),
            ) as lock,
            patch("screen_locker._shutdown_base.flat_earners", return_value=()),
        ):
            apply_flat_bonuses_if_new(state, MagicMock())
        lock.assert_called_once_with(state)
        assert seen == [True]

    def test_held_by_the_daily_reset(self, tmp_path: Path) -> None:
        """reset_to_base_if_new_day runs under the lock."""
        state = tmp_path / "s.json"
        with (
            patch("screen_locker._shutdown_base.bonus_lock") as lock,
            patch("screen_locker._shutdown_base._reset", return_value=True) as reset,
        ):
            assert reset_to_base_if_new_day(state, object()) is True
        lock.assert_called_once_with(state)
        reset.assert_called_once_with(state, reset.call_args.args[1], None, None)
