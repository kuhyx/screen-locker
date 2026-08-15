"""Tests for the phone-workout sync pull (crdt-sync transport).

Covers the token read, the payload predicates, the per-log record extractors
and the cross-device merge. The backend selection (``sync_client`` /
``remote_client``) and the two public pulls live in ``_part2``.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from crdt_sync import GitHubSyncError
import pytest

from screen_locker import _workout_sync
from screen_locker.tests._workout_sync_fixtures import (
    _multi_device_client,
    _session_payload,
    _session_record_dict,
)


class TestMergeDeviceRecords:
    """The walk over EVERY ``devices/<id>/log.json``, not one hardcoded path."""

    def test_merges_records_across_every_device(self) -> None:
        """Merges records across every device."""
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
        """Dedups the same ID keeping the highest clock."""
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
        """Ignores a lower clock duplicate seen later."""
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
        """Skips a corrupt device log."""
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
        """Skips an unreachable device."""
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
        """Returns empty on a listing failure when not strict."""
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
        """Warns about a skipped device."""
        client = _multi_device_client({"gone": GitHubSyncError("404")})
        with caplog.at_level("WARNING"):
            _workout_sync._merge_device_records(
                client, _workout_sync._session_records, "sessions"
            )
        assert "SKIPPING that device" in caplog.text
