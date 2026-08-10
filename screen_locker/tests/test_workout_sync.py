"""Tests for the phone-workout sync pull (crdt-sync transport).

Covers the token read, the payload predicates, the per-log record extractors
and the cross-device merge. The backend selection (``sync_client`` /
``remote_client``) and the two public pulls live in ``_part2``.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from crdt_sync import GitHubSyncError, Hlc, Record
import pytest

from screen_locker import _workout_sync
from screen_locker.tests._workout_sync_fixtures import (
    _manual_payload,
    _manual_record_dict,
    _multi_device_client,
    _record_json,
    _session_payload,
    _session_record_dict,
)

# The autouse `isolate_sync_token` fixture (registered repo-wide via the
# `pytest_plugins` entry for `screen_locker.tests.test_sync_fixtures` in
# pyproject.toml) already redirects `_workout_sync.SYNC_TOKEN_FILE` into a
# per-test tmp_path, so tests here can write to it directly without needing
# their own isolation fixture. The autouse `_no_real_firebase_config` fixture
# in conftest.py likewise points `CONFIG_FILE` at a nonexistent path, so tests
# that want the Firebase branch must monkeypatch it back at a file they own.


class TestReadSyncToken:
    def test_returns_none_when_file_is_missing(self) -> None:
        assert _workout_sync.read_sync_token() is None

    def test_returns_none_when_file_is_empty(self) -> None:
        _workout_sync.SYNC_TOKEN_FILE.write_text("   \n")
        assert _workout_sync.read_sync_token() is None

    def test_returns_the_stripped_token(self) -> None:
        _workout_sync.SYNC_TOKEN_FILE.write_text("  abc123  \n")
        assert _workout_sync.read_sync_token() == "abc123"


class TestIsSessionPayload:
    """Sessions are identified by SHAPE (an ``exercises`` list), not ``kind``."""

    def test_true_for_a_dict_with_an_exercises_list(self) -> None:
        assert _workout_sync._is_session_payload(_session_payload()) is True

    def test_true_even_with_an_empty_exercises_list(self) -> None:
        assert _workout_sync._is_session_payload({"exercises": []}) is True

    def test_false_for_a_manual_workout(self) -> None:
        assert _workout_sync._is_session_payload(_manual_payload()) is False

    def test_false_for_verified_records_sharing_the_same_log(self) -> None:
        """``*_verified`` records are non-manual but have no ``exercises``."""
        assert _workout_sync._is_session_payload({"kind": "runnerup_verified"}) is False
        assert _workout_sync._is_session_payload({"kind": "phone_verified"}) is False

    def test_false_when_exercises_is_not_a_list(self) -> None:
        assert _workout_sync._is_session_payload({"exercises": "Squat"}) is False

    def test_false_for_a_non_dict_payload(self) -> None:
        assert _workout_sync._is_session_payload("not-a-dict") is False
        assert _workout_sync._is_session_payload(None) is False


class TestIsManualPayload:
    def test_true_for_manual_kind(self) -> None:
        assert _workout_sync._is_manual_payload({"kind": "manual_workout"}) is True

    def test_false_for_session_or_non_dict(self) -> None:
        assert _workout_sync._is_manual_payload(_session_payload()) is False
        assert _workout_sync._is_manual_payload("not-a-dict") is False


class TestSessionRecords:
    def test_returns_only_session_records(self) -> None:
        log = {
            "s": _session_record_dict("session:1", _session_payload()),
            "m": _manual_record_dict("manual:1", _manual_payload()),
            "v": _manual_record_dict("verified:1", {"kind": "runnerup_verified"}),
        }
        result = _workout_sync._session_records(json.dumps(log))
        assert list(result) == ["session:1"]

    def test_skips_records_without_a_payload_field(self) -> None:
        no_payload = Record(
            id="a",
            fields={"other": (1, Hlc(wall_time_ms=1, counter=0, node_id="phone"))},
        )
        log = {"a": no_payload.to_dict()}
        assert _workout_sync._session_records(json.dumps(log)) == {}

    def test_raises_type_error_when_top_level_is_not_an_object(self) -> None:
        with pytest.raises(TypeError, match="not a JSON object"):
            _workout_sync._session_records(json.dumps([1, 2, 3]))

    def test_raises_value_error_for_invalid_json(self) -> None:
        with pytest.raises(ValueError, match="Expecting property name"):
            _workout_sync._session_records("{not valid json")

    def test_raises_key_error_for_a_malformed_record(self) -> None:
        log = {"a": {"id": "a"}}  # missing "fields"
        with pytest.raises(KeyError):
            _workout_sync._session_records(json.dumps(log))


class TestManualRecords:
    def test_returns_only_manual_records(self) -> None:
        log = {
            "s": _record_json(_session_payload()),
            "m": _manual_record_dict("manual:1", _manual_payload()),
        }
        result = _workout_sync._manual_records(json.dumps(log))
        assert list(result) == ["manual:1"]

    def test_skips_records_without_a_payload_field(self) -> None:
        no_payload = Record(
            id="a",
            fields={"other": (1, Hlc(wall_time_ms=1, counter=0, node_id="phone"))},
        )
        log = {"a": no_payload.to_dict()}
        assert _workout_sync._manual_records(json.dumps(log)) == {}

    def test_raises_type_error_when_top_level_is_not_an_object(self) -> None:
        with pytest.raises(TypeError, match="not a JSON object"):
            _workout_sync._manual_records(json.dumps([1, 2, 3]))


class TestMergeDeviceRecords:
    """The walk over EVERY ``devices/<id>/log.json``, not one hardcoded path."""

    def test_merges_records_across_every_device(self) -> None:
        client = _multi_device_client(
            {
                "phone": json.dumps(
                    {"a": _session_record_dict("session:a", _session_payload())}
                ),
                "pc": json.dumps(
                    {"b": _session_record_dict("session:b", _session_payload())}
                ),
            }
        )
        merged = _workout_sync._merge_device_records(
            client, _workout_sync._session_records, "sessions"
        )
        assert sorted(merged) == ["session:a", "session:b"]

    def test_dedups_the_same_id_keeping_the_highest_clock(self) -> None:
        client = _multi_device_client(
            {
                "phone": json.dumps(
                    {
                        "a": _session_record_dict(
                            "session:a",
                            _session_payload(note="OLD"),
                            wall_time_ms=100,
                        )
                    }
                ),
                "pc": json.dumps(
                    {
                        "a": _session_record_dict(
                            "session:a",
                            _session_payload(note="NEW"),
                            wall_time_ms=200,
                        )
                    }
                ),
            }
        )
        merged = _workout_sync._merge_device_records(
            client, _workout_sync._session_records, "sessions"
        )
        assert len(merged) == 1
        assert merged["session:a"][0]["note"] == "NEW"

    def test_ignores_a_lower_clock_duplicate_seen_later(self) -> None:
        client = _multi_device_client(
            {
                "phone": json.dumps(
                    {
                        "a": _session_record_dict(
                            "session:a",
                            _session_payload(note="NEW"),
                            wall_time_ms=200,
                        )
                    }
                ),
                "pc": json.dumps(
                    {
                        "a": _session_record_dict(
                            "session:a",
                            _session_payload(note="OLD"),
                            wall_time_ms=100,
                        )
                    }
                ),
            }
        )
        merged = _workout_sync._merge_device_records(
            client, _workout_sync._session_records, "sessions"
        )
        assert merged["session:a"][0]["note"] == "NEW"

    def test_skips_a_corrupt_device_log(self) -> None:
        client = _multi_device_client(
            {
                "good": json.dumps(
                    {"a": _session_record_dict("session:a", _session_payload())}
                ),
                "corrupt": "{not json",
            }
        )
        merged = _workout_sync._merge_device_records(
            client, _workout_sync._session_records, "sessions"
        )
        assert list(merged) == ["session:a"]

    def test_skips_an_unreachable_device(self) -> None:
        client = _multi_device_client(
            {
                "good": json.dumps(
                    {"a": _session_record_dict("session:a", _session_payload())}
                ),
                "gone": GitHubSyncError("404"),
                "empty": None,
            }
        )
        merged = _workout_sync._merge_device_records(
            client, _workout_sync._session_records, "sessions"
        )
        assert list(merged) == ["session:a"]

    def test_returns_empty_on_a_listing_failure_when_not_strict(self) -> None:
        client = MagicMock()
        client.list_directory.side_effect = GitHubSyncError("offline")
        merged = _workout_sync._merge_device_records(
            client, _workout_sync._session_records, "sessions"
        )
        assert merged == {}

    def test_reraises_on_a_listing_failure_when_strict(self) -> None:
        """Callers separating "nothing to sync" from "sync broke" need the raise."""
        client = MagicMock()
        client.list_directory.side_effect = GitHubSyncError("offline")
        with pytest.raises(GitHubSyncError, match="offline"):
            _workout_sync._merge_device_records(
                client, _workout_sync._session_records, "sessions", strict=True
            )

    def test_warns_about_a_listing_failure(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A total pull failure must never be silent."""
        client = MagicMock()
        client.list_directory.side_effect = GitHubSyncError("offline")
        with caplog.at_level("WARNING"):
            _workout_sync._merge_device_records(
                client, _workout_sync._session_records, "sessions"
            )
        assert "offline" in caplog.text

    def test_warns_about_a_skipped_device(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        client = _multi_device_client({"gone": GitHubSyncError("404")})
        with caplog.at_level("WARNING"):
            _workout_sync._merge_device_records(
                client, _workout_sync._session_records, "sessions"
            )
        assert "SKIPPING that device" in caplog.text
