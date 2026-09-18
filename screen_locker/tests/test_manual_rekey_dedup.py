"""A workout rekeyed to its local day is not re-ingested, and never double-budgeted.

Regression for 2026-09-13, second act. The football logged at 00:02 local was
filed under the UTC day and then moved to ``2026-09-13`` by
``scripts/rekey_log_entry.py``, keeping its ``workout_id``
``manual:2026-09-12T14:30``. The 09:40 tick published that entry, pulled it
straight back, and ingested it AGAIN as ``manual:2026-09-13T14:30``:

* ``_already_ingested`` matched only ``sync_record_id``, which a locally
  logged entry never carries;
* the write chokepoint re-derived the id from the payload's (now corrected)
  date, so ``_is_logged_anywhere`` found no twin.

The weekly count collapsed the pair through ``credit_key``, but the
manual-workout budget counted raw entries, so one football read as 2/2 for a
week and the lock screen hid "Log Manual Workout" over a workout logged once.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from screen_locker._log_mixin import write_signed_entry
from screen_locker._manual_sync import ingest_manual_records
from screen_locker._manual_workout import (
    SPORT_OTHER,
    ManualWorkoutDraft,
    build_entry,
    build_sync_payload,
    count_in_window,
    is_budget_exhausted,
    manual_sync_record_id,
)
from screen_locker._weekly_check import count_day_credits

if TYPE_CHECKING:
    from pathlib import Path

UTC_DAY = "2026-09-12"
LOCAL_DAY = "2026-09-13"
TODAY = "2026-09-18"

FOOTBALL = ManualWorkoutDraft(
    sport=SPORT_OTHER,
    start_time="14:30",
    end_time="16:30",
    location_name="Boisko stoczniowiec Płock",
    transport_method="by car ~2hr",
    cost="free (?)",
    rpe=6,
    went_well="Stamina held up for the full two hours of play",
    to_improve="Look around before passing instead of passing immediately",
    overall_feeling="Pretty good session, long drive but worth it once a year",
    activity_type_other="football 11v11",
    activity_details="We played a traditional football game 11v11 with lots of swaps",
    equipment="regular football shoes, white shirt",
)
# Minted at 00:02 local, when the day key was still the UTC day.
FOOTBALL_ID = manual_sync_record_id(UTC_DAY, FOOTBALL.start_time)


def _log_after_rekey(log_file: Path) -> None:
    """Write the log exactly as it stood after the rekey, before the 09:40 tick.

    One football under the local day, keyed on the id it was minted with.
    """
    write_signed_entry(
        log_file, LOCAL_DAY, {**build_entry(FOOTBALL), "workout_id": FOOTBALL_ID}
    )


def _published_twin() -> tuple[str, dict]:
    """The record the PC pushed at 09:40: the minted id, the corrected day."""
    return FOOTBALL_ID, build_sync_payload(FOOTBALL, LOCAL_DAY)


class TestSyncedTwinIsNotReIngested:
    """Pulling back the PC's own published entry is a no-op."""

    def test_rekeyed_entry_is_recognised_by_its_workout_id(
        self, tmp_path: Path
    ) -> None:
        log_file = tmp_path / "log.json"
        _log_after_rekey(log_file)

        ingested = ingest_manual_records(log_file, [_published_twin()], today=LOCAL_DAY)

        assert ingested == []
        assert len(json.loads(log_file.read_text())[LOCAL_DAY]) == 1

    def test_ingested_entry_keeps_the_wire_id(self, tmp_path: Path) -> None:
        """A synced manual is filed under the id it arrived with, not a re-derived one."""
        log_file = tmp_path / "log.json"
        record_id, payload = _published_twin()

        ingest_manual_records(log_file, [(record_id, payload)], today=LOCAL_DAY)

        (entry,) = json.loads(log_file.read_text())[LOCAL_DAY]
        assert entry["workout_id"] == record_id
        assert entry["workout_data"]["sync_record_id"] == record_id


class TestBudgetCountsWorkoutsNotEntries:
    """The manual budget shares ``credit_key`` with the weekly count."""

    def test_synced_copy_of_an_entry_consumes_no_second_slot(
        self, tmp_path: Path
    ) -> None:
        """The exact pair on disk on 2026-09-13: one football, two entries."""
        log_file = tmp_path / "log.json"
        _log_after_rekey(log_file)
        twin = build_entry(FOOTBALL)
        twin["sync_record_id"] = FOOTBALL_ID
        # What the old ingest wrote: same workout under a freshly derived id.
        write_signed_entry(log_file, LOCAL_DAY, twin)
        entries = json.loads(log_file.read_text())[LOCAL_DAY]
        assert len(entries) == 2

        assert count_day_credits(LOCAL_DAY, entries) == 1
        assert count_in_window(log_file, 7, today=TODAY) == 1
        assert not is_budget_exhausted(log_file, today=TODAY)

    def test_two_distinct_manuals_on_one_day_both_consume_a_slot(
        self, tmp_path: Path
    ) -> None:
        """Collapsing is for duplicates only; two real workouts still cost two."""
        log_file = tmp_path / "log.json"
        _log_after_rekey(log_file)
        evening = ManualWorkoutDraft(
            **{**FOOTBALL.__dict__, "start_time": "19:00", "end_time": "20:00"}
        )
        write_signed_entry(log_file, LOCAL_DAY, build_entry(evening))

        assert count_in_window(log_file, 7, today=TODAY) == 2
        assert is_budget_exhausted(log_file, today=TODAY)
