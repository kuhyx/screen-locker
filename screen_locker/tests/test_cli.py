"""Tests for screen_locker._cli, the command-line entry-point dispatcher.

This logic used to live in ``screen_lock.py``'s ``if __name__ == "__main__":``
block, which coverage excludes -- so it shipped untested. Splitting it into a
real module for the 250-line cap made it testable; these tests cover it.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar  # ClassVar is needed at runtime
from unittest.mock import patch

import pytest

from screen_locker import _cli

if TYPE_CHECKING:
    from collections.abc import Iterator


class _FakeLocker:
    """Stand-in for ScreenLocker recording how it was constructed."""

    instances: ClassVar[list[_FakeLocker]] = []

    def __init__(self, *, demo_mode: bool = True, verify_only: bool = False) -> None:
        self.demo_mode = demo_mode
        self.verify_only = verify_only
        self.ran = False
        self.log_file: Path | None = None
        self.workout_data: dict[str, str] | None = None
        self.synced = False
        _FakeLocker.instances.append(self)

    def run(self) -> None:
        """Record that the main loop was entered."""
        self.ran = True

    def sync_now(self) -> None:
        """Record that a sync pass was requested."""
        self.synced = True


@pytest.fixture(autouse=True)
def _reset_instances() -> Iterator[None]:
    """Clear the recorded instances before each test."""
    _FakeLocker.instances = []
    yield
    _FakeLocker.instances = []


class TestHeadlessLocker:
    """_headless_locker bypasses __init__ so no UI is ever built."""

    def test_bypasses_init_and_seeds_only_the_two_needed_fields(self) -> None:
        """Bypassing __init__ leaves only log_file and workout_data set."""
        locker = _cli._headless_locker(_FakeLocker)

        # __init__ never ran, so demo_mode/verify_only are absent entirely.
        assert not hasattr(locker, "demo_mode")
        assert not _FakeLocker.instances
        assert not locker.workout_data
        assert locker.log_file.name == "log.json"

    def test_log_file_sits_beside_the_package(self) -> None:
        """The workout log is resolved relative to the package directory."""
        locker = _cli._headless_locker(_FakeLocker)

        assert locker.log_file.parent == Path(_cli.__file__).resolve().parent


class TestStatusMode:
    """--status runs the status report against a headless locker."""

    def test_calls_run_status_without_constructing_a_ui(self) -> None:
        """--status reports via run_status and builds no locker."""
        # The real run_status ends in sys.exit(0), which is why main() needs
        # no `return` here; the fake reproduces that so the fall-through to
        # the UI locker is exercised exactly as it is in production.
        with (
            patch.object(_cli, "run_status", side_effect=SystemExit(0)) as run_status,
            pytest.raises(SystemExit) as excinfo,
        ):
            _cli.main(_FakeLocker, ["screen_lock.py", "--status"])

        assert not excinfo.value.code
        run_status.assert_called_once()
        passed = run_status.call_args[0][0]
        assert not passed.workout_data
        # No real locker was constructed for the status path.
        assert not _FakeLocker.instances


class TestSyncOnlyMode:
    """--sync-only runs one headless sync pass and exits 0.

    The suite-wide conftest fixture patches ``sys.exit`` to a no-op so a stray
    exit cannot kill the test run, so these assert on the call rather than on
    a raised SystemExit.
    """

    def test_syncs_then_exits_zero(self) -> None:
        """--sync-only configures logging and exits 0."""
        with (
            patch.object(_cli.logging, "basicConfig") as basic_config,
            patch.object(_cli.sys, "exit") as sys_exit,
        ):
            _cli.main(_FakeLocker, ["screen_lock.py", "--sync-only"])

        sys_exit.assert_called_once_with(0)
        basic_config.assert_called_once()

    def test_actually_calls_sync_now(self) -> None:
        """--sync-only runs exactly one sync pass."""
        synced: list[bool] = []

        class _Recorder(_FakeLocker):
            def sync_now(self) -> None:
                """Record the sync call."""
                synced.append(True)

        with (
            patch.object(_cli.logging, "basicConfig"),
            patch.object(_cli.sys, "exit"),
        ):
            _cli.main(_Recorder, ["screen_lock.py", "--sync-only"])

        assert synced == [True]


class TestLockMode:
    """With no subcommand flag, the real locker is built and run."""

    def test_defaults_to_demo_mode(self) -> None:
        """With no flags the locker is built in demo mode and run."""
        _cli.main(_FakeLocker, ["screen_lock.py"])

        locker = _FakeLocker.instances[-1]
        assert locker.demo_mode is True
        assert locker.verify_only is False
        assert locker.ran is True

    def test_production_flag_disables_demo_mode(self) -> None:
        """--production turns demo mode off."""
        _cli.main(_FakeLocker, ["screen_lock.py", "--production"])

        locker = _FakeLocker.instances[-1]
        assert locker.demo_mode is False
        assert locker.verify_only is False

    def test_verify_workout_flag_sets_verify_only(self) -> None:
        """--verify-workout sets verify_only."""
        _cli.main(_FakeLocker, ["screen_lock.py", "--verify-workout"])

        locker = _FakeLocker.instances[-1]
        assert locker.verify_only is True
        assert locker.demo_mode is True

    def test_production_and_verify_combine(self) -> None:
        """--production and --verify-workout apply together."""
        _cli.main(_FakeLocker, ["screen_lock.py", "--production", "--verify-workout"])

        locker = _FakeLocker.instances[-1]
        assert locker.demo_mode is False
        assert locker.verify_only is True


class TestScreenLockDelegation:
    """screen_lock.py's __main__ block delegates here rather than duplicating."""

    def test_main_is_exported(self) -> None:
        """main is the module's public entry point."""
        assert _cli.__all__ == ["main"]
        assert callable(_cli.main)


class TestLogManualWorkoutMode:
    """--log-manual-workout hands everything after the flag to the logger.

    Dispatch only: the field rules themselves are covered by
    ``test_manual_cli.py`` against the real validator.
    """

    def test_forwards_the_remaining_args_and_exits_with_its_code(self) -> None:
        """The flag's own name is not passed on, and the exit code is used."""
        seen: list[tuple[object, list[str]]] = []

        def _fake_run(log_file: object, argv: list[str]) -> int:
            """Record the call and report a refusal."""
            seen.append((log_file, list(argv)))
            return 1

        with (
            patch.object(_cli.logging, "basicConfig"),
            patch.object(_cli, "run_manual_log", _fake_run),
            patch.object(_cli.sys, "exit") as sys_exit,
        ):
            _cli.main(
                _FakeLocker,
                ["screen_lock.py", "--log-manual-workout", "--sport", "other"],
            )

        (log_file, argv) = seen[0]
        assert argv == ["--sport", "other"]
        assert log_file.name == "log.json"
        sys_exit.assert_called_once_with(1)

    def test_exits_before_reaching_the_lock_screen(self) -> None:
        """A successful log exits 0 rather than falling through to the UI.

        ``sys.exit`` is a no-op under the suite-wide fixture, so this asserts
        on the exit call: in the real process that call is what stops the
        headless path from continuing on to build a lock screen.
        """
        with (
            patch.object(_cli.logging, "basicConfig"),
            patch.object(_cli, "run_manual_log", lambda *_: 0),
            patch.object(_cli.sys, "exit") as sys_exit,
        ):
            _cli.main(_FakeLocker, ["screen_lock.py", "--log-manual-workout"])

        assert sys_exit.call_args_list[0].args == (0,)
