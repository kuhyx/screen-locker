"""Backfilling the workout log from RunnerUp exports already on the phone.

Split out of :mod:`screen_locker._runnerup_verification` to keep every file
under the 250-line cap. Composed back into ``RunnerUpVerificationMixin``
there, so callers see no change.

Used by the weekly scan: a run exported days ago still counts, so the log is
filled in from whatever RunnerUp kept rather than only from today's check.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
from typing import TYPE_CHECKING, Any

from screen_locker._log_mixin import write_signed_entry
from screen_locker._walk_tcx import activity_day, activity_shortfall

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    # Same shape as ``_manual_sync.OnIngestedCallback``: the appended
    # ``workout_data`` and that day's entries *before* it.
    OnIngestedCallback = Callable[[dict, "list[dict]"], None]

_logger = logging.getLogger(__name__)


def _record(
    log_file: Path,
    date_str: str,
    workout_data: dict[str, Any],
    on_ingested: OnIngestedCallback | None,
) -> bool:
    """Append one verified RunnerUp entry and credit it; False if a duplicate."""
    result = write_signed_entry(log_file, date_str, workout_data)
    if not result.appended:
        return False
    _logger.info(
        "Auto-filled RunnerUp entry for %s: %s", date_str, workout_data["source"]
    )
    if on_ingested is not None:
        on_ingested(workout_data, result.prior_entries)
    return True


class RunnerUpBackfillMixin:
    """Fills the log from RunnerUp exports for a date or a whole week."""

    def _try_fill_runnerup_for_date(
        self,
        date_str: str,
        log_file: Path,
        on_ingested: OnIngestedCallback | None = None,
    ) -> bool:
        """Append a verified RunnerUp entry for ``date_str`` if not already logged.

        Appends via the write chokepoint, which dedups by ``workout_id``
        (``runnerup_verified:{date}``): re-scanning a day whose run is already
        recorded is a no-op, but a day that only holds, say, a manual workout
        still gets the run appended alongside it (multiple workouts per day).

        ``on_ingested(workout_data, prior_entries)`` fires once per appended
        entry, exactly like manual-sync ingestion, so a run pulled off the
        phone earns the same day-scaled reward as every other source. It used
        to earn only a weekly-surplus bonus (+1h per workout above the weekly
        minimum), which is 0 for most of the week: on 2026-09-16 a run synced
        at 20:25 left the config at 20:00 while the daily reset would have
        derived 22:00 from the same log.

        Returns True if a new verified entry was appended for ``date_str``.
        """
        activities = [
            data
            for remote in self._find_runnerup_exports_for_date(date_str)
            if (data := self._pull_and_parse_tcx(remote)) is not None
        ]
        return self._try_fill_day(date_str, activities, log_file, on_ingested)

    @staticmethod
    def _try_fill_day(
        date_str: str,
        activities: list[dict[str, Any]],
        log_file: Path,
        on_ingested: OnIngestedCallback | None,
    ) -> bool:
        """Append the day's activity as its RunnerUp workout, once it adds up.

        One rule for runs and walks alike (see :mod:`screen_locker._walk_tcx`):
        the day's activities are summed, never judged one file at a time. They
        share the ``runnerup_verified:{date}`` slot, so a walk and a run on
        one day are one RunnerUp credit. ``activity: walking`` is kept for the
        phone's history display only; it never decides credit.
        """
        if not activities:
            return False
        day = activity_day(activities)
        if not day.qualifies:
            _logger.warning(
                "RunnerUp activity for %s does not count yet: %s",
                date_str,
                activity_shortfall(day),
            )
            return False
        workout_data: dict[str, Any] = {
            "type": "runnerup_verified",
            "source": f"Auto-scanned: {day.message()}",
            "distance_km": round(day.distance_km, 2),
            "duration_minutes": round(day.moving_minutes, 1),
            "completed_at": day.completed_at,
        }
        if day.all_walks:
            workout_data["activity"] = "walking"
        return _record(log_file, date_str, workout_data, on_ingested)

    def _scan_and_fill_week_runnerup(
        self, log_file: Path, on_ingested: OnIngestedCallback | None = None
    ) -> int:
        """Scan the current ISO week for RunnerUp runs and append any not logged.

        ``on_ingested`` is passed through to every appended entry; see
        :meth:`_try_fill_runnerup_for_date`.

        Returns the count of newly appended entries (0 if no export source --
        neither the WebDAV drop directory nor an adb-visible phone).
        """
        if not self._has_runnerup_source():
            _logger.info(
                "No RunnerUp source (no WebDAV drop dir, phone not connected); "
                "skipping auto-scan for past RunnerUp exports."
            )
            return 0

        now = datetime.now(tz=UTC).astimezone()
        today = now.date()
        week_start = today - timedelta(days=today.weekday())

        filled = 0
        current = week_start
        while current <= today:
            if self._try_fill_runnerup_for_date(
                current.strftime("%Y-%m-%d"), log_file, on_ingested
            ):
                filled += 1
            current += timedelta(days=1)

        return filled

    # ------------------------------------------------------------------
    # Shared validation
    # ------------------------------------------------------------------
