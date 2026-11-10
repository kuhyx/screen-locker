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
    put_marker,
    put_tcx,
)

if TYPE_CHECKING:
    from pathlib import Path

_AT = "2026-11-01T10:45:00+00:00"


def test_run_key_drops_device_prefix_only() -> None:
    plain = "RunnerUp_2026-08-22-23-51-04_Running.tcx"
    twin = "RunnerUp_Pixel_6a_2026-08-22-23-51-04_Running.tcx"
    assert rt.run_key(twin) == plain
    assert rt.run_key(plain) == plain


def test_list_tcx_skips_dotfiles_other_types_and_missing_dir(tmp_path: Path) -> None:
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
    assert rt.is_app_tcx(put_tcx(tmp_path, "r.tcx", **kwargs)) is expected


def test_is_app_tcx_ignores_the_name_in_free_text(tmp_path: Path) -> None:
    path = tmp_path / "n.tcx"
    path.write_text(f"<Notes>{APP}</Notes>")
    assert rt.is_app_tcx(path) is False


def test_is_app_tcx_unreadable_is_a_loud_non_app(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        assert rt.is_app_tcx(tmp_path) is False
    assert "Cannot read" in caplog.text


def _app_run(tmp_path: Path, name: str = "app.tcx", where: str = "") -> Path:
    return put_tcx(tmp_path / where if where else tmp_path, name, author=APP)


def test_anchor_is_the_credit_time_of_the_entry_matching_the_run_end(
    tmp_path: Path,
) -> None:
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
    _app_run(tmp_path)
    log = tmp_path / "log.json"
    put_log(log, {"2026-11-01": [credit(_AT, END_UNIX - 3600)]})
    assert rt.find_anchor(log, [tmp_path]) is None


def test_no_app_run_means_no_anchor(tmp_path: Path) -> None:
    put_tcx(tmp_path, "r.tcx")
    log = tmp_path / "log.json"
    put_log(log, {"d": [credit(_AT, END_UNIX)]})
    assert rt.find_anchor(log, [tmp_path]) is None


def test_unreadable_or_trackless_app_tcx_cannot_anchor(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "bad.tcx").write_text(f"<Author><Name>{APP}</Name></Author>")
    log = tmp_path / "log.json"
    put_log(log, {"d": [credit(_AT, END_UNIX)]})
    with caplog.at_level(logging.WARNING):
        assert rt.find_anchor(log, [tmp_path]) is None
    assert "cannot anchor" in caplog.text


def test_log_entries_that_cannot_match_are_skipped(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
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
    _app_run(tmp_path)
    log = tmp_path / "log.json"
    put_log(log, {"d": [credit("2026-11-01T10:45:00", END_UNIX)]})
    found = rt.find_anchor(log, [tmp_path])
    assert found is not None
    assert found.tzinfo is not None


def _processed(tmp_path: Path) -> Path:
    processed = tmp_path / "processed"
    put_tcx(processed, "RunnerUp_2026-08-12-17-42-11_Running.tcx")
    put_tcx(processed, "RunnerUp_Pixel_6a_2026-08-12-17-42-11_Running.tcx")
    put_tcx(processed, "RunnerUp_2026-08-14-00-58-45_Running.tcx")
    put_tcx(processed, "app_2026-11-01.tcx", author=APP)
    return processed


_LISTED = [
    "RunnerUp_2026-08-12-17-42-11_Running.tcx",
    "RunnerUp_2026-08-14-00-58-45_Running.tcx",
]


def test_marker_valid_counts_device_twins_and_ignores_app_files(
    tmp_path: Path,
) -> None:
    processed = _processed(tmp_path)
    marker = put_marker(tmp_path, _LISTED)
    check = rt.check_marker(marker, processed)
    assert check.ok
    assert "2 runs" in check.reason


def test_marker_may_name_the_device_prefixed_copy(tmp_path: Path) -> None:
    processed = _processed(tmp_path)
    names = ["RunnerUp_Pixel_6a_2026-08-12-17-42-11_Running.tcx", _LISTED[1]]
    assert rt.check_marker(put_marker(tmp_path, names), processed).ok


def test_marker_missing_is_not_valid(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        check = rt.check_marker(tmp_path / "m.json", tmp_path)
    assert not check.ok
    assert "has not imported yet" in check.reason
    assert "marker problem" in caplog.text


def test_marker_unreadable_and_bad_json(tmp_path: Path) -> None:
    folder_as_marker = tmp_path / "m"
    folder_as_marker.mkdir()
    assert "unreadable" in rt.check_marker(folder_as_marker, tmp_path).reason
    bad = tmp_path / "bad.json"
    bad.write_text("{nope")
    assert "unreadable" in rt.check_marker(bad, tmp_path).reason


@pytest.mark.parametrize(
    ("body", "fragment"),
    [
        ("[]", "not a JSON object"),
        ('{"count": 0, "tcx_names": []}', "no completed_at"),
        ('{"completed_at": "", "count": 0, "tcx_names": []}', "no completed_at"),
        ('{"completed_at": "t", "count": 0, "tcx_names": "x"}', "not a list"),
        ('{"completed_at": "t", "count": 0, "tcx_names": [1]}', "not a list"),
        ('{"completed_at": "t", "count": 3, "tcx_names": ["a"]}', "count 3"),
        ('{"completed_at": "t", "count": true, "tcx_names": ["a"]}', "count True"),
        ('{"completed_at": "t", "count": "1", "tcx_names": ["a"]}', "count '1'"),
        ('{"completed_at": "t", "count": 1, "tcx_names": ["x/a"]}', "bare file"),
        ('{"completed_at": "t", "count": 1, "tcx_names": [".a"]}', "bare file"),
    ],
)
def test_marker_shape_errors(tmp_path: Path, body: str, fragment: str) -> None:
    marker = tmp_path / "m.json"
    marker.write_text(body)
    check = rt.check_marker(marker, tmp_path)
    assert not check.ok
    assert fragment in check.reason


def test_marker_listing_one_run_twice_is_invalid(tmp_path: Path) -> None:
    processed = _processed(tmp_path)
    twin = "RunnerUp_Pixel_6a_2026-08-12-17-42-11_Running.tcx"
    marker = put_marker(tmp_path, [_LISTED[0], twin])
    assert "more than once" in rt.check_marker(marker, processed).reason


def test_marker_naming_a_run_not_in_processed_is_invalid(tmp_path: Path) -> None:
    processed = _processed(tmp_path)
    marker = put_marker(tmp_path, [*_LISTED, "RunnerUp_2099-01-01-00-00-00_X.tcx"])
    reason = rt.check_marker(marker, processed).reason
    assert "not in processed/" in reason


def test_marker_missing_a_processed_run_asks_for_a_reimport(tmp_path: Path) -> None:
    processed = _processed(tmp_path)
    marker = put_marker(tmp_path, _LISTED[:1])
    reason = rt.check_marker(marker, processed).reason
    assert "re-run the app's import" in reason
