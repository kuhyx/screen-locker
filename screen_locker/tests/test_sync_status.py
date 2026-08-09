"""Tests for the on-disk sync posture shown in the status view.

The point of this module is that it never touches the network, so every test
here drives it purely from files in ``tmp_path``.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import patch

from screen_locker._sync_status import (
    SyncStatus,
    format_sync_line,
    gather_sync_status,
)
from screen_locker.status_view import main

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _gather(
    tmp_path: Path,
    *,
    state_file: Path | None = None,
    token_file: Path | None = None,
    firebase_config: Path | None = None,
) -> SyncStatus:
    """Gather status against files under ``tmp_path`` unless overridden."""
    return gather_sync_status(
        state_file=state_file or tmp_path / "sync_state.json",
        token_file=token_file or tmp_path / "sync_token",
        firebase_config=firebase_config or tmp_path / "firebase.json",
    )


class TestBackendDetection:
    """Which backend this machine is configured for, from files alone."""

    def test_no_credentials_is_not_configured(self, tmp_path: Path) -> None:
        """No credentials is not configured."""
        assert _gather(tmp_path).backend == "none"

    def test_a_github_token_alone_is_the_mirror_path(self, tmp_path: Path) -> None:
        """A github token alone is the mirror path."""
        (tmp_path / "sync_token").write_text("tok")

        assert _gather(tmp_path).backend == "github"

    def test_firebase_wins_when_both_exist(self, tmp_path: Path) -> None:
        """Firebase is primary; GitHub is only the cutover mirror."""
        (tmp_path / "sync_token").write_text("tok")
        (tmp_path / "firebase.json").write_text("{}")

        assert _gather(tmp_path).backend == "firebase"


class TestPushState:
    """What the revision cache says about pushes and peers."""

    def test_no_state_file_means_never_pushed(self, tmp_path: Path) -> None:
        """No state file means never pushed."""
        status = _gather(tmp_path)

        assert status.pushed is False
        assert status.peer_count == 0
        assert status.last_push is None

    def test_a_pushed_rev_counts_as_pushed(self, tmp_path: Path) -> None:
        """A pushed rev counts as pushed."""
        (tmp_path / "sync_state.json").write_text(
            json.dumps({"pushed_rev": "abc", "peer_revs": {"a": "1", "b": "2"}})
        )

        status = _gather(tmp_path)

        assert status.pushed is True
        assert status.peer_count == 2
        assert status.last_push is not None

    def test_a_corrupt_state_file_reads_as_nothing_known(self, tmp_path: Path) -> None:
        """A broken cache must not stop the status window from opening."""
        (tmp_path / "sync_state.json").write_text("{not json")

        status = _gather(tmp_path)

        assert status.pushed is False
        assert status.peer_count == 0

    def test_a_non_object_state_file_reads_as_nothing_known(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "sync_state.json").write_text("[]")

        assert _gather(tmp_path).pushed is False

    def test_a_non_dict_peer_revs_counts_as_no_peers(self, tmp_path: Path) -> None:
        """A non dict peer revs counts as no peers."""
        (tmp_path / "sync_state.json").write_text(
            json.dumps({"pushed_rev": "abc", "peer_revs": "not-a-map"})
        )

        assert _gather(tmp_path).peer_count == 0

    def test_an_unstattable_state_file_has_no_timestamp(self, tmp_path: Path) -> None:
        """A path whose parent is a file cannot be stat'd; that is not fatal."""
        blocker = tmp_path / "blocker"
        blocker.write_text("not a directory")

        status = _gather(tmp_path, state_file=blocker / "sync_state.json")

        assert status.last_push is None


class TestHealthy:
    """Configured AND actually pushing -- the distinction that matters."""

    def test_unconfigured_is_not_healthy(self) -> None:
        """Unconfigured is not healthy."""
        status = SyncStatus(
            device_id="u", backend="none", pushed=False, peer_count=0, last_push=None
        )

        assert status.healthy is False

    def test_configured_but_never_pushed_is_not_healthy(self) -> None:
        """The interesting failure: looks fine everywhere, produces no data."""
        status = SyncStatus(
            device_id="u",
            backend="firebase",
            pushed=False,
            peer_count=0,
            last_push=None,
        )

        assert status.healthy is False

    def test_configured_and_pushed_is_healthy(self) -> None:
        """Configured and pushed is healthy."""
        status = SyncStatus(
            device_id="u", backend="firebase", pushed=True, peer_count=1, last_push="x"
        )

        assert status.healthy is True


class TestFormatSyncLine:
    """The one-line rendering used by the window and i3blocks."""

    def test_unconfigured_says_so(self) -> None:
        """Unconfigured says so."""
        status = SyncStatus(
            device_id="u", backend="none", pushed=False, peer_count=0, last_push=None
        )

        assert format_sync_line(status) == "sync not configured"

    def test_never_pushed_names_the_backend(self) -> None:
        """Never pushed names the backend."""
        status = SyncStatus(
            device_id="u",
            backend="firebase",
            pushed=False,
            peer_count=0,
            last_push=None,
        )

        assert "never pushed" in format_sync_line(status)
        assert "firebase" in format_sync_line(status)

    def test_pushed_with_peers_reports_both(self) -> None:
        """Pushed with peers reports both."""
        status = SyncStatus(
            device_id="u",
            backend="firebase",
            pushed=True,
            peer_count=2,
            last_push="2026-08-09 19:05",
        )

        line = format_sync_line(status)

        assert "2026-08-09 19:05" in line
        assert "2 peer(s)" in line

    def test_pushed_with_no_peers_says_no_peers(self) -> None:
        """Pushed with no peers says no peers."""
        status = SyncStatus(
            device_id="u",
            backend="firebase",
            pushed=True,
            peer_count=0,
            last_push="2026-08-09 19:05",
        )

        assert "no peers" in format_sync_line(status)


class TestSyncCliFlag:
    """The --sync flag i3blocks calls."""

    def test_sync_flag_prints_the_backend_line(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--sync must stay on-disk only: safe on every i3blocks tick."""
        with patch(
            "screen_locker.status_view.gather_sync_status",
            return_value=SyncStatus(
                device_id="u",
                backend="firebase",
                pushed=True,
                peer_count=2,
                last_push="2026-08-09 19:05",
            ),
        ):
            main(["--sync"])
        out = capsys.readouterr().out
        assert "firebase" in out
        assert "2 peer(s)" in out
