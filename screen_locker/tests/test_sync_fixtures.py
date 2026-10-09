"""Autouse isolation fixtures for the phone-workout sync layer.

Split out of ``conftest.py`` (already at the repo's 400-line-per-file cap)
and re-exported there so pytest still picks this up as an autouse fixture
for every test in this directory.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture(autouse=True)
def isolate_sync_device_id(tmp_path: Path) -> Iterator[None]:
    """Redirect the persisted device id so tests never mint one for real.

    Without this the first test that syncs writes a uuid into the real
    ``~/.local/share/screen_locker/.device_id``, and this machine's live sync
    identity ends up decided by whichever test happened to run first.
    """
    with patch(
        "screen_locker._device.SYNC_DEVICE_ID_FILE",
        tmp_path / ".device_id",
    ):
        yield


@pytest.fixture(autouse=True)
def no_sync_retry_sleep() -> Iterator[None]:
    """Make the sync retry's backoff instant for every test.

    ``with_sync_retry`` waits 2s + 4s + 8s before giving up, which is right in
    production (it covers the network coming up after boot/resume) but would
    add ~14s to every test that exercises a sync failure. Tests that care about
    the backoff assert on the patched ``sleep`` calls instead -- see
    ``test_sync_retry.py``.
    """
    with patch("screen_locker._sync_retry.sleep"):
        yield
