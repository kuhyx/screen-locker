"""Tests for _queue_state and _queue_wait: making a blocked run visible.

On 2026-08-30 the locker decided to lock at 09:01, sat in gatelock's queue
behind ``wake_alarm`` until 11:59, and nothing anywhere said so -- the unit
was ``active``, no window was up, and the status page read a bare "Lock would
fire". These cover the file that closes that blind spot.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from gatelock import QueueResult

from screen_locker._queue_state import (
    clear_queue_wait,
    publish_queue_wait,
    read_queue_wait,
)
from screen_locker._queue_wait import wait_for_screen

_PKG = "screen_locker._queue_state"


class TestPublishAndRead:
    """A blocked run cannot answer for itself, so it writes the answer down."""

    def test_a_published_wait_reads_back(self) -> None:
        """The round trip a status page depends on."""
        publish_queue_wait(("wake_alarm",), 10716.0)
        record = read_queue_wait()
        assert record is not None
        assert record["blocked_by"] == ["wake_alarm"]
        assert record["elapsed_seconds"] == 10716.0

    def test_no_file_means_not_queued(self) -> None:
        """Absence is the normal case and must not read as a failure."""
        clear_queue_wait()
        assert read_queue_wait() is None

    def test_an_empty_blocker_set_clears_the_wait(self) -> None:
        """gatelock signals "clear" with an empty tuple."""
        publish_queue_wait(("wake_alarm",), 5.0)
        publish_queue_wait((), 10.0)
        assert read_queue_wait() is None

    def test_clearing_twice_is_harmless(self) -> None:
        """The locker clears on every exit path, armed or not."""
        clear_queue_wait()
        clear_queue_wait()
        assert read_queue_wait() is None


class TestUnreadableState:
    """Every failure says why: a silent None is a lie about enforcement."""

    def test_an_unwritable_path_warns(self, caplog: MagicMock) -> None:
        """A status page that cannot learn of a wait must say so."""
        with patch.object(Path, "write_text", side_effect=OSError("readonly")):
            publish_queue_wait(("wake_alarm",), 1.0)
        assert "Could not publish the queue wait" in caplog.text

    def test_an_unremovable_path_warns(self, caplog: MagicMock) -> None:
        """Otherwise the page keeps claiming a wait that ended."""
        with patch.object(Path, "unlink", side_effect=OSError("busy")):
            clear_queue_wait()
        assert "Could not clear the queue wait" in caplog.text

    def test_an_unreadable_file_warns(self, caplog: MagicMock) -> None:
        """ "Not queued" is a claim, so a failed read cannot make it quietly."""
        publish_queue_wait(("wake_alarm",), 1.0)
        with patch.object(Path, "read_text", side_effect=OSError("eio")):
            assert read_queue_wait() is None
        assert "Could not read the queue wait" in caplog.text

    def test_unparsable_json_warns(self, caplog: MagicMock, tmp_path: Path) -> None:
        """A truncated write must not crash the status server."""
        target = tmp_path / "queue_state.json"
        target.write_text("{not json", encoding="utf-8")
        with patch(f"{_PKG}.QUEUE_STATE_FILE", target):
            assert read_queue_wait() is None
        assert "unparsable" in caplog.text

    def test_a_non_object_payload_warns(
        self, caplog: MagicMock, tmp_path: Path
    ) -> None:
        """Valid JSON is not automatically the right shape."""
        target = tmp_path / "queue_state.json"
        target.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        with patch(f"{_PKG}.QUEUE_STATE_FILE", target):
            assert read_queue_wait() is None
        assert "not an object" in caplog.text


class TestWaitForScreen:
    """The wait itself: published while it happens, recorded when it ends."""

    @staticmethod
    def _wait(result: QueueResult) -> MagicMock:
        """Run wait_for_screen with a canned queue result.

        Args:
            result: What gatelock's wait_for_turn should return.

        Returns:
            The patched ``record_run_aborted`` mock.
        """
        with (
            patch(
                "screen_locker._queue_wait.wait_for_turn", return_value=result
            ) as turn,
            patch("screen_locker._queue_wait.record_run_aborted") as aborted,
        ):
            wait_for_screen(MagicMock())
        # The publisher must be handed to gatelock, or the wait stays invisible
        # for its whole duration -- only its end would ever be recorded.
        assert turn.call_args.kwargs["on_state"] is publish_queue_wait
        return aborted

    def test_an_unblocked_run_records_nothing(self) -> None:
        """The common case must not add a row to every single locker run."""
        aborted = self._wait(
            QueueResult(waited_seconds=0.0, blocked_by=(), timed_out=False)
        )
        aborted.assert_not_called()

    def test_a_real_wait_is_recorded_with_its_length(self) -> None:
        """The 2h58m gap between "enforced" and a window on screen."""
        aborted = self._wait(
            QueueResult(
                waited_seconds=10716.0, blocked_by=("wake_alarm",), timed_out=False
            )
        )
        reason, detail = aborted.call_args.args
        assert reason == "queued_behind_holder"
        assert "10716s" in detail
        assert "wake_alarm" in detail
        assert "deadline hit" not in detail

    def test_hitting_the_deadline_is_named(self) -> None:
        """Arming anyway is a different event from the holder standing down."""
        aborted = self._wait(
            QueueResult(
                waited_seconds=21600.0, blocked_by=("wake_alarm",), timed_out=True
            )
        )
        assert "deadline hit" in aborted.call_args.args[1]
