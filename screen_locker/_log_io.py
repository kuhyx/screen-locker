"""Single normalization point for reading ``log.json``.

The log is day-keyed and now holds MULTIPLE workouts per day. This module is
the one place that reads the raw file and normalizes both shapes into a
per-day list:

* legacy ``{date: entry}`` — the single ``entry`` is wrapped in a
  one-element list, and
* new ``{date: [entry, ...]}`` — returned as-is.

Kept dependency-free (stdlib only) so any module — including the low-level
``_log_mixin`` and ``_compliance_state`` — can import it without risking an
import cycle. Every consumer reads through :func:`load_workout_log` and
iterates the per-day list rather than assuming one entry per day.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)


def read_raw_log(log_file: Path) -> dict:
    """Load ``log.json`` verbatim (values may be dict or list), or ``{}``.

    Returns the on-disk shape unchanged. Prefer :func:`load_workout_log` for
    reading; this raw form exists for the writer, which rewrites the file, and
    for the one-shot migration.
    """
    if not log_file.exists():
        return {}
    try:
        with log_file.open() as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        _logger.warning(
            "Could not read the workout log at %s (%s) — treating it as EMPTY, "
            "so NO workouts count and the lock will fire until it is readable",
            log_file,
            exc,
        )
        return {}
    if not isinstance(data, dict):
        _logger.warning(
            "Workout log at %s is a %s, not an object of dates — treating it as "
            "EMPTY, so NO workouts count",
            log_file,
            type(data).__name__,
        )
        return {}
    return data


def load_workout_log(log_file: Path) -> dict[str, list[dict]]:
    """Load ``log.json`` normalized to ``{date: [entry, ...]}``.

    Accepts BOTH the legacy day-keyed shape (``{date: entry}``) and the new
    multi-entry shape so old files, rolled-back writers, and mid-migration
    states all read correctly. Each entry is the usual
    ``{timestamp, workout_data, hmac[, workout_id]}`` dict; malformed values
    are dropped. Missing/corrupt file → ``{}``.
    """
    normalized: dict[str, list[dict]] = {}
    for date, value in read_raw_log(log_file).items():
        if isinstance(value, list):
            normalized[date] = [entry for entry in value if isinstance(entry, dict)]
        elif isinstance(value, dict):
            normalized[date] = [value]
    return normalized
