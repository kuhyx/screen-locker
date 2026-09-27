"""Isolation fixture for the phone-workout GitHub sync token.

Split out of ``conftest.py`` (already at the repo's 400-line-per-file cap)
and re-exported there so pytest still picks this up as an autouse fixture
for every test in this directory.
"""

from __future__ import annotations

from contextlib import ExitStack
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


# Every module that holds SYNC_TOKEN_FILE (~/.config/screen_locker/sync_token)
# by value, bound at import before any fixture could redirect Path.home().
_SYNC_TOKEN_BINDINGS = (
    "_constants",
    "_manual_push",
    "_sync_client",
    "_sync_status",
    "_workout_sync",
)


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
    # read_sync_token moved to _sync_client when _workout_sync was split;
    # _workout_sync still re-exports the constant, so both names must be
    # redirected or a real token on the host leaks into the tests. The rest
    # bind it by value too (only for messages today); patching every binding
    # is what test_home_isolation's module scan checks.
    token = tmp_path / "sync_token"
    with ExitStack() as stack:
        for module in _SYNC_TOKEN_BINDINGS:
            stack.enter_context(patch(f"screen_locker.{module}.SYNC_TOKEN_FILE", token))
        yield


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
