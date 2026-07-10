"""Tests for the phone-workout GitHub sync pull (crdt-sync transport)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from crdt_sync import GitHubSyncError, Hlc, Record
import pytest

from screen_locker import _workout_sync

# The autouse `_isolate_sync_token` fixture in conftest.py already redirects
# `_workout_sync.SYNC_TOKEN_FILE` into a per-test tmp_path, so tests here can
# write to it directly without needing their own isolation fixture.


def _record_json(payload: dict, *, wall_time_ms: int = 1000) -> dict:
    hlc = Hlc(wall_time_ms=wall_time_ms, counter=0, node_id="phone")
    record = Record(id="x", fields={"payload": (payload, hlc)})
    return record.to_dict()


class TestReadSyncToken:
    def test_returns_none_when_file_is_missing(self) -> None:
        assert _workout_sync.read_sync_token() is None

    def test_returns_none_when_file_is_empty(self) -> None:
        _workout_sync.SYNC_TOKEN_FILE.write_text("   \n")
        assert _workout_sync.read_sync_token() is None

    def test_returns_the_stripped_token(self) -> None:
        _workout_sync.SYNC_TOKEN_FILE.write_text("  abc123  \n")
        assert _workout_sync.read_sync_token() == "abc123"


class TestLatestPayload:
    def test_returns_none_for_an_empty_log(self) -> None:
        assert _workout_sync._latest_payload("{}") is None

    def test_returns_the_only_records_payload(self) -> None:
        log = {"a": _record_json({"succeeded": True})}
        assert _workout_sync._latest_payload(json.dumps(log)) == {"succeeded": True}

    def test_returns_the_payload_with_the_greatest_clock(self) -> None:
        log = {
            "old": _record_json({"succeeded": False}, wall_time_ms=100),
            "new": _record_json({"succeeded": True}, wall_time_ms=200),
        }
        assert _workout_sync._latest_payload(json.dumps(log)) == {"succeeded": True}

    def test_skips_records_with_no_payload_field(self) -> None:
        no_payload = Record(
            id="a",
            fields={"other": (1, Hlc(wall_time_ms=1, counter=0, node_id="phone"))},
        )
        log = {"a": no_payload.to_dict()}
        assert _workout_sync._latest_payload(json.dumps(log)) is None

    def test_raises_type_error_when_top_level_is_not_an_object(self) -> None:
        with pytest.raises(TypeError, match="not a JSON object"):
            _workout_sync._latest_payload(json.dumps([1, 2, 3]))

    def test_raises_type_error_when_payload_field_is_not_an_object(self) -> None:
        log = {"a": _record_json("not-a-dict")}
        with pytest.raises(TypeError, match="payload field is not a JSON object"):
            _workout_sync._latest_payload(json.dumps(log))

    def test_raises_key_error_for_a_malformed_record(self) -> None:
        log = {"a": {"id": "a"}}  # missing "fields"
        with pytest.raises(KeyError):
            _workout_sync._latest_payload(json.dumps(log))

    def test_raises_value_error_for_invalid_json(self) -> None:
        with pytest.raises(ValueError, match="Expecting property name"):
            _workout_sync._latest_payload("{not valid json")


def _mock_client(*, get_file_text: object) -> MagicMock:
    client = MagicMock()
    if isinstance(get_file_text, Exception):
        client.get_file_text.side_effect = get_file_text
    else:
        client.get_file_text.return_value = get_file_text
    return client


class TestPullSyncedWorkout:
    def test_returns_none_none_when_no_token_is_configured(self) -> None:
        with patch.object(_workout_sync, "GitHubSyncClient") as client_cls:
            assert _workout_sync.pull_synced_workout() == (None, None)
        client_cls.assert_not_called()

    def test_returns_the_error_message_on_a_sync_error(self) -> None:
        _workout_sync.SYNC_TOKEN_FILE.write_text("tok")
        client = _mock_client(get_file_text=GitHubSyncError("offline"))
        with patch.object(_workout_sync, "GitHubSyncClient", return_value=client):
            assert _workout_sync.pull_synced_workout() == (None, "offline")

    def test_returns_none_none_when_nothing_has_been_pushed_yet(self) -> None:
        _workout_sync.SYNC_TOKEN_FILE.write_text("tok")
        client = _mock_client(get_file_text=None)
        with patch.object(_workout_sync, "GitHubSyncClient", return_value=client):
            assert _workout_sync.pull_synced_workout() == (None, None)

    def test_returns_the_payload_on_success(self) -> None:
        _workout_sync.SYNC_TOKEN_FILE.write_text("tok")
        log = json.dumps({"a": _record_json({"succeeded": True})})
        client = _mock_client(get_file_text=log)
        with patch.object(_workout_sync, "GitHubSyncClient", return_value=client):
            assert _workout_sync.pull_synced_workout() == ({"succeeded": True}, None)

    def test_returns_a_corrupt_data_message_on_malformed_sync_data(self) -> None:
        _workout_sync.SYNC_TOKEN_FILE.write_text("tok")
        client = _mock_client(get_file_text="{not valid json")
        with patch.object(_workout_sync, "GitHubSyncClient", return_value=client):
            data, error = _workout_sync.pull_synced_workout()
        assert data is None
        assert error is not None
        assert "corrupt sync data" in error
