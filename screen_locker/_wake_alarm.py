"""rtcwake wake-alarm scheduling, split out of the shutdown mixin.

Split out of :mod:`screen_locker._shutdown` to keep every file under the
250-line cap. Composed back into ``ShutdownMixin`` there, so callers see no
change.
"""

from __future__ import annotations

import calendar
from datetime import UTC, datetime, timedelta
import logging
import subprocess

from screen_locker._constants import ALARM_DAYS, RTCWAKE_BIN, WAKE_AFTER_HOURS

_logger = logging.getLogger(__name__)


class WakeAlarmMixin:
    """Schedules an RTC wake alarm for the next alarm day."""

    # ------------------------------------------------------------------
    # rtcwake integration for weekend wake alarm
    # ------------------------------------------------------------------

    @staticmethod
    def _is_tomorrow_alarm_day() -> bool:
        """Check if tomorrow is an alarm day."""
        tomorrow = datetime.now(tz=UTC) + timedelta(days=1)
        return tomorrow.weekday() in ALARM_DAYS

    @staticmethod
    def _compute_wake_timestamp() -> int:
        """Compute the UTC epoch timestamp for the next wake alarm.

        Returns:
            Epoch seconds WAKE_AFTER_HOURS from now.
        """
        wake_time = datetime.now(tz=UTC) + timedelta(
            hours=WAKE_AFTER_HOURS,
        )
        return calendar.timegm(wake_time.utctimetuple())

    @staticmethod
    def _schedule_rtcwake() -> bool:
        """Set rtcwake to power on the PC after WAKE_AFTER_HOURS.

        Uses ``rtcwake -m disk`` to hibernate immediately while programming
        the RTC to restore power at wake_epoch.  Hibernate is completely
        silent and dark (state written to swap file), making it suitable
        when the PC is in a bedroom.

        Returns:
            True if rtcwake was set successfully, False otherwise.
        """
        wake_epoch = WakeAlarmMixin._compute_wake_timestamp()
        cmd = [
            "/usr/bin/sudo",
            RTCWAKE_BIN,
            "-m",
            "disk",
            "-t",
            str(wake_epoch),
        ]
        try:
            subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.SubprocessError as exc:
            _logger.warning("Failed to set rtcwake: %s", exc)
            return False
        _logger.info(
            "rtcwake set: PC will wake at epoch %d",
            wake_epoch,
        )
        return True

    def schedule_wake_if_needed(self) -> bool:
        """Schedule rtcwake if tomorrow is an alarm day.

        Call this at shutdown time.

        Returns:
            True if wake was scheduled, False if not needed or failed.
        """
        if not self._is_tomorrow_alarm_day():
            _logger.info("Tomorrow is not an alarm day — skipping rtcwake")
            return False
        return self._schedule_rtcwake()
