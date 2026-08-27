"""Tests for headless manual-workout logging (``--log-manual-workout``).

The point of these is the REFUSALS. A headless entry point is only safe if it
cannot log a workout the phone form would have rejected, so each way of being
invalid is asserted to write nothing and exit non-zero.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from screen_locker._manual_cli import run_manual_log

if TYPE_CHECKING:
    from pathlib import Path

_VALID = (
    "--sport",
    "other",
    "--activity",
    "padel",
    "--date",
    "2026-08-27",
    "--start",
    "17:30",
    "--end",
    "19:00",
    "--location",
    "Padel PGE Narodowy",
    "--transport",
    "By bus, 2 przesiadki",
    "--cost",
    "60 PLN",
    "--rpe",
    "4",
    "--details",
    "Played 6 games 1 did not finish won 3 lost 2",
    "--went-well",
    "my serves got much better, with good speed and accuracy",
    "--to-improve",
    "first game was sluggish, I was tired from work",
    "--feeling",
    "after the tiredness went away the game went very well indeed",
)


def _args(**overrides: str) -> list[str]:
    """Return the valid arg list with ``--flag`` values replaced."""
    args = list(_VALID)
    for flag, value in overrides.items():
        idx = args.index(f"--{flag.replace('_', '-')}")
        args[idx + 1] = value
    return args


def _entries(log_file: Path) -> list[dict]:
    """Return every logged entry, or [] when nothing was written."""
    if not log_file.exists():
        return []
    return [e for day in json.loads(log_file.read_text()).values() for e in day]


def test_logs_a_valid_workout(tmp_path: Path) -> None:
    """A complete draft is signed, filed under its date and reported."""
    log_file = tmp_path / "log.json"

    assert run_manual_log(log_file, _args()) == 0

    (entry,) = _entries(log_file)
    data = entry["workout_data"]
    assert data["type"] == "manual_workout"
    assert data["activity_type"] == "padel"
    assert data["duration_minutes"] == "90.0"
    assert data["rpe"] == 4
    assert entry["workout_id"] == "manual:2026-08-27T17:30"
    assert entry["hmac"]


def test_unsupplied_optional_matches_the_form_default(tmp_path: Path) -> None:
    """``pain_or_injury`` defaults to "none" -- an answer, not a blank.

    An empty string would read as "never asked", which is a different claim
    from the one the form records.
    """
    log_file = tmp_path / "log.json"
    run_manual_log(log_file, _args())

    (entry,) = _entries(log_file)
    assert entry["workout_data"]["pain_or_injury"] == "none"


@pytest.mark.parametrize(
    ("field", "value", "why"),
    [
        ("details", "too short", "under the 40-char activity-details bar"),
        ("went_well", "brief", "under the 20-char reflection bar"),
        ("to_improve", "brief", "under the 20-char reflection bar"),
        ("feeling", "brief", "under the 20-char reflection bar"),
        ("location", "", "required field left blank"),
        ("transport", "", "required field left blank"),
        ("cost", "", "required field left blank"),
        ("rpe", "11", "outside the 1-10 RPE range"),
        ("end", "17:35", "under the minimum workout duration"),
    ],
)
def test_refuses_and_writes_nothing(
    tmp_path: Path, field: str, value: str, why: str
) -> None:
    """Every way of being invalid refuses the whole run.

    Asserted per-field rather than once, because a headless path that logged
    even one of these would be the deleted ``log_manual_workout.py`` again.
    """
    log_file = tmp_path / "log.json"

    assert run_manual_log(log_file, _args(**{field: value})) == 1, why
    assert _entries(log_file) == []


def test_rerunning_the_same_workout_logs_it_once(tmp_path: Path) -> None:
    """The record id is derived from (date, start), so a repeat is a no-op."""
    log_file = tmp_path / "log.json"

    assert run_manual_log(log_file, _args()) == 0
    assert run_manual_log(log_file, _args()) == 1
    assert len(_entries(log_file)) == 1


def test_the_rolling_budget_still_caps_headless_entries(tmp_path: Path) -> None:
    """The third workout in a week is refused, exactly as on the phone."""
    log_file = tmp_path / "log.json"

    assert run_manual_log(log_file, _args(start="07:00", end="08:30")) == 0
    assert run_manual_log(log_file, _args(start="10:00", end="11:30")) == 0
    assert run_manual_log(log_file, _args(start="17:30", end="19:00")) == 1
    assert len(_entries(log_file)) == 2


def test_date_defaults_to_today(tmp_path: Path) -> None:
    """Omitting --date files the workout under today rather than failing."""
    log_file = tmp_path / "log.json"
    args = [a for a in _args() if a not in {"--date", "2026-08-27"}]

    assert run_manual_log(log_file, args) == 0
    assert _entries(log_file)


def test_table_tennis_needs_no_activity_name(tmp_path: Path) -> None:
    """``--activity`` is only meaningful for the open-ended "other" sport.

    Table tennis names itself, but it does demand its own evidence (a match
    count), so the sport-specific rules survive the headless path too.
    """
    log_file = tmp_path / "log.json"
    args = _args(sport="table_tennis")
    args[args.index("--activity") + 1] = ""
    args += [
        "--matches-won",
        "3",
        "--matches-lost",
        "1",
        "--sets-won",
        "7",
        "--sets-lost",
        "4",
        "--racket",
        "Butterfly",
        "--balls",
        "Nittaku",
    ]

    assert run_manual_log(log_file, args) == 0
    assert _entries(log_file)[0]["workout_data"]["activity_type"] == "table tennis"
