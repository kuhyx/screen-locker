"""Mark a day sick in the test's own (tmp) sickdays pool.

The autouse ``_no_sick_days_by_default`` fixture already points the pool at
``tmp_path``; this writes through ``sickdays.import_legacy``, the one writer
that accepts any date, so a test can mark a fixed past day as well as today.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import sickdays

if TYPE_CHECKING:
    from collections.abc import Iterable


def mark_sick(day: date | str | None = None, *, keep: Iterable[str] = ()) -> date:
    """Mark ``day`` (default: today, local) sick and return it.

    ``keep`` names the lockers (``sickdays.LOCKER_*``) the day keeps active;
    the default keeps none, i.e. every locker stands down, like the lock
    screen's one-tap button.
    """
    if day is None:
        target = sickdays.today()
    elif isinstance(day, str):
        target = date.fromisoformat(day)
    else:
        target = day
    if keep:
        # ``now=target`` makes a past day "today", so a kept past day can be
        # written; import_legacy cannot carry a keep set.
        sickdays.add_sick_day(target, keep=keep, is_free=lambda _day: False, now=target)
    else:
        sickdays.import_legacy([target])
    return target
