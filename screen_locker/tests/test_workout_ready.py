"""Tests for waiting on the workout app's ready line.

These use REAL pipes wherever the behaviour under test is what a blocking
file descriptor does -- the partial-line hang that motivated this module is
invisible to a fake whose ``readline`` returns instantly.
"""

from __future__ import annotations

import io
import os

from screen_locker._workout_ready import READY_MARKER, _read_available, await_ready


class TestReadAvailable:
    """Reading a pipe that may hold a partial line.

    These use REAL pipes: the whole point of the code under test is what
    ``readline`` does to a blocking file descriptor, which a fake cannot show.
    """

    def test_reads_a_partial_line_without_waiting_for_a_newline(self) -> None:
        """The regression: ``readline`` would block here until the deadline."""
        read_fd, write_fd = os.pipe()
        with os.fdopen(read_fd, "r") as reader, os.fdopen(write_fd, "w") as writer:
            writer.write("WORKOUT_")
            writer.flush()
            assert _read_available(reader) == "WORKOUT_"

    def test_falls_back_to_readline_without_a_binary_buffer(self) -> None:
        """Plain text objects have no ``.buffer``; a line never blocks there."""
        assert _read_available(io.StringIO("one\ntwo\n")) == "one\n"

    def test_reassembles_a_marker_split_across_reads(self) -> None:
        """A chunk boundary inside the marker must not strand a healthy app."""
        read_fd, write_fd = os.pipe()
        with os.fdopen(read_fd, "r") as reader, os.fdopen(write_fd, "w") as writer:
            writer.write(f"noise\n{READY_MARKER[:8]}")
            writer.flush()

            class _Child:
                stdout = reader

            def _feed(
                _r: object, _w: object, _x: object, _t: float
            ) -> tuple[list[object], list[object], list[object]]:
                writer.write(f"{READY_MARKER[8:]}\n")
                writer.flush()
                return [reader], [], []

            ready, why = await_ready(_Child(), 5.0, _feed)
        assert ready
        assert why == "ready"
