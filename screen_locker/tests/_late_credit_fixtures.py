"""Pinning the clock an untimed credit is stamped with.

Re-exported from ``conftest`` rather than defined there so neither file
exceeds the repo's line limit.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from screen_locker import _late_credit

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _untimed_credits_land_at_noon() -> Iterator[None]:
    """A credit with no time of its own (``at=None``) lands at today's noon.

    ``at=None`` means "now", and a suite run after a test's configured
    shutdown (18:00, say) made every such credit late: the same tests went red
    at 18:01. Noon is before any shutdown, so only tests that pass ``at=``
    (or re-patch ``_late_credit._now``) take the late path.
    """
    noon = datetime.now(tz=UTC).astimezone().replace(hour=12, minute=0, second=0)
    with patch.object(_late_credit, "_now", return_value=noon.timestamp()):
        yield
