"""Tests for the phone-workout sync pull (crdt-sync transport).

Covers the token read, the payload predicates, the per-log record extractors
and the cross-device merge. The backend selection (``sync_client`` /
``remote_client``) and the two public pulls live in ``_part2``.
"""

from __future__ import annotations

import json

from crdt_sync import Hlc, Record
import pytest

from screen_locker import _sync_records, _workout_sync
from screen_locker.tests._workout_sync_fixtures import (
    _manual_payload,
    _manual_record_dict,
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
    """ReadSyncToken."""

    def test_returns_none_when_file_is_missing(self) -> None:
        """Returns none when file is missing."""
        assert _workout_sync.read_sync_token() is None

    def test_returns_none_when_file_is_empty(self) -> None:
        """Returns none when file is empty."""
        _workout_sync.SYNC_TOKEN_FILE.write_text("   \n")
        assert _workout_sync.read_sync_token() is None

    def test_returns_the_stripped_token(self) -> None:
        """Returns the stripped token."""
        _workout_sync.SYNC_TOKEN_FILE.write_text("  abc123  \n")
        assert _workout_sync.read_sync_token() == "abc123"


class TestIsSessionPayload:
    """Sessions are identified by SHAPE (an ``exercises`` list), not ``kind``."""

    def test_true_for_a_dict_with_an_exercises_list(self) -> None:
        """True for a dict with an exercises list."""
        assert _workout_sync._is_session_payload(_session_payload()) is True

    def test_true_even_with_an_empty_exercises_list(self) -> None:
        """True even with an empty exercises list."""
        assert _workout_sync._is_session_payload({"exercises": []}) is True

    def test_false_for_a_manual_workout(self) -> None:
        """False for a manual workout."""
        assert _workout_sync._is_session_payload(_manual_payload()) is False

    def test_false_for_verified_records_sharing_the_same_log(self) -> None:
        """``*_verified`` records are non-manual but have no ``exercises``."""
        assert _workout_sync._is_session_payload({"kind": "runnerup_verified"}) is False
        assert _workout_sync._is_session_payload({"kind": "phone_verified"}) is False

    def test_false_when_exercises_is_not_a_list(self) -> None:
        """False when exercises is not a list."""
        assert _workout_sync._is_session_payload({"exercises": "Squat"}) is False

    def test_false_for_a_non_dict_payload(self) -> None:
        """False for a non dict payload."""
        assert _workout_sync._is_session_payload("not-a-dict") is False
        assert _workout_sync._is_session_payload(None) is False


class TestIsManualPayload:
    """IsManualPayload."""

    def test_true_for_manual_kind(self) -> None:
        """True for manual kind."""
        assert _workout_sync._is_manual_payload({"kind": "manual_workout"}) is True

    def test_false_for_session_or_non_dict(self) -> None:
        """False for session or non dict."""
        assert _workout_sync._is_manual_payload(_session_payload()) is False
        assert _workout_sync._is_manual_payload("not-a-dict") is False


class TestSessionRecords:
    """SessionRecords."""

    def test_returns_only_session_records(self) -> None:
        """Returns only session records."""
        log = {
            "s": _session_record_dict("session:1", _session_payload()),
            "m": _manual_record_dict("manual:1", _manual_payload()),
            "v": _manual_record_dict("verified:1", {"kind": "runnerup_verified"}),
        }
        result = _workout_sync._session_records(json.dumps(log))
        assert list(result) == ["session:1"]

    def test_skips_records_without_a_payload_field(self) -> None:
        """Skips records without a payload field."""
        no_payload = Record(
            id="a",
            fields={"other": (1, Hlc(wall_time_ms=1, counter=0, node_id="phone"))},
        )
        log = {"a": no_payload.to_dict()}
        assert _workout_sync._session_records(json.dumps(log)) == {}

    def test_raises_type_error_when_top_level_is_not_an_object(self) -> None:
        """Raises type error when top level is not an object."""
        with pytest.raises(TypeError, match="not a JSON object"):
            _workout_sync._session_records(json.dumps([1, 2, 3]))

    def test_raises_value_error_for_invalid_json(self) -> None:
        """Raises value error for invalid JSON."""
        with pytest.raises(ValueError, match="Expecting property name"):
            _workout_sync._session_records("{not valid json")

    def test_raises_key_error_for_a_malformed_record(self) -> None:
        """Raises key error for a malformed record."""
        log = {"a": {"id": "a"}}  # missing "fields"
        with pytest.raises(KeyError):
            _workout_sync._session_records(json.dumps(log))


class TestManualRecords:
    """ManualRecords."""

    def test_returns_only_manual_records(self) -> None:
        """Returns only manual records."""
        log = {
            "s": _record_json(_session_payload()),
            "m": _manual_record_dict("manual:1", _manual_payload()),
        }
        result = _workout_sync._manual_records(json.dumps(log))
        assert list(result) == ["manual:1"]

    def test_skips_records_without_a_payload_field(self) -> None:
        """Skips records without a payload field."""
        no_payload = Record(
            id="a",
            fields={"other": (1, Hlc(wall_time_ms=1, counter=0, node_id="phone"))},
        )
        log = {"a": no_payload.to_dict()}
        assert _workout_sync._manual_records(json.dumps(log)) == {}

    def test_raises_type_error_when_top_level_is_not_an_object(self) -> None:
        """Raises type error when top level is not an object."""
        with pytest.raises(TypeError, match="not a JSON object"):
            _workout_sync._manual_records(json.dumps([1, 2, 3]))


class TestTombstonedIds:
    """TombstonedIds."""

    def test_returns_only_the_deleted_ids(self) -> None:
        """Returns only the deleted ids."""
        hlc = Hlc(wall_time_ms=1, counter=0, node_id="phone")
        live = Record(id="live", fields={"payload": ({"a": 1}, hlc)})
        gone = Record(
            id="gone",
            fields={"payload": ({"a": 1}, hlc)},
            deleted=True,
            deleted_hlc=hlc,
        )
        log = {"x": live.to_dict(), "y": gone.to_dict()}
        assert _sync_records._tombstoned_ids(json.dumps(log)) == {"gone"}

    def test_raises_type_error_when_top_level_is_not_an_object(self) -> None:
        """Raises type error when top level is not an object."""
        with pytest.raises(TypeError, match="not a JSON object"):
            _sync_records._tombstoned_ids(json.dumps([1, 2, 3]))
