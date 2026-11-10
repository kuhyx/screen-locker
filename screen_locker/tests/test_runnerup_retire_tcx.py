"""RunnerUp retirement: app-run detection, anchor derivation, marker validation."""

from __future__ import annotations

from datetime import UTC, datetime
import logging
from typing import TYPE_CHECKING

import pytest

from screen_locker import _runnerup_retire_tcx as rt
from screen_locker.tests._retire_helpers import (
    APP,
    END_UNIX,
    credit,
    put_log,
    put_tcx,
)

if TYPE_CHECKING:
    from pathlib import Path

_AT = "2026-11-01T10:45:00+00:00"


def test_run_key_drops_device_prefix_only() -> None:
    """Test run key drops device prefix only."""
    plain = "RunnerUp_2026-08-22-23-51-04_Running.tcx"
    twin = "RunnerUp_Pixel_6a_2026-08-22-23-51-04_Running.tcx"
    assert rt.run_key(twin) == plain
    assert rt.run_key(plain) == plain


def test_list_tcx_skips_dotfiles_other_types_and_missing_dir(tmp_path: Path) -> None:
    """Test list tcx skips dotfiles other types and missing dir."""
    assert rt.list_tcx(tmp_path / "nope") == []
    put_tcx(tmp_path, "a.tcx")
    put_tcx(tmp_path, ".partial.tcx")
    (tmp_path / "a.gpx").write_text("x")
    (tmp_path / "dir.tcx").mkdir()
    assert [p.name for p in rt.list_tcx(tmp_path)] == ["a.tcx"]


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"author": APP}, True),
        ({"creator": APP}, True),
        ({"author": "RunnerUp"}, False),
        ({"author": f"{APP} fork"}, False),
    ],
)
def test_is_app_tcx_reads_author_and_creator(
    tmp_path: Path, kwargs: dict[str, str], expected: bool
) -> None:
    """Test is app tcx reads author and creator."""
    assert rt.is_app_tcx(put_tcx(tmp_path, "r.tcx", **kwargs)) is expected


def test_is_app_tcx_ignores_the_name_in_free_text(tmp_path: Path) -> None:
    """Test is app tcx ignores the name in free text."""
    path = tmp_path / "n.tcx"
    path.write_text(f"<Notes>{APP}</Notes>")
    assert rt.is_app_tcx(path) is False


def test_is_app_tcx_unreadable_is_a_loud_non_app(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test is app tcx unreadable is a loud non app."""
    with caplog.at_level(logging.WARNING):
        assert rt.is_app_tcx(tmp_path) is False
    assert "Cannot read" in caplog.text


def _app_run(tmp_path: Path, name: str = "app.tcx", where: str = "") -> Path:
    """App run."""
    return put_tcx(tmp_path / where if where else tmp_path, name, author=APP)


def test_anchor_is_the_credit_time_of_the_entry_matching_the_run_end(
    tmp_path: Path,
) -> None:
    """Test anchor is the credit time of the entry matching the run end."""
    _app_run(tmp_path, where="processed")
    log = tmp_path / "log.json"
    put_log(
        log,
        {
            "2026-11-01": [credit(_AT, END_UNIX)],
            "2026-11-02": [credit("2026-11-02T09:00:00+00:00", "1700000000.0")],
        },
    )
    found = rt.find_anchor(log, [tmp_path, tmp_path / "processed"])
    assert found == datetime(2026, 11, 1, 10, 45, tzinfo=UTC)


def test_anchor_accepts_a_stringified_end_and_the_earliest_credit(
    tmp_path: Path,
) -> None:
    """Test anchor accepts a stringified end and the earliest credit."""
    _app_run(tmp_path)
    log = tmp_path / "log.json"
    put_log(
        log,
        {
            "a": [credit("2026-11-03T00:00:00+00:00", str(END_UNIX))],
            "b": [credit("2026-11-02T00:00:00+00:00", END_UNIX + 0.4)],
        },
    )
    found = rt.find_anchor(log, [tmp_path])
    assert found == datetime(2026, 11, 2, tzinfo=UTC)


def test_same_day_runnerup_credit_does_not_anchor_the_app_run(tmp_path: Path) -> None:
    """Test same day runnerup credit does not anchor the app run."""
    _app_run(tmp_path)
    log = tmp_path / "log.json"
    put_log(log, {"2026-11-01": [credit(_AT, END_UNIX - 3600)]})
    assert rt.find_anchor(log, [tmp_path]) is None


def test_no_app_run_means_no_anchor(tmp_path: Path) -> None:
    """Test no app run means no anchor."""
    put_tcx(tmp_path, "r.tcx")
    log = tmp_path / "log.json"
    put_log(log, {"d": [credit(_AT, END_UNIX)]})
    assert rt.find_anchor(log, [tmp_path]) is None


def test_unreadable_or_trackless_app_tcx_cannot_anchor(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test unreadable or trackless app tcx cannot anchor."""
    (tmp_path / "bad.tcx").write_text(f"<Author><Name>{APP}</Name></Author>")
    log = tmp_path / "log.json"
    put_log(log, {"d": [credit(_AT, END_UNIX)]})
    with caplog.at_level(logging.WARNING):
        assert rt.find_anchor(log, [tmp_path]) is None
    assert "cannot anchor" in caplog.text


def test_log_entries_that_cannot_match_are_skipped(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test log entries that cannot match are skipped."""
    _app_run(tmp_path)
    log = tmp_path / "log.json"
    put_log(
        log,
        {
            "d": [
                credit(_AT),  # an older entry without completed_at
                credit(_AT, True),
                credit(_AT, "soon"),
                credit(_AT, END_UNIX, kind="manual_workout"),
                {
                    "timestamp": "garbage",
                    "workout_data": {
                        "type": "runnerup_verified",
                        "completed_at": END_UNIX,
                    },
                },
                {"workout_data": None},
            ]
        },
    )
    with caplog.at_level(logging.WARNING):
        assert rt.find_anchor(log, [tmp_path]) is None
    assert "no usable timestamp" in caplog.text


def test_naive_credit_timestamps_are_read_as_local_time(tmp_path: Path) -> None:
    """Test naive credit timestamps are read as local time."""
    _app_run(tmp_path)
    log = tmp_path / "log.json"
    put_log(log, {"d": [credit("2026-11-01T10:45:00", END_UNIX)]})
    found = rt.find_anchor(log, [tmp_path])
    assert found is not None
    assert found.tzinfo is not None


def test_app_run_ends_lists_every_app_run_in_every_folder(tmp_path: Path) -> None:
    """Test app run ends lists every app run in every folder."""
    _app_run(tmp_path, "a.tcx")
    _app_run(tmp_path, "b.tcx", where="processed")
    put_tcx(tmp_path, "r.tcx")
    ends = rt.app_run_ends([tmp_path, tmp_path / "processed"])
    assert ends == [END_UNIX, END_UNIX]
