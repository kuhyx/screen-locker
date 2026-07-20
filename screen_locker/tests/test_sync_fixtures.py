"""Isolation fixture for the phone-workout GitHub sync token.

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
def isolate_sync_token(tmp_path: Path) -> Iterator[None]:
    """Redirect SYNC_TOKEN_FILE to tmp_path so tests never see a real token.

    Without this, any test calling ``_verify_phone_workout`` would fall
    through to ``pull_synced_workout()``, which -- if a real
    ``~/.config/screen_locker/sync_token`` happens to exist on the host --
    would make a real GitHub API call. Defaulting to a nonexistent tmp_path
    file makes ``read_sync_token()`` return None, the same benign "sync not
    configured" state every existing test already assumes.
    """
    with patch(
        "screen_locker._workout_sync.SYNC_TOKEN_FILE",
        tmp_path / "sync_token",
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
