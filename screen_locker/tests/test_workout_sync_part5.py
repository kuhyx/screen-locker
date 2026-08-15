"""Backend selection and the two public pulls, split from ``test_workout_sync``.

``sync_client`` decides WHICH backend is read; ``pull_synced_workout`` and
``pull_all_manual_records`` are what the locker actually calls.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from crdt_sync import (
    FirebaseSyncError,
    GitHubSyncError,
)

from screen_locker import _sync_client, _workout_sync
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

    import pytest


class TestPullSyncedWorkout:
    """PullSyncedWorkout."""

    def test_returns_none_none_when_no_token_is_configured(self) -> None:
        """Returns none none when no token is configured."""
        with patch.object(_sync_client, "GitHubSyncClient") as client_cls:
            assert _workout_sync.pull_synced_workout() == (None, None)
        client_cls.assert_not_called()

    def test_returns_the_error_message_on_a_sync_error(self) -> None:
        """A failed device LISTING is a real error, not "nothing to sync"."""
        _workout_sync.SYNC_TOKEN_FILE.write_text("tok")
        client = MagicMock()
        client.list_directory.side_effect = GitHubSyncError("offline")
        with patch.object(_sync_client, "GitHubSyncClient", return_value=client):
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
        with patch.object(_sync_client, "GitHubSyncClient", return_value=client):
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
        _firebase_config(_sync_client, tmp_path, monkeypatch)
        client = MagicMock()
        client.list_directory.side_effect = FirebaseSyncError("firebase exploded")
        monkeypatch.setattr(_sync_client, "firebase_client_for", lambda _app: client)
        data, error = _workout_sync.pull_synced_workout()
        assert data is None
        assert error == "firebase exploded"

    def test_returns_none_none_when_nothing_has_been_pushed_yet(self) -> None:
        """Returns none none when nothing has been pushed yet."""
        _workout_sync.SYNC_TOKEN_FILE.write_text("tok")
        client = _multi_device_client({"phone": None})
        with patch.object(_sync_client, "GitHubSyncClient", return_value=client):
            assert _workout_sync.pull_synced_workout() == (None, None)

    def test_returns_none_none_when_there_are_no_devices_at_all(self) -> None:
        """Returns none none when there are no devices at all."""
        _workout_sync.SYNC_TOKEN_FILE.write_text("tok")
        client = _multi_device_client({})
        with patch.object(_sync_client, "GitHubSyncClient", return_value=client):
            assert _workout_sync.pull_synced_workout() == (None, None)

    def test_returns_the_payload_on_success(self) -> None:
        """Returns the payload on success."""
        _workout_sync.SYNC_TOKEN_FILE.write_text("tok")
        payload = _session_payload()
        client = _multi_device_client(
            {"phone": json.dumps({"a": _session_record_dict("session:a", payload)})}
        )
        with patch.object(_sync_client, "GitHubSyncClient", return_value=client):
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
        with patch.object(_sync_client, "GitHubSyncClient", return_value=client):
            assert _workout_sync.pull_synced_workout() == (fresh, None)

    def test_returns_the_highest_clock_session_across_devices(self) -> None:
        """Returns the highest clock session across devices."""
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
        with patch.object(_sync_client, "GitHubSyncClient", return_value=client):
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
        with patch.object(_sync_client, "GitHubSyncClient", return_value=client):
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
        with patch.object(_sync_client, "GitHubSyncClient", return_value=client):
            assert _workout_sync.pull_synced_workout() == (payload, None)

    def test_returns_none_none_when_every_device_log_is_corrupt(self) -> None:
        """Returns none none when every device log is corrupt."""
        _workout_sync.SYNC_TOKEN_FILE.write_text("tok")
        client = _multi_device_client({"corrupt": "{not valid json"})
        with patch.object(_sync_client, "GitHubSyncClient", return_value=client):
            assert _workout_sync.pull_synced_workout() == (None, None)
