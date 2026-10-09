"""Tests for _stream_cache: merge, tombstones, own-device rule and crediting."""

from __future__ import annotations

import json
import logging
import threading
from typing import TYPE_CHECKING

from crdt_sync import Hlc, Record
import pytest

from screen_locker import _stream_cache
from screen_locker._poke_credit import BatchOutcome
from screen_locker._rtdb_stream import SseEvent
from screen_locker._stream_cache import DeviceLogCache

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

_LEAF = "log~2Ejson"
OWN = "pc-own"
_PAYLOAD = {"exercises": [], "date": "2026-10-09"}


def log_blob(
    rid: str, *, wall: int = 1, deleted: bool = False, payload: object = None
) -> str:
    """One device-log blob holding a single (possibly tombstoned) record."""
    hlc = Hlc(wall, 0, "n")
    record = Record(
        rid,
        {"payload": (_PAYLOAD if payload is None else payload, hlc)},
        deleted=deleted,
        deleted_hlc=hlc if deleted else None,
    )
    return json.dumps({rid: record.to_dict()})


def snapshot(logs: Mapping[str, str]) -> SseEvent:
    """A ``put /`` carrying every device log."""
    data = {dev: {_LEAF: text} for dev, text in logs.items()}
    return SseEvent("put", json.dumps({"path": "/", "data": data}))


def patch_event(logs: Mapping[str, str | None]) -> SseEvent:
    """A ``patch /`` rewriting some device logs (``None`` deletes one)."""
    data = {f"{dev}/{_LEAF}": text for dev, text in logs.items()}
    return SseEvent("patch", json.dumps({"path": "/", "data": data}))


class Credit:
    """Stand-in for ``credit_sessions`` that records every batch it is handed."""

    def __init__(self) -> None:
        self.batches: list[list[str]] = []
        self.error: Exception | None = None
        self.gate_held: list[bool] = []
        self.gate: threading.Lock | None = None

    def __call__(
        self, records: Iterable[tuple[str, Mapping[str, object]]]
    ) -> BatchOutcome:
        if self.gate is not None:
            self.gate_held.append(self.gate.locked())
        if self.error is not None:
            raise self.error
        ids = [rid for rid, _payload in records]
        self.batches.append(ids)
        return BatchOutcome(ingested=tuple(ids), credited=len(ids))


@pytest.fixture
def credit(monkeypatch: pytest.MonkeyPatch) -> Credit:
    """Replace the real (locker-building) credit step with a recorder."""
    fake = Credit()
    monkeypatch.setattr(_stream_cache._poke_credit, "credit_sessions", fake)
    return fake


@pytest.fixture
def cache(credit: Credit) -> DeviceLogCache:
    """A cache whose own device dir is ``pc-own``."""
    gate = threading.Lock()
    credit.gate = gate
    return DeviceLogCache("sync/devices", frozenset({OWN}), gate)


class TestCredit:
    """Which events credit, and how."""

    def test_snapshot_credits_foreign_sessions_under_the_gate(
        self, cache: DeviceLogCache, credit: Credit
    ) -> None:
        """A phone session in the snapshot is credited while the lock is held."""
        result = cache.handle(snapshot({"phone": log_blob("s1")}))
        assert result.snapshot is True
        assert credit.batches == [["s1"]]
        assert credit.gate_held == [True]
        assert (
            "1 session(s) checked, 1 newly logged ['s1'], 1 credited" in result.summary
        )

    def test_patch_credits_a_new_session(
        self, cache: DeviceLogCache, credit: Credit
    ) -> None:
        """A later patch for the phone credits only what is new."""
        cache.handle(snapshot({"phone": log_blob("s1")}))
        result = cache.handle(patch_event({"phone": log_blob("s2")}))
        assert result.snapshot is False
        assert credit.batches == [["s1"], ["s2"]]

    def test_already_handed_sessions_are_a_no_op(
        self, cache: DeviceLogCache, credit: Credit
    ) -> None:
        """Re-streaming the same snapshot costs no second credit call."""
        cache.handle(snapshot({"phone": log_blob("s1")}))
        result = cache.handle(snapshot({"phone": log_blob("s1")}))
        assert credit.batches == [["s1"]]
        assert "no-op, no file I/O" in result.summary
        assert result.snapshot is True

    def test_a_newer_hlc_of_the_same_record_is_credited_again(
        self, cache: DeviceLogCache, credit: Credit
    ) -> None:
        """The seen-set is keyed on (id, hlc): an edit is a new thing to check."""
        cache.handle(snapshot({"phone": log_blob("s1", wall=1)}))
        cache.handle(patch_event({"phone": log_blob("s1", wall=2)}))
        assert credit.batches == [["s1"], ["s1"]]

    def test_non_session_records_are_not_credited(
        self, cache: DeviceLogCache, credit: Credit
    ) -> None:
        """A record without ``exercises`` (e.g. runnerup_verified) is skipped."""
        cache.handle(snapshot({"phone": log_blob("v1", payload={"kind": "x"})}))
        assert credit.batches == []


class TestFailures:
    """Nothing is swallowed silently; nothing is marked seen on failure."""

    def test_credit_failure_is_logged_and_retried_next_event(
        self,
        cache: DeviceLogCache,
        credit: Credit,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A crediting error logs at ERROR, keeps the stream, retries later."""
        credit.error = RuntimeError("disk full")
        with caplog.at_level(logging.WARNING):
            result = cache.handle(snapshot({"phone": log_blob("s1")}))
        assert result.summary == "crediting failed (see above)"
        assert result.snapshot is True
        failures = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert failures
        assert failures[0].exc_info is not None
        assert "Crediting 1 streamed session(s) failed" in failures[0].getMessage()
        credit.error = None
        cache.handle(snapshot({"phone": log_blob("s1")}))
        assert credit.batches == [["s1"]]

    def test_bad_json_propagates_for_the_caller_to_warn(
        self, cache: DeviceLogCache
    ) -> None:
        """Undecodable events are the connection's to report, not ours to eat."""
        with pytest.raises(json.JSONDecodeError):
            cache.handle(SseEvent("put", "{nope"))
        with pytest.raises(TypeError, match="without a path"):
            cache.handle(SseEvent("put", "[]"))
