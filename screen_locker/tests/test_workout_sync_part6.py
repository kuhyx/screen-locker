"""Backend selection and the two public pulls, split from ``test_workout_sync``.

``sync_client`` decides WHICH backend is read; ``pull_synced_workout`` and
``pull_all_manual_records`` are what the locker actually calls.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from crdt_sync import (
    GitHubSyncError,
    Hlc,
    Record,
)

from screen_locker import _sync_client, _workout_sync
from screen_locker.tests._workout_sync_fixtures import (
    _manual_payload,
    _manual_record_dict,
    _multi_device_client,
)


class TestPullAllManualRecords:
    """PullAllManualRecords."""

    def test_returns_empty_when_no_token(self) -> None:
        """Returns empty when no token."""
        assert _workout_sync.pull_all_manual_records() == []

    def test_returns_empty_when_listing_fails(self) -> None:
        """Returns empty when listing fails."""
        _workout_sync.SYNC_TOKEN_FILE.write_text("tok")
        client = MagicMock()
        client.list_directory.side_effect = GitHubSyncError("offline")
        with patch.object(_sync_client, "GitHubSyncClient", return_value=client):
            assert _workout_sync.pull_all_manual_records() == []

    def test_merges_manual_records_across_devices(self) -> None:
        """Merges manual records across devices."""
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
        with patch.object(_sync_client, "GitHubSyncClient", return_value=client):
            result = _workout_sync.pull_all_manual_records()
        assert sorted(rid for rid, _ in result) == ["manual:a", "manual:b"]

    def test_skips_a_tombstoned_record(self) -> None:
        """A workout deleted on another device must stop counting here.

        crdt-sync deletion is monotonic, so the tombstone is the only durable
        way to retract a synced workout. Ingesting it anyway made a delete in
        the phone app look like it worked and then silently come back on the
        next 15-minute sync.
        """
        _workout_sync.SYNC_TOKEN_FILE.write_text("tok")
        hlc = Hlc(wall_time_ms=1000, counter=0, node_id="phone")
        tombstoned = Record(
            id="manual:gone",
            fields={"payload": (_manual_payload(), hlc)},
            deleted=True,
            deleted_hlc=hlc,
        ).to_dict()
        client = _multi_device_client(
            {
                "phone": json.dumps(
                    {
                        "a": _manual_record_dict("manual:kept", _manual_payload()),
                        "b": tombstoned,
                    }
                ),
            }
        )
        with patch.object(_sync_client, "GitHubSyncClient", return_value=client):
            result = _workout_sync.pull_all_manual_records()
        assert [rid for rid, _ in result] == ["manual:kept"]

    def test_skips_missing_and_corrupt_device_logs(self) -> None:
        """Skips missing and corrupt device logs."""
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
        with patch.object(_sync_client, "GitHubSyncClient", return_value=client):
            result = _workout_sync.pull_all_manual_records()
        assert [rid for rid, _ in result] == ["manual:a"]

    def test_dedups_same_id_keeping_highest_clock(self) -> None:
        """Dedups same ID keeping highest clock."""
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
        with patch.object(_sync_client, "GitHubSyncClient", return_value=client):
            result = _workout_sync.pull_all_manual_records()
        assert len(result) == 1
        assert result[0][1]["cost"] == "NEW"

    def test_ignores_a_lower_clock_duplicate_seen_later(self) -> None:
        """Ignores a lower clock duplicate seen later."""
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
        with patch.object(_sync_client, "GitHubSyncClient", return_value=client):
            result = _workout_sync.pull_all_manual_records()
        assert len(result) == 1
        assert result[0][1]["cost"] == "NEW"
