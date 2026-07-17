"""Tests for screen_locker._log_io — the workout-log normalization layer."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import patch

from screen_locker._log_io import load_workout_log, read_raw_log

if TYPE_CHECKING:
    from pathlib import Path


class TestReadRawLog:
    """Tests for read_raw_log (verbatim on-disk shape)."""

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        """Non-existent file → {}."""
        assert read_raw_log(tmp_path / "nope.json") == {}

    def test_returns_contents_verbatim(self, tmp_path: Path) -> None:
        """Values are returned unchanged — dict or list."""
        f = tmp_path / "log.json"
        f.write_text(json.dumps({"2026-07-13": {"workout_data": {"type": "x"}}}))
        assert read_raw_log(f) == {"2026-07-13": {"workout_data": {"type": "x"}}}

    def test_invalid_json_returns_empty(self, tmp_path: Path) -> None:
        """Corrupt JSON → {}."""
        f = tmp_path / "log.json"
        f.write_text("{not json}")
        assert read_raw_log(f) == {}

    def test_oserror_returns_empty(self, tmp_path: Path) -> None:
        """OSError on open → {}."""
        f = tmp_path / "log.json"
        f.write_text("{}")
        with patch("builtins.open", side_effect=OSError("perm")):
            assert read_raw_log(f) == {}

    def test_non_dict_top_level_returns_empty(self, tmp_path: Path) -> None:
        """A JSON list/scalar at the top level is not a log → {}."""
        f = tmp_path / "log.json"
        f.write_text(json.dumps([1, 2, 3]))
        assert read_raw_log(f) == {}


class TestLoadWorkoutLog:
    """Tests for load_workout_log (normalizes both shapes to per-day lists)."""

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        """Non-existent file → {}."""
        assert load_workout_log(tmp_path / "nope.json") == {}

    def test_legacy_dict_value_is_wrapped_in_a_list(self, tmp_path: Path) -> None:
        """The old one-entry-per-day shape reads as a one-element list."""
        entry = {"timestamp": "t", "workout_data": {"type": "runnerup_verified"}}
        f = tmp_path / "log.json"
        f.write_text(json.dumps({"2026-07-12": entry}))
        assert load_workout_log(f) == {"2026-07-12": [entry]}

    def test_list_value_is_passed_through(self, tmp_path: Path) -> None:
        """The new multi-entry shape is returned as-is, order preserved."""
        a = {"workout_data": {"type": "manual_workout"}}
        b = {"workout_data": {"type": "runnerup_verified"}}
        f = tmp_path / "log.json"
        f.write_text(json.dumps({"2026-07-13": [a, b]}))
        assert load_workout_log(f) == {"2026-07-13": [a, b]}

    def test_malformed_list_elements_are_dropped(self, tmp_path: Path) -> None:
        """Non-dict entries inside a day's list are ignored."""
        good = {"workout_data": {"type": "phone_verified"}}
        f = tmp_path / "log.json"
        f.write_text(json.dumps({"2026-07-13": [good, "junk", 7, None]}))
        assert load_workout_log(f) == {"2026-07-13": [good]}

    def test_malformed_day_value_is_skipped(self, tmp_path: Path) -> None:
        """A day whose value is neither dict nor list is omitted entirely."""
        good = {"workout_data": {"type": "phone_verified"}}
        f = tmp_path / "log.json"
        f.write_text(json.dumps({"2026-07-13": good, "2026-07-14": "junk"}))
        assert load_workout_log(f) == {"2026-07-13": [good]}

    def test_mixed_legacy_and_new_shapes(self, tmp_path: Path) -> None:
        """A half-migrated file reads correctly — both shapes coexist."""
        legacy = {"workout_data": {"type": "runnerup_verified"}}
        a = {"workout_data": {"type": "manual_workout"}}
        b = {"workout_data": {"type": "runnerup_verified"}}
        f = tmp_path / "log.json"
        f.write_text(json.dumps({"2026-07-12": legacy, "2026-07-13": [a, b]}))
        assert load_workout_log(f) == {"2026-07-12": [legacy], "2026-07-13": [a, b]}
