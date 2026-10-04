"""Shared helpers for the earner tests: signed ledgers and canned answers.

Ledgers are written where the code under test reads them -- under
``_earned.LEDGER_HOME``, which the autouse redirect (``_isolated_state.py``)
points at tmp_path -- and signed with ``earned_time.entry_signature`` against
a temp key patched onto ``_earned.HMAC_KEY_FILE``. ``_earned`` holds its own
binding of the key and the suite does not redirect it, so a test that reads a
ledger without :func:`signing_key` would read the host's real key.

Plain helpers rather than fixtures, so test modules wrap them in their own
fixtures instead of importing fixture names they never reference.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import json
from typing import TYPE_CHECKING, Any, Final
from unittest.mock import MagicMock, patch

import earned_time

from screen_locker import _earned, _shutdown_base

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

KEY: Final = b"test-key-bytes"


def _any_credit(row: dict[str, object], window: tuple[float, float]) -> bool:
    """EXTRA's rule: any verified credit counts, whenever it landed."""
    del row, window
    return True


# A flat earner the registry does not have yet, for tests that register one
# (``monkeypatch.setattr(earned_time, "EARNERS", (*earned_time.EARNERS, EXTRA))``)
# to pin that nothing in screen-locker needs code for it.
EXTRA: Final = earned_time.Earner(
    name="extra",
    label="Extra",
    gaming_minutes=60,
    shutdown_minutes=60,
    ledger=".local/share/extra_guard/ledger.json",
    match=_any_credit,
)


@contextmanager
def signing_key(tmp_path: Path, content: bytes = KEY) -> Iterator[Path]:
    """Write ``content`` as the HMAC key and point ``_earned`` at it."""
    key = tmp_path / "hmac.key"
    key.write_bytes(content)
    with patch.object(_earned, "HMAC_KEY_FILE", key):
        yield key


def signed(body: dict[str, Any]) -> dict[str, Any]:
    """``body`` plus the ``hmac`` a genuine gate would have written."""
    return {**body, "hmac": earned_time.entry_signature(body, KEY)}


def write_ledger(earner: earned_time.Earner, entries: list[Any]) -> Path:
    """Write ``entries`` as ``earner``'s ledger, where screen-locker reads it."""
    path = _earned.ledger_file(earner)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"entries": entries}), encoding="utf-8")
    return path


def credit(earner: earned_time.Earner, when: datetime | None = None) -> dict[str, Any]:
    """A signed credit row that counts for ``earner`` at ``when`` (default now).

    Whole seconds, floored: a stamp can never land after the reader's "now".
    """
    moment = when or datetime.now().astimezone()
    stamp = int(moment.timestamp())
    detail: dict[str, Any] = (
        {"bonus": "1", "ended_at": str(stamp)}
        if earner.name == earned_time.READING.name
        else {"submitted_at": stamp}
    )
    return signed(
        {
            "entry_id": f"{earner.name}:{stamp}",
            "kind": "credit",
            "day": moment.date().isoformat(),
            "detail": detail,
        }
    )


@contextmanager
def answering(answers: dict[str, bool | None]) -> Iterator[MagicMock]:
    """Every flat earner answers from ``answers`` (absent: ``False``).

    ``earned_today`` is bound twice -- the reset reaches it through
    ``_earned.flat_answers``, the live pass through ``_shutdown_base`` -- so
    both names get the same mock. ``answers`` is read at call time; a test may
    change it after entering.
    """

    def _answer(earner: earned_time.Earner, now: datetime | None = None) -> bool | None:
        del now
        return answers.get(earner.name, False)

    mock = MagicMock(side_effect=_answer)
    with (
        patch.object(_earned, "earned_today", mock),
        patch.object(_shutdown_base, "earned_today", mock),
    ):
        yield mock
