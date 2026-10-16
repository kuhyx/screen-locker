"""Mark a day sick in the test's own (tmp) sickdays pool.

The autouse ``_no_sick_days_by_default`` fixture already points the pool at
``tmp_path``; this writes through ``sickdays.import_legacy``, the one writer
that accepts any date, so a test can mark a fixed past day as well as today.
"""

from __future__ import annotations

from datetime import date

import sickdays


def mark_sick(day: date | str | None = None) -> date:
    """Mark ``day`` (default: today, local) sick and return it."""
    if day is None:
        target = sickdays.today()
    elif isinstance(day, str):
        target = date.fromisoformat(day)
    else:
        target = day
    sickdays.import_legacy([target])
    return target
