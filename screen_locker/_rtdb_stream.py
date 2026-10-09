"""Pure parsing for a Firebase RTDB REST stream of the device-log node.

``GET <db>/screen-locker-sync/devices.json`` with ``Accept: text/event-stream``
answers with Server-Sent Events: ``put``/``patch`` carry
``{"path": ..., "data": ...}`` relative to the streamed node, plus
``keep-alive``, ``cancel`` and ``auth_revoked``. Everything here is network-free
so it can be unit-tested; the connection itself is
:mod:`screen_locker._session_stream`.

Each device log is ONE JSON-string leaf at ``<device>/log~2Ejson``
(``crdt_sync._fbkeys`` escapes the dot), so an event normalises to "these
devices now hold this text (or nothing)".
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import TYPE_CHECKING, Final

from crdt_sync._firebase import decode_key

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

__all__ = ["LOG_LEAF", "SseEvent", "device_updates", "parse_sse"]

LOG_LEAF: Final = "log.json"


@dataclass(frozen=True)
class SseEvent:
    """One Server-Sent Event: its name and its (joined) data lines."""

    name: str
    data: str


def parse_sse(lines: Iterable[str]) -> Iterator[SseEvent]:
    """Yield events from decoded SSE lines; a blank line ends each event."""
    name = ""
    data: list[str] = []
    for line in lines:
        if not line:
            if name or data:
                yield SseEvent(name or "message", "\n".join(data))
            name, data = "", []
        elif line.startswith("event:"):
            name = line[len("event:") :].strip()
        elif line.startswith("data:"):
            data.append(line[len("data:") :].lstrip())


def _segments(path: str) -> list[str]:
    """``/a/b~2Ec`` -> ``["a", "b.c"]`` (decoded, empty segments dropped)."""
    return [decode_key(part) for part in path.split("/") if part]


def _texts_under(segments: list[str], data: object) -> dict[str, str | None]:
    """Device -> log text for a ``put`` of ``data`` at ``segments``.

    ``None`` means that device's log is gone (deleted, or not a text blob --
    the latter is the caller's to warn about, see :func:`device_updates`).

    Raises:
        TypeError: The data does not have the device-node shape at all.
    """
    if not segments:  # the whole node: {device: {leaf: text}}
        if data is None:
            return {}
        if not isinstance(data, dict):
            msg = f"devices node is {type(data).__name__}, not an object"
            raise TypeError(msg)
        return {decode_key(key): _leaf_text(value) for key, value in data.items()}
    device = segments[0]
    if len(segments) == 1:
        return {device: _leaf_text(data)}
    if segments[1:] == [LOG_LEAF]:
        return {device: data if isinstance(data, str) else None}
    return {}  # something below a device that is not its log: irrelevant


def _leaf_text(device_node: object) -> str | None:
    """The log text inside one ``{leaf: text}`` device node, if any."""
    if not isinstance(device_node, dict):
        return None
    for key, value in device_node.items():
        if decode_key(key) == LOG_LEAF and isinstance(value, str):
            return value
    return None


def device_updates(event: SseEvent) -> tuple[bool, dict[str, str | None]]:
    """Normalise a ``put``/``patch`` into ``(is_full_snapshot, updates)``.

    ``updates`` maps a device id to its log's new full text, or ``None`` when
    it no longer has one. A ``put`` at ``/`` is a full snapshot: the caller
    must REPLACE its cache, since devices missing from it are gone. A
    ``patch`` carries several children whose keys may be multi-segment paths.

    Raises:
        ValueError: The data is not JSON.
        TypeError: The JSON is not the documented ``{path, data}`` shape.
    """
    body = json.loads(event.data)
    if not isinstance(body, dict) or not isinstance(body.get("path"), str):
        msg = f"{event.name} event without a path: {event.data[:120]!r}"
        raise TypeError(msg)
    base = _segments(body["path"])
    if event.name == "put":
        return not base, _texts_under(base, body.get("data"))
    children = body.get("data")
    if not isinstance(children, dict):
        msg = f"patch data is {type(children).__name__}, not an object"
        raise TypeError(msg)
    updates: dict[str, str | None] = {}
    for key, value in children.items():
        updates.update(_texts_under([*base, *_segments(key)], value))
    return False, updates
