"""Cross-language fixture test for manual-workout budget counting.

The Dart app mirrors this accounting in ``lib/models/manual_workout_budget.dart``
and ``lib/services/workout_sync_service_read.dart``. Each language's own
round-trip test passed happily while the two sides disagreed -- on 2026-08-27
the phone read ``2/2w 4/10m (exhausted)`` for the very records this side read
as ``1/2w 2/10m`` -- so the only thing that catches the drift is a shared
literal both read: ``fixtures/manual_budget_merge.json``. The Dart twin of
this file is ``test/models/manual_budget_merge_fixture_test.dart``; they must
stay in step.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from screen_locker._log_mixin import write_signed_entry
from screen_locker._manual_workout import (
    MANUAL_WORKOUT_TYPE,
    count_in_window,
    is_budget_exhausted,
)

FIXTURE = Path(__file__).parent / "fixtures" / "manual_budget_merge.json"


def _fixture() -> dict[str, Any]:
    """Load the shared cross-language budget fixture."""
    loaded: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return loaded


def _live_payloads(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop tombstoned records, as the sync reader does across the union."""
    return [r["payload"] for r in records if not r["deleted"]]


def _log_from(payloads: list[dict[str, Any]], log_file: Path) -> Path:
    """Write the ingestable payloads into a real signed log file.

    Stubs without ``start_time`` are skipped exactly as ``_manual_sync``
    refuses them ("no workout data to ingest"), so the fixture exercises the
    same admission rule the live ingest applies.
    """
    for payload in payloads:
        if not isinstance(payload.get("start_time"), str):
            continue
        workout_data = {k: v for k, v in payload.items() if k != "kind"}
        workout_data["type"] = MANUAL_WORKOUT_TYPE
        workout_data["workout_id"] = f"manual:{payload['date']}T{payload['start_time']}"
        write_signed_entry(log_file, str(payload["date"]), workout_data)
    return log_file


def test_budget_matches_the_phone_for_the_2026_08_27_divergence(
    tmp_path: Path,
) -> None:
    """The window counts must equal the numbers the Dart twin asserts."""
    fixture = _fixture()
    expected = fixture["expected"]
    today = str(fixture["today"])
    log_file = _log_from(_live_payloads(fixture["records"]), tmp_path / "log.json")

    assert count_in_window(log_file, 7, today=today) == expected["week"]
    assert count_in_window(log_file, 30, today=today) == expected["month"]
    assert is_budget_exhausted(log_file, today=today) is expected["exhausted"]


def test_a_tombstoned_duplicate_frees_its_weekly_slot(tmp_path: Path) -> None:
    """Resurrecting the deleted duplicate must exhaust the week.

    This is the pre-fix behaviour the phone exhibited; asserting it proves the
    tombstone is load-bearing rather than incidentally outside the window.
    """
    fixture = _fixture()
    today = str(fixture["today"])
    resurrected = [r["payload"] for r in fixture["records"]]
    log_file = _log_from(resurrected, tmp_path / "log.json")

    assert count_in_window(log_file, 7, today=today) == 2
    assert is_budget_exhausted(log_file, today=today) is True


def test_an_evidence_less_stub_never_consumes_budget(tmp_path: Path) -> None:
    """The `{type, kind, date}` stub must cost nothing in either window."""
    fixture = _fixture()
    today = str(fixture["today"])
    stub = next(
        r["payload"] for r in fixture["records"] if "start_time" not in r["payload"]
    )
    log_file = _log_from([stub], tmp_path / "log.json")

    assert count_in_window(log_file, 7, today=today) == 0
    assert count_in_window(log_file, 30, today=today) == 0
