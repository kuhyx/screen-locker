"""A ``holds`` stand-in for tests: ``covers`` returns a value or raises it."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime


class FakeHolds:
    """A ``holds`` stand-in: ``covers`` returns the value, or raises it."""

    def __init__(self, covers: object) -> None:
        self._covers = covers
        self.calls: list[tuple[str, datetime | None]] = []

    def covers(self, gate: str, now: datetime | None = None) -> bool:
        """Record the call, then answer like ``holds.covers``."""
        self.calls.append((gate, now))
        if isinstance(self._covers, BaseException):
            raise self._covers
        return bool(self._covers)


def fake_holds_module(*, covers: object) -> FakeHolds:
    """A ``holds`` stand-in to install with ``monkeypatch.setitem(sys.modules, ...)``."""
    return FakeHolds(covers)
