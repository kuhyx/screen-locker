"""``preview_shutdown --sequence`` simulates a review credit (earned_time 0.23).

The review is a top-up that joins the registry only from ``REVIEW_FROM``
(``earners_for(day)``), so a lookup in the static ``EARNERS`` tuple raised
``KeyError: 'review'``. The preview must look earners up in the simulated
day's registry, and reject a name not in force that day with a usage error.
"""

from __future__ import annotations

from datetime import timedelta
import sys

import earned_time
import pytest

from screen_locker import _earned, _grace_floor, _shutdown, _sick_floor
from screen_locker._earned import hhmm
from scripts import preview_shutdown

_REVIEW_DAY = earned_time.REVIEW_FROM.isoformat()
# The last day before the review joined the registry.
_EVE = (earned_time.REVIEW_FROM - timedelta(days=1)).isoformat()
# conftest stubs ``sys.exit`` process-wide; argparse's usage error needs the
# real one, captured at import (before the autouse stub).
_real_exit = sys.exit


@pytest.fixture(autouse=True)
def _restore_patched_globals(monkeypatch: pytest.MonkeyPatch) -> None:
    """The script rebinds module globals with ``vars()``; undo them afterwards."""
    for module in (_grace_floor, _shutdown, _sick_floor):
        for name in ("today_str", "GRACE_STATE_FILE", "sick_target"):
            if name in vars(module):
                monkeypatch.setattr(module, name, vars(module)[name])
    for name, module in tuple(sys.modules.items()):
        if name.startswith("sickdays.") and "resolve_paths" in vars(module):
            monkeypatch.setattr(module, "resolve_paths", vars(module)["resolve_paths"])
    monkeypatch.setattr(_earned, "LEDGER_HOME", _earned.LEDGER_HOME)
    monkeypatch.setattr(sys, "exit", _real_exit)


def _run(monkeypatch: pytest.MonkeyPatch, *argv: str) -> int:
    monkeypatch.setattr(sys, "argv", ["preview_shutdown", *argv])
    return preview_shutdown.main()


def _lines(text: str) -> dict[str, str]:
    """``step -> rest`` for each ``    name@HH:MM: ...`` sequence line."""
    out = {}
    for line in text.splitlines():
        step, sep, rest = line.strip().partition(": config ")
        if sep:
            out[step] = rest
    return out


def _start(text: str) -> int:
    line = next(x for x in text.splitlines() if x.startswith("[sequence]"))
    hours, minutes = line.split(" start ")[1].split()[0].split(":")
    return int(hours) * 60 + int(minutes)


def test_preview_review_sequence_adds_flat_review_minutes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """C1: a review on its first day adds its flat minutes, live == derived."""
    _run(monkeypatch, "--day", _REVIEW_DAY, "--sequence", "review@21:00")
    out = capsys.readouterr().out
    want = hhmm(_start(out) + earned_time.REVIEW_SHUTDOWN_MINUTES)
    assert _lines(out) == {"review@21:00": f"{want} (derived {want})"}


def test_preview_review_sequence_stacks_with_leetcode(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """C2: review then LeetCode stack, and every step matches the derivation."""
    steps = "review@21:00,leetcode@21:30"
    _run(monkeypatch, "--day", _REVIEW_DAY, "--sequence", steps)
    out = capsys.readouterr().out
    after_review = _start(out) + earned_time.REVIEW_SHUTDOWN_MINUTES
    after_leetcode = after_review + earned_time.earner("leetcode").shutdown_minutes
    first, second = hhmm(after_review), hhmm(after_leetcode)
    assert _lines(out) == {
        "review@21:00": f"{first} (derived {first})",
        "leetcode@21:30": f"{second} (derived {second})",
    }
    assert "MISMATCH" not in out


def test_preview_review_sequence_before_review_from_is_a_usage_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """C3: the day before the review existed exits 2 with a one-line reason."""
    with pytest.raises(SystemExit) as raised:
        _run(monkeypatch, "--day", _EVE, "--sequence", "review@21:00")
    assert raised.value.code == 2
    err = capsys.readouterr().err
    assert "review" in err
    assert _EVE in err
    assert "Traceback" not in err
    assert "KeyError" not in err
