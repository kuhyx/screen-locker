"""RunnerUp retirement: the state file round-trip and its loud failures."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from screen_locker._runnerup_retire_state import RetireState, load_state, save_state

if TYPE_CHECKING:
    from pathlib import Path


def test_state_roundtrip_and_anchor(tmp_path: Path) -> None:
    """Test state roundtrip and anchor."""
    path = tmp_path / "deep" / "s.json"
    assert load_state(path) == RetireState()
    save_state(path, RetireState(anchor_at="2026-11-01T10:45:00+00:00"))
    assert load_state(path).anchor is not None
    assert RetireState().anchor is None


@pytest.mark.parametrize(
    "body", ["{nope", "[]", json.dumps({"anchor_at": "not a date"})]
)
def test_bad_state_is_loud_and_ignored(
    tmp_path: Path, body: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Test bad state is loud and ignored."""
    path = tmp_path / "s.json"
    path.write_text(body)
    with caplog.at_level("WARNING"):
        assert load_state(path) == RetireState()
    assert "Retire state" in caplog.text


def test_unreadable_state_is_loud(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test unreadable state is loud."""
    with caplog.at_level("WARNING"):
        assert load_state(tmp_path) == RetireState()
    assert "unreadable" in caplog.text


def test_state_ignores_unknown_and_non_string_fields(tmp_path: Path) -> None:
    """Test state ignores unknown and non string fields."""
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"done_at": 5, "extra": "x", "backup_path": "/b"}))
    assert load_state(path) == RetireState(backup_path="/b")
