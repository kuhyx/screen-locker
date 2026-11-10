"""RunnerUp retirement: validating the app's import marker against processed/."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from screen_locker import _runnerup_retire_tcx as rt
from screen_locker.tests._retire_helpers import APP, put_marker, put_tcx

if TYPE_CHECKING:
    from pathlib import Path


def _processed(tmp_path: Path) -> Path:
    """Processed."""
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
    """Test marker valid counts device twins and ignores app files."""
    processed = _processed(tmp_path)
    marker = put_marker(tmp_path, _LISTED)
    check = rt.check_marker(marker, processed)
    assert check.ok
    assert "2 runs" in check.reason


def test_marker_may_name_the_device_prefixed_copy(tmp_path: Path) -> None:
    """Test marker may name the device prefixed copy."""
    processed = _processed(tmp_path)
    names = ["RunnerUp_Pixel_6a_2026-08-12-17-42-11_Running.tcx", _LISTED[1]]
    assert rt.check_marker(put_marker(tmp_path, names), processed).ok


def test_marker_missing_is_not_valid(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test marker missing is not valid."""
    with caplog.at_level(logging.WARNING):
        check = rt.check_marker(tmp_path / "m.json", tmp_path)
    assert not check.ok
    assert "has not imported yet" in check.reason
    assert "marker problem" in caplog.text


def test_marker_unreadable_and_bad_json(tmp_path: Path) -> None:
    """Test marker unreadable and bad json."""
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
    """Test marker shape errors."""
    marker = tmp_path / "m.json"
    marker.write_text(body)
    check = rt.check_marker(marker, tmp_path)
    assert not check.ok
    assert fragment in check.reason


def test_marker_listing_one_run_twice_is_invalid(tmp_path: Path) -> None:
    """Test marker listing one run twice is invalid."""
    processed = _processed(tmp_path)
    twin = "RunnerUp_Pixel_6a_2026-08-12-17-42-11_Running.tcx"
    marker = put_marker(tmp_path, [_LISTED[0], twin])
    assert "more than once" in rt.check_marker(marker, processed).reason


def test_marker_naming_a_run_not_in_processed_is_invalid(tmp_path: Path) -> None:
    """Test marker naming a run not in processed is invalid."""
    processed = _processed(tmp_path)
    marker = put_marker(tmp_path, [*_LISTED, "RunnerUp_2099-01-01-00-00-00_X.tcx"])
    reason = rt.check_marker(marker, processed).reason
    assert "not in processed/" in reason


def test_marker_missing_a_processed_run_asks_for_a_reimport(tmp_path: Path) -> None:
    """Test marker missing a processed run asks for a reimport."""
    processed = _processed(tmp_path)
    marker = put_marker(tmp_path, _LISTED[:1])
    reason = rt.check_marker(marker, processed).reason
    assert "re-run the app's import" in reason
