"""What the Firebase stream does with one ``put``/``patch``: cache, merge, credit.

Holds every device's last-seen log text, so each event recomputes the
cross-device union with the sync's OWN decoder and tombstone rule
(:func:`screen_locker._sync_records.merge_device_texts`) without a single
extra Firebase read. The PC's own log stays in the union -- it carries the
tombstones ``_manual_push`` re-publishes every tick, and dropping it would
let a retracted session be credited again -- but an event that touched only
this PC's log never triggers a pass.

Crediting is :func:`screen_locker._poke_credit.credit_sessions` under the
same in-process lock as the LAN poke handler. ``write_signed_entry`` already
dedups by workout id; the ``seen`` set here only spares the file I/O for
records this daemon has already handed to the ingest.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import time
from typing import TYPE_CHECKING, Final

from screen_locker import _poke_credit
from screen_locker._rtdb_stream import LOG_LEAF, device_updates
from screen_locker._sync_records import _session_records, merge_device_texts

if TYPE_CHECKING:
    import threading

    from screen_locker._rtdb_stream import SseEvent

__all__ = ["DeviceLogCache", "EventResult"]

_logger: Final = logging.getLogger(__name__)


@dataclass(frozen=True)
class EventResult:
    """What one event did, as a sentence for the journal."""

    snapshot: bool
    summary: str


class DeviceLogCache:
    """Every device's last-streamed log text, plus records already ingested."""

    def __init__(
        self, prefix: str, own_ids: frozenset[str], gate: threading.Lock
    ) -> None:
        """Cache logs under ``prefix``; ``own_ids`` are this PC's device dirs."""
        self._prefix = prefix
        self._own_ids = own_ids
        self._gate = gate
        self._texts: dict[str, str] = {}
        self._seen: set[tuple[str, str]] = set()

    def _apply(self, updates: dict[str, str | None], *, full: bool) -> set[str]:
        """Fold ``updates`` into the cache; return the devices that changed."""
        if full:
            fresh = {dev: text for dev, text in updates.items() if text is not None}
            changed = {
                dev
                for dev in fresh.keys() | self._texts.keys()
                if fresh.get(dev) != self._texts.get(dev)
            }
            self._texts = fresh
            return changed
        changed = set()
        for dev, text in updates.items():
            if text == self._texts.get(dev):
                continue  # byte-identical rewrite: nothing to read or credit
            changed.add(dev)
            if text is None:
                self._texts.pop(dev, None)
            else:
                self._texts[dev] = text
        return changed

    def _pending(self) -> list[tuple[str, dict[str, object], str]]:
        """Union records this daemon has not yet handed to the ingest."""
        union = merge_device_texts(
            (
                (f"{self._prefix}/{dev}/{LOG_LEAF}", text)
                for dev, text in sorted(self._texts.items())
            ),
            _session_records,
            "sessions",
        )
        return [
            (rid, payload, str(hlc))
            for rid, (payload, hlc) in sorted(union.items())
            if (rid, str(hlc)) not in self._seen
        ]

    def handle(self, event: SseEvent) -> EventResult:
        """Apply one ``put``/``patch`` and credit whatever it newly brought.

        Raises:
            ValueError: The event's data is not JSON.
            TypeError: The JSON is not the documented ``{path, data}`` shape.
        """
        started = time.perf_counter()
        full, updates = device_updates(event)
        changed = self._apply(updates, full=full)
        devices = ", ".join(sorted(changed)) or "none"
        if not full and not changed:
            return EventResult(
                snapshot=False, summary="byte-identical rewrite; nothing to do"
            )
        foreign = changed - self._own_ids
        if not full and not foreign:
            return EventResult(
                snapshot=False,
                summary=f"only this PC's own log changed ({devices}); no credit",
            )
        pending = self._pending()
        if not pending:
            return EventResult(
                snapshot=full,
                summary=f"{len(self._texts)} device log(s) cached, changed: {devices}; "
                f"every session already handed to the ingest -- no-op, no file I/O "
                f"({_ms(started)} ms)",
            )
        try:
            with self._gate:
                outcome = _poke_credit.credit_sessions(
                    [(rid, payload) for rid, payload, _hlc in pending]
                )
        except Exception:
            # Not a stream problem: keep the connection (a reconnect would
            # re-download the snapshot and fail the same way). Nothing is
            # marked seen, so the next event retries.
            _logger.exception(
                "Crediting %d streamed session(s) failed; the next stream event "
                "retries, and the 15-min workout-sync still covers them",
                len(pending),
            )
            return EventResult(snapshot=full, summary="crediting failed (see above)")
        self._seen.update((rid, hlc) for rid, _payload, hlc in pending)
        return EventResult(
            snapshot=full,
            summary=f"{len(self._texts)} device log(s) cached, changed: {devices}; "
            f"{len(pending)} session(s) checked, {len(outcome.ingested)} newly "
            f"logged {list(outcome.ingested)}, {outcome.credited} credited "
            f"({_ms(started)} ms)",
        )


def _ms(started: float) -> int:
    """Milliseconds since ``started`` (a ``perf_counter`` reading)."""
    return round((time.perf_counter() - started) * 1000)
