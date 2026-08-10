"""Backend selection and the two public pulls, split from ``test_workout_sync``.

``sync_client`` decides WHICH backend is read; ``pull_synced_workout`` and
``pull_all_manual_records`` are what the locker actually calls.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from crdt_sync import (
    ConfigError,
    FirebaseAuthError,
    FirebaseSyncError,
    GitHubSyncError,
)
import pytest

from screen_locker import _workout_sync
from screen_locker.tests._workout_sync_fixtures import (
    _firebase_config,
    _manual_payload,
    _manual_record_dict,
    _multi_device_client,
    _session_payload,
    _session_record_dict,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestSyncClient:
    """Every configuration of (GitHub token, Firebase config), plus failure."""

    def test_returns_none_when_nothing_is_configured(self) -> None:
        assert _workout_sync.sync_client() is None

    def test_warns_when_nothing_is_configured(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level("WARNING"):
            _workout_sync.sync_client()
        assert "sync is OFF" in caplog.text

    def test_uses_github_alone_when_only_the_token_exists(self) -> None:
        _workout_sync.SYNC_TOKEN_FILE.write_text("tok")
        github = MagicMock()
        with patch.object(_workout_sync, "GitHubSyncClient", return_value=github):
            assert _workout_sync.sync_client() is github

    def test_mirrors_when_both_the_token_and_firebase_exist(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _workout_sync.SYNC_TOKEN_FILE.write_text("tok")
        _firebase_config(_workout_sync, tmp_path, monkeypatch)
        github = MagicMock()
        monkeypatch.setattr(
            _workout_sync, "mirror_client_for", lambda _app, client: ("mirror", client)
        )
        with patch.object(_workout_sync, "GitHubSyncClient", return_value=github):
            assert _workout_sync.sync_client() == ("mirror", github)

    def test_uses_firebase_alone_when_only_the_config_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A Firebase-only machine must still sync -- no PAT required."""
        _firebase_config(_workout_sync, tmp_path, monkeypatch)
        firebase = MagicMock()
        monkeypatch.setattr(_workout_sync, "firebase_client_for", lambda _app: firebase)
        assert _workout_sync.sync_client() is firebase

    @pytest.mark.parametrize(
        "error",
        [
            ConfigError("no password"),
            FirebaseAuthError("bad credentials"),
            FirebaseSyncError("backend down"),
        ],
    )
    def test_returns_none_when_firebase_only_is_unusable(
        self, error: Exception, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No PAT to fall back to: report it loudly, do not raise."""
        _firebase_config(_workout_sync, tmp_path, monkeypatch)

        def _boom(*_args: object, **_kwargs: object) -> None:
            raise error

        monkeypatch.setattr(_workout_sync, "firebase_client_for", _boom)
        assert _workout_sync.sync_client() is None

    def test_warns_when_firebase_only_is_unusable(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _firebase_config(_workout_sync, tmp_path, monkeypatch)

        def _boom(*_args: object, **_kwargs: object) -> None:
            message = "backend down"
            raise FirebaseSyncError(message)

        monkeypatch.setattr(_workout_sync, "firebase_client_for", _boom)
        with caplog.at_level("WARNING"):
            _workout_sync.sync_client()
        assert "backend down" in caplog.text


class TestPullSyncedWorkout:
    def test_returns_none_none_when_no_token_is_configured(self) -> None:
        with patch.object(_workout_sync, "GitHubSyncClient") as client_cls:
            assert _workout_sync.pull_synced_workout() == (None, None)
        client_cls.assert_not_called()

    def test_returns_the_error_message_on_a_sync_error(self) -> None:
        """A failed device LISTING is a real error, not "nothing to sync"."""
        _workout_sync.SYNC_TOKEN_FILE.write_text("tok")
        client = MagicMock()
        client.list_directory.side_effect = GitHubSyncError("offline")
        with patch.object(_workout_sync, "GitHubSyncClient", return_value=client):
            assert _workout_sync.pull_synced_workout() == (None, "offline")

    def test_does_not_propagate_a_firebase_sync_error(self) -> None:
        """Regression: FirebaseSyncError is a SIBLING of GitHubSyncError.

        Catching only ``GitHubSyncError`` let a Firebase failure escape and
        crash the locker with status=1/FAILURE. It must come back as an error
        tuple like any other backend failure.
        """
        _workout_sync.SYNC_TOKEN_FILE.write_text("tok")
        client = MagicMock()
        client.list_directory.side_effect = FirebaseSyncError("firebase exploded")
        with patch.object(_workout_sync, "GitHubSyncClient", return_value=client):
            data, error = _workout_sync.pull_synced_workout()
        assert data is None
        assert error == "firebase exploded"

    def test_does_not_propagate_a_firebase_error_on_a_firebase_only_machine(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The crash's real shape: no PAT, Firebase primary, backend throws.

        The configuration the locker actually died in, pinned in its own right
        so a future GitHub-only narrowing of the handler cannot pass.
        """
        _firebase_config(_workout_sync, tmp_path, monkeypatch)
        client = MagicMock()
        client.list_directory.side_effect = FirebaseSyncError("firebase exploded")
        monkeypatch.setattr(_workout_sync, "firebase_client_for", lambda _app: client)
        data, error = _workout_sync.pull_synced_workout()
        assert data is None
        assert error == "firebase exploded"

    def test_returns_none_none_when_nothing_has_been_pushed_yet(self) -> None:
        _workout_sync.SYNC_TOKEN_FILE.write_text("tok")
        client = _multi_device_client({"phone": None})
        with patch.object(_workout_sync, "GitHubSyncClient", return_value=client):
            assert _workout_sync.pull_synced_workout() == (None, None)

    def test_returns_none_none_when_there_are_no_devices_at_all(self) -> None:
        _workout_sync.SYNC_TOKEN_FILE.write_text("tok")
        client = _multi_device_client({})
        with patch.object(_workout_sync, "GitHubSyncClient", return_value=client):
            assert _workout_sync.pull_synced_workout() == (None, None)

    def test_returns_the_payload_on_success(self) -> None:
        _workout_sync.SYNC_TOKEN_FILE.write_text("tok")
        payload = _session_payload()
        client = _multi_device_client(
            {"phone": json.dumps({"a": _session_record_dict("session:a", payload)})}
        )
        with patch.object(_workout_sync, "GitHubSyncClient", return_value=client):
            assert _workout_sync.pull_synced_workout() == (payload, None)

    def test_finds_a_session_in_a_uuid_named_device_directory(self) -> None:
        """The actual bug: the phone's dir is a per-install uuid, not "phone".

        Reading a single hardcoded ``devices/phone/log.json`` returned a stale
        session forever while newer ones sat unread one directory over.
        """
        _workout_sync.SYNC_TOKEN_FILE.write_text("tok")
        fresh = _session_payload(note="FROM-UUID-DIR")
        client = _multi_device_client(
            {
                "pc": json.dumps(
                    {
                        "old": _session_record_dict(
                            "session:old",
                            _session_payload(note="STALE"),
                            wall_time_ms=100,
                        )
                    }
                ),
                "0f1d2c3b-4a59-4c6d-8e7f-a0b1c2d3e4f5": json.dumps(
                    {
                        "new": _session_record_dict(
                            "session:new", fresh, wall_time_ms=200
                        )
                    }
                ),
            }
        )
        with patch.object(_workout_sync, "GitHubSyncClient", return_value=client):
            assert _workout_sync.pull_synced_workout() == (fresh, None)

    def test_returns_the_highest_clock_session_across_devices(self) -> None:
        _workout_sync.SYNC_TOKEN_FILE.write_text("tok")
        newest = _session_payload(note="NEWEST")
        client = _multi_device_client(
            {
                "phone-a": json.dumps(
                    {
                        "a": _session_record_dict(
                            "session:a",
                            _session_payload(note="OLDER"),
                            wall_time_ms=100,
                        )
                    }
                ),
                "phone-b": json.dumps(
                    {"b": _session_record_dict("session:b", newest, wall_time_ms=300)}
                ),
                "phone-c": json.dumps(
                    {
                        "c": _session_record_dict(
                            "session:c",
                            _session_payload(note="MIDDLE"),
                            wall_time_ms=200,
                        )
                    }
                ),
            }
        )
        with patch.object(_workout_sync, "GitHubSyncClient", return_value=client):
            data, error = _workout_sync.pull_synced_workout()
        assert error is None
        assert data == newest

    def test_ignores_non_session_records_in_the_same_logs(self) -> None:
        """``phone_verified`` / ``runnerup_verified`` share these device logs.

        They are non-manual but have no ``exercises``, so "not manual" alone
        would hand back a record with none of the fields a caller expects --
        even though here they carry the HIGHEST clocks in the log.
        """
        _workout_sync.SYNC_TOKEN_FILE.write_text("tok")
        session = _session_payload(note="REAL-SESSION")
        client = _multi_device_client(
            {
                "phone": json.dumps(
                    {
                        "s": _session_record_dict(
                            "session:a", session, wall_time_ms=100
                        ),
                        "v": _session_record_dict(
                            "verified:1",
                            {"kind": "phone_verified", "date": "2026-08-10"},
                            wall_time_ms=900,
                        ),
                        "r": _session_record_dict(
                            "verified:2",
                            {"kind": "runnerup_verified", "date": "2026-08-10"},
                            wall_time_ms=950,
                        ),
                        "m": _manual_record_dict(
                            "manual:1", _manual_payload(), wall_time_ms=999
                        ),
                    }
                )
            }
        )
        with patch.object(_workout_sync, "GitHubSyncClient", return_value=client):
            data, error = _workout_sync.pull_synced_workout()
        assert error is None
        assert data == session

    def test_skips_a_corrupt_device_log_instead_of_failing(self) -> None:
        """A corrupt log costs that device's sessions, not the whole pull."""
        _workout_sync.SYNC_TOKEN_FILE.write_text("tok")
        payload = _session_payload()
        client = _multi_device_client(
            {
                "corrupt": "{not valid json",
                "phone": json.dumps({"a": _session_record_dict("session:a", payload)}),
            }
        )
        with patch.object(_workout_sync, "GitHubSyncClient", return_value=client):
            assert _workout_sync.pull_synced_workout() == (payload, None)

    def test_returns_none_none_when_every_device_log_is_corrupt(self) -> None:
        _workout_sync.SYNC_TOKEN_FILE.write_text("tok")
        client = _multi_device_client({"corrupt": "{not valid json"})
        with patch.object(_workout_sync, "GitHubSyncClient", return_value=client):
            assert _workout_sync.pull_synced_workout() == (None, None)


class TestPullAllManualRecords:
    def test_returns_empty_when_no_token(self) -> None:
        assert _workout_sync.pull_all_manual_records() == []

    def test_returns_empty_when_listing_fails(self) -> None:
        _workout_sync.SYNC_TOKEN_FILE.write_text("tok")
        client = MagicMock()
        client.list_directory.side_effect = GitHubSyncError("offline")
        with patch.object(_workout_sync, "GitHubSyncClient", return_value=client):
            assert _workout_sync.pull_all_manual_records() == []

    def test_merges_manual_records_across_devices(self) -> None:
        _workout_sync.SYNC_TOKEN_FILE.write_text("tok")
        client = _multi_device_client(
            {
                "phone": json.dumps(
                    {"a": _manual_record_dict("manual:a", _manual_payload())}
                ),
                "pc": json.dumps(
                    {"b": _manual_record_dict("manual:b", _manual_payload())}
                ),
            }
        )
        with patch.object(_workout_sync, "GitHubSyncClient", return_value=client):
            result = _workout_sync.pull_all_manual_records()
        assert sorted(rid for rid, _ in result) == ["manual:a", "manual:b"]

    def test_skips_missing_and_corrupt_device_logs(self) -> None:
        _workout_sync.SYNC_TOKEN_FILE.write_text("tok")
        client = _multi_device_client(
            {
                "phone": json.dumps(
                    {"a": _manual_record_dict("manual:a", _manual_payload())}
                ),
                "gone": GitHubSyncError("404"),
                "empty": None,
                "corrupt": "{not json",
            }
        )
        with patch.object(_workout_sync, "GitHubSyncClient", return_value=client):
            result = _workout_sync.pull_all_manual_records()
        assert [rid for rid, _ in result] == ["manual:a"]

    def test_dedups_same_id_keeping_highest_clock(self) -> None:
        _workout_sync.SYNC_TOKEN_FILE.write_text("tok")
        client = _multi_device_client(
            {
                "phone": json.dumps(
                    {
                        "a": _manual_record_dict(
                            "manual:a",
                            _manual_payload(cost="OLD"),
                            wall_time_ms=100,
                        )
                    }
                ),
                "pc": json.dumps(
                    {
                        "a": _manual_record_dict(
                            "manual:a",
                            _manual_payload(cost="NEW"),
                            wall_time_ms=200,
                        )
                    }
                ),
            }
        )
        with patch.object(_workout_sync, "GitHubSyncClient", return_value=client):
            result = _workout_sync.pull_all_manual_records()
        assert len(result) == 1
        assert result[0][1]["cost"] == "NEW"

    def test_ignores_a_lower_clock_duplicate_seen_later(self) -> None:
        _workout_sync.SYNC_TOKEN_FILE.write_text("tok")
        client = _multi_device_client(
            {
                "phone": json.dumps(
                    {
                        "a": _manual_record_dict(
                            "manual:a",
                            _manual_payload(cost="NEW"),
                            wall_time_ms=200,
                        )
                    }
                ),
                "pc": json.dumps(
                    {
                        "a": _manual_record_dict(
                            "manual:a",
                            _manual_payload(cost="OLD"),
                            wall_time_ms=100,
                        )
                    }
                ),
            }
        )
        with patch.object(_workout_sync, "GitHubSyncClient", return_value=client):
            result = _workout_sync.pull_all_manual_records()
        assert len(result) == 1
        assert result[0][1]["cost"] == "NEW"
