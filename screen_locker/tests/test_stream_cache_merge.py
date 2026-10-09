"""Tests for _stream_cache: union merge, tombstones and the own-device rule."""

from __future__ import annotations

import json
import logging
import threading

import pytest

from screen_locker import _stream_cache
from screen_locker._rtdb_stream import SseEvent
from screen_locker._stream_cache import DeviceLogCache
from screen_locker.tests.test_stream_cache import (
    OWN,
    Credit,
    log_blob,
    patch_event,
    snapshot,
)


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


class TestMerge:
    """Union across devices, tombstones and the own-device rule."""

    def test_highest_hlc_copy_wins_across_devices(
        self, cache: DeviceLogCache, credit: Credit
    ) -> None:
        """One record mirrored in two device logs is credited once."""
        both = {"phone": log_blob("s1", wall=1), "tab": log_blob("s1", wall=5)}
        result = cache.handle(snapshot(both))
        assert credit.batches == [["s1"]]
        assert "1 session(s) checked" in result.summary

    def test_tombstone_on_another_device_drops_the_record(
        self, cache: DeviceLogCache, credit: Credit
    ) -> None:
        """A delete anywhere beats a live copy elsewhere: nothing is credited."""
        logs = {"phone": log_blob("s1"), "tab": log_blob("s1", deleted=True)}
        result = cache.handle(snapshot(logs))
        assert credit.batches == []
        assert "no-op" in result.summary

    def test_own_log_tombstone_still_suppresses_a_phone_session(
        self, cache: DeviceLogCache, credit: Credit
    ) -> None:
        """The PC's own log stays in the union: its tombstones must be honoured."""
        logs = {OWN: log_blob("s1", deleted=True), "phone": log_blob("s1")}
        cache.handle(snapshot(logs))
        assert credit.batches == []

    def test_event_touching_only_the_own_log_never_credits(
        self, cache: DeviceLogCache, credit: Credit
    ) -> None:
        """Our own push echoing back must not trigger a pass."""
        result = cache.handle(patch_event({OWN: log_blob("s9")}))
        assert credit.batches == []
        assert "only this PC's own log changed (pc-own); no credit" in result.summary
        assert result.snapshot is False

    def test_own_snapshot_is_still_processed(
        self, cache: DeviceLogCache, credit: Credit
    ) -> None:
        """A full snapshot always runs the union, even if only own logs differ."""
        cache.handle(snapshot({OWN: log_blob("s9")}))
        assert credit.batches == [["s9"]]

    def test_byte_identical_rewrite_does_nothing(
        self, cache: DeviceLogCache, credit: Credit
    ) -> None:
        """RTDB-style repeat of the same text: nothing to read or credit."""
        cache.handle(snapshot({"phone": log_blob("s1")}))
        result = cache.handle(patch_event({"phone": log_blob("s1")}))
        assert "byte-identical rewrite" in result.summary
        assert credit.batches == [["s1"]]

    def test_deleting_an_unknown_device_is_a_no_op(self, cache: DeviceLogCache) -> None:
        """A ``null`` for a device never cached changes nothing."""
        result = cache.handle(patch_event({"ghost": None}))
        assert "byte-identical rewrite" in result.summary

    def test_patch_null_removes_a_cached_device(
        self, cache: DeviceLogCache, credit: Credit
    ) -> None:
        """Deleting a device log drops it from the cache."""
        cache.handle(snapshot({"phone": log_blob("s1")}))
        result = cache.handle(patch_event({"phone": None}))
        assert "0 device log(s) cached, changed: phone" in result.summary
        assert credit.batches == [["s1"]]

    def test_snapshot_replaces_the_cache(self, cache: DeviceLogCache) -> None:
        """Devices missing from a new snapshot are gone, and reported changed."""
        cache.handle(snapshot({"a": log_blob("s1"), "b": log_blob("s2")}))
        result = cache.handle(snapshot({"a": log_blob("s1")}))
        assert "1 device log(s) cached, changed: b;" in result.summary

    def test_snapshot_ignores_devices_without_alog_blob(
        self, cache: DeviceLogCache
    ) -> None:
        """A device node with no text is not cached."""
        event = SseEvent(
            "put", json.dumps({"path": "/", "data": {"a": {"other": "x"}}})
        )
        result = cache.handle(event)
        assert "0 device log(s) cached" in result.summary

    def test_corrupt_log_is_skipped_with_a_warning(
        self,
        cache: DeviceLogCache,
        credit: Credit,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """One broken device log does not hide the others' sessions."""
        with caplog.at_level(logging.WARNING):
            cache.handle(snapshot({"bad": "not json", "phone": log_blob("s1")}))
        assert credit.batches == [["s1"]]
        assert any(
            "Corrupt sync data at sync/devices/bad/log.json" in r.getMessage()
            and r.levelno >= logging.WARNING
            for r in caplog.records
        )
