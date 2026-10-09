"""``--help`` answers and exits; an unknown flag is a usage error.

Before this, both fell through to building the demo lock screen. Split from
``test_cli.py`` for the 250-line cap. ``sys.exit`` is a no-op suite-wide (see
conftest), so each test installs one that really raises ``SystemExit``.
"""
# pylint: disable=protected-access

from __future__ import annotations

from typing import TYPE_CHECKING, NoReturn, cast

import pytest

from screen_locker import _cli

if TYPE_CHECKING:
    from screen_locker.screen_lock import ScreenLocker


def _really_exit(code: int = 0) -> NoReturn:
    raise SystemExit(code)


@pytest.fixture(autouse=True)
def _exiting_sys_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_cli.sys, "exit", _really_exit)


class _NeverBuilt:
    """A locker class whose construction would mean the guard failed."""

    def __init__(self, *_: object, **__: object) -> None:
        msg = "the lock screen must not be built"
        raise AssertionError(msg)


def _main(argv: list[str]) -> None:
    locker_cls = cast("type[ScreenLocker]", _NeverBuilt)
    _cli.main(locker_cls, ["screen_lock.py", *argv])


@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_help_prints_usage_and_exits_zero(
    flag: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Help goes to stdout and the process exits 0 before any UI."""
    with pytest.raises(SystemExit) as exited:
        _main(["--production", flag])
    assert exited.value.code == 0
    out = capsys.readouterr().out
    assert out.startswith("usage: python3 -m screen_locker.screen_lock")


def test_unknown_flag_is_exit_two_with_usage(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A typo is named on stderr with the usage, and exits 2."""
    with pytest.raises(SystemExit) as exited:
        _main(["--prodution"])
    assert exited.value.code == 2
    err = capsys.readouterr().err
    assert "unknown argument(s): --prodution" in err
    assert "usage:" in err


def test_subcommand_args_are_not_judged_here() -> None:
    """Everything after a trailing-arg subcommand belongs to its own parser."""
    assert (
        _cli._own_args(["screen_lock.py", "--log-manual-workout", "--help", "--weird"])
        == []
    )
    assert _cli._own_args(["screen_lock.py", "--status"]) == ["--status"]
