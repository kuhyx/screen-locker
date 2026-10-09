"""A sandbox poke is verified and answered, but writes and credits nothing."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from screen_locker import _poke_credit, _poke_server
from screen_locker._poke_credit import PokeLocker
from screen_locker._poke_wire import PokeRequest

if TYPE_CHECKING:
    from pathlib import Path

_LOCKER_STEPS = (
    "start_the_day",
    "credit_written",
    "_write_shutdown_config",
    "_adjust_shutdown_time_later",
    "_apply_credit_for_written_entry",
)


def _request(*, sandbox: bool) -> PokeRequest:
    return PokeRequest(
        sent_at_ms=1,
        nonce="n",
        sandbox=sandbox,
        record_id="rec-1",
        payload={"date": "2026-10-09"},
    )


@pytest.fixture
def pc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, MagicMock]:
    """A real PokeLocker on a tmp log with every state-changing step spied."""

    def headless(locker_cls: type[PokeLocker]) -> PokeLocker:
        locker = object.__new__(locker_cls)
        locker.log_file = tmp_path / "log.json"
        return locker

    spies = {name: MagicMock() for name in (*_LOCKER_STEPS, "ingest", "credit")}
    for name in _LOCKER_STEPS:
        monkeypatch.setattr(PokeLocker, name, spies[name])
    monkeypatch.setattr(_poke_credit, "_headless_locker", headless)
    monkeypatch.setattr(_poke_credit, "ingest_session_records", spies["ingest"])
    monkeypatch.setattr(_poke_credit, "credit_session", spies["credit"])
    monkeypatch.setattr(_poke_credit, "current_shutdown", lambda: "20:30")
    monkeypatch.setattr(_poke_credit, "current_gaming_minutes", lambda _p: 75)
    return spies


def test_sandbox_replies_ok_with_the_snapshot_and_nothing_credited(
    pc: dict[str, MagicMock],
) -> None:
    reply = _poke_server._process(_request(sandbox=True))
    assert reply["ok"] is True
    assert reply["sandbox"] is True
    assert reply["credited"] is False
    assert reply["duplicate"] is False
    assert reply["shutdown"] == "20:30"
    assert reply["gaming_budget_minutes"] == 75
    assert "nothing written or credited" in str(reply["reason"])


def test_sandbox_never_logs_credits_or_touches_the_shutdown_config(
    pc: dict[str, MagicMock], tmp_path: Path
) -> None:
    before = sorted(p.name for p in tmp_path.iterdir())
    _poke_server._process(_request(sandbox=True))
    for name, spy in pc.items():
        assert not spy.called, name
    assert sorted(p.name for p in tmp_path.iterdir()) == before
    assert not (tmp_path / "log.json").exists()


def test_a_real_poke_does_reach_the_credit_step(pc: dict[str, MagicMock]) -> None:
    """Guards the guard: the spies above are wired to the path a real poke takes."""
    pc["credit"].return_value = _poke_credit.PokeOutcome(
        ok=True, credited=True, duplicate=False, reason="workout credited"
    )
    reply = _poke_server._process(_request(sandbox=False))
    assert reply["credited"] is True
    pc["credit"].assert_called_once_with("rec-1", {"date": "2026-10-09"})
