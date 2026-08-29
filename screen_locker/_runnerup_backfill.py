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
from typing import TYPE_CHECKING

from screen_locker._log_mixin import write_signed_entry

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)


class RunnerUpBackfillMixin:
    """Fills the log from RunnerUp exports for a date or a whole week."""

    def _try_fill_runnerup_for_date(self, date_str: str, log_file: Path) -> bool:
        """Append a verified RunnerUp entry for ``date_str`` if not already logged.

        Appends via the write chokepoint, which dedups by ``workout_id``
        (``runnerup_verified:{date}``): re-scanning a day whose run is already
        recorded is a no-op, but a day that only holds, say, a manual workout
        still gets the run appended alongside it (multiple workouts per day).

        Returns True if a new verified entry was appended for ``date_str``.
        """
        for remote in self._find_runnerup_exports_for_date(date_str):
            data = self._pull_and_parse_tcx(remote)
            if data is None:
                continue
            status, msg = self._validate_runnerup_data(data)
            if status != "verified":
                _logger.warning(
                    "RunnerUp export %s for %s did not qualify (%s): %s",
                    remote,
                    date_str,
                    status,
                    msg,
                )
                continue
            workout_data = {
                "type": "runnerup_verified",
                "source": f"Auto-scanned: {msg}",
                "distance_km": round(data["distance_m"] / 1000, 2),
                "duration_minutes": round(data["duration_seconds"] / 60, 1),
            }
            if write_signed_entry(log_file, date_str, workout_data).appended:
                _logger.info("Auto-filled RunnerUp entry for %s: %s", date_str, msg)
                return True
            return False
        return False

    def _scan_and_fill_week_runnerup(self, log_file: Path) -> int:
        """Scan the current ISO week for RunnerUp runs and append any not logged.

        Returns the count of newly appended entries (0 if phone not connected).
        """
        if not self._has_adb_device():
            _logger.info(
                "Phone not connected; skipping auto-scan for past RunnerUp exports."
            )
            return 0

        now = datetime.now(tz=UTC).astimezone()
        today = now.date()
        week_start = today - timedelta(days=today.weekday())

        filled = 0
        current = week_start
        while current <= today:
            if self._try_fill_runnerup_for_date(current.strftime("%Y-%m-%d"), log_file):
                filled += 1
            current += timedelta(days=1)

        return filled

    # ------------------------------------------------------------------
    # Shared validation
    # ------------------------------------------------------------------
