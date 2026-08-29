"""Tests for the duplicate-credit ledger script.

The ledger is documentation, not behaviour -- nothing reads it to decide a
lock. Its one hard requirement is that it never contradicts
:func:`~screen_locker._weekly_check.count_day_credits`, because a ledger that
describes a different rule than the locker uses is worse than no ledger at all.
That invariant is enforced at runtime by ``check_ledger_agrees`` and pinned
here.
"""

from __future__ import annotations

import sys
from typing import Any, NoReturn

import pytest

from scripts.annotate_duplicate_credits import (
    build_ledger,
    check_ledger_agrees,
)


def _raising_exit(code: object = None) -> NoReturn:
    """Stand in for the real ``sys.exit``.

    Args:
        code: The exit status, as ``sys.exit`` takes.

    Raises:
        SystemExit: Always, exactly as ``sys.exit`` does.
    """
    raise SystemExit(code)


@pytest.fixture
def restore_sys_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give this test a ``sys.exit`` that actually exits.

    The autouse ``_block_real_tk_and_exit`` fixture in conftest patches
    ``screen_locker.screen_lock.sys.exit``. That attribute path resolves to the
    *global* ``sys`` module object, not a per-module copy, so the patch replaces
    ``sys.exit`` for every module in the process for the duration of every test
    -- including this script's. Without this fixture the guard under test is a
    no-op and the test passes for the wrong reason.

    Args:
        monkeypatch: pytest's attribute patcher, which undoes this on teardown.
    """
    monkeypatch.setattr(sys, "exit", _raising_exit)


def _entry(wtype: str, timestamp: str) -> dict[str, Any]:
    """Build a log entry with a workout_id, as the real writer does.

    Args:
        wtype: The ``workout_data.type`` value.
        timestamp: ISO-8601 timestamp.

    Returns:
        A log entry dict.
    """
    return {
        "timestamp": timestamp,
        "workout_data": {"type": wtype},
        "workout_id": f"{wtype}:{timestamp[:10]}",
    }


class TestBuildLedger:
    """The ledger names exactly the entries that share one credit."""

    def test_stronglifts_pair_is_recorded(self) -> None:
        """A phone/PC pair on one day becomes one ledger record."""
        logs = {
            "2026-08-24": [
                _entry("pc_workout_verified", "2026-08-24T10:55:29+00:00"),
                _entry("phone_verified", "2026-08-24T10:55:38+00:00"),
            ],
        }
        ledger = build_ledger(logs)
        assert list(ledger) == ["2026-08-24"]
        record = ledger["2026-08-24"][0]
        assert record["credit"] == "stronglifts"
        # Earliest timestamp is the canonical entry; the later copy is absorbed.
        assert record["counted"] == "pc_workout_verified:2026-08-24"
        assert record["duplicate_of"] == ["phone_verified:2026-08-24"]

    def test_days_without_a_shared_credit_are_absent(self) -> None:
        """Separate workouts produce no ledger entry at all."""
        logs = {
            "2026-08-24": [
                _entry("phone_verified", "2026-08-24T10:00:00+00:00"),
                _entry("runnerup_verified", "2026-08-24T19:00:00+00:00"),
            ],
            "2026-08-25": [_entry("manual_workout", "2026-08-25T10:00:00+00:00")],
        }
        assert build_ledger(logs) == {}

    def test_uncredited_entries_are_ignored(self) -> None:
        """A skip marker earns no credit, so it can never share one."""
        logs = {
            "2026-08-25": [
                _entry("relaxed_day_skip", "2026-08-25T18:00:00+00:00"),
                _entry("relaxed_day_skip", "2026-08-25T19:00:00+00:00"),
            ],
        }
        assert build_ledger(logs) == {}

    def test_entry_without_workout_id_falls_back_to_position(self) -> None:
        """Legacy entries predating workout_id are still nameable."""
        logs = {
            "2026-08-24": [
                {
                    "timestamp": "2026-08-24T10:00:00+00:00",
                    "workout_data": {"type": "phone_verified"},
                },
                {
                    "timestamp": "2026-08-24T11:00:00+00:00",
                    "workout_data": {"type": "pc_workout_verified"},
                },
            ],
        }
        record = build_ledger(logs)["2026-08-24"][0]
        assert record["counted"] == "2026-08-24#0"
        assert record["duplicate_of"] == ["2026-08-24#1"]


class TestLedgerAgreesWithTheCreditRule:
    """The ledger's arithmetic must match count_day_credits exactly."""

    def test_generated_ledger_agrees(self) -> None:
        """A ledger built from a log always agrees with that log."""
        logs = {
            "2026-08-24": [
                _entry("pc_workout_verified", "2026-08-24T10:55:29+00:00"),
                _entry("phone_verified", "2026-08-24T10:55:38+00:00"),
            ],
            "2026-08-27": [_entry("manual_workout", "2026-08-27T18:45:32+00:00")],
        }
        check_ledger_agrees(logs, build_ledger(logs))

    @pytest.mark.usefixtures("restore_sys_exit")
    def test_over_claiming_ledger_is_refused(self) -> None:
        """A ledger claiming a duplicate that is not one aborts the script."""
        logs = {
            "2026-08-24": [
                _entry("runnerup_verified", "2026-08-24T07:00:00+00:00"),
                _entry("runnerup_verified", "2026-08-24T19:00:00+00:00"),
            ],
        }
        hand_written = {
            "2026-08-24": [
                {
                    "credit": "runnerup_verified",
                    "counted": "runnerup_verified:2026-08-24",
                    "duplicate_of": ["runnerup_verified:2026-08-24"],
                    "note": "wrong: two runs in a day are two workouts",
                },
            ],
        }
        with pytest.raises(SystemExit, match="Ledger disagrees"):
            check_ledger_agrees(logs, hand_written)
