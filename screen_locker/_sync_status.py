"""Read this machine's cross-device sync state from disk, for the status view.

Deliberately on-disk only -- no network, no Firebase sign-in -- because
:func:`screen_locker._status_data.gather_status` is called on every i3blocks
tick and every status-window open. A sync check that hit the RTDB would turn a
status refresh into a rate-limited network round-trip.

What is knowable without the network is still the useful part: which device id
this machine publishes under, whether a backend is configured at all, when it
last pushed, and how many peers it has merged. "Never pushed" and "configured
but failing" look identical from the RTDB; they are distinguishable here.
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import json
import logging
from typing import TYPE_CHECKING

from crdt_sync import CONFIG_FILE as FIREBASE_CONFIG_FILE

from screen_locker._constants import SYNC_STATE_FILE, SYNC_TOKEN_FILE
from screen_locker._device import device_identity

_logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class SyncStatus:
    """This machine's sync posture, as far as on-disk state can tell.

    Attributes:
        device_id: The uuid this machine publishes under.
        backend: ``"firebase"``, ``"github"``, or ``"none"`` -- the highest
            backend this machine is configured for. Firebase is primary and
            GitHub is the cutover mirror, so Firebase wins when both exist.
        pushed: Whether this machine has ever completed a push.
        peer_count: How many other devices' logs it has merged.
        last_push: ISO-ish local timestamp of the last push, or None.
    """

    device_id: str
    backend: str
    pushed: bool
    peer_count: int
    last_push: str | None

    @property
    def healthy(self) -> bool:
        """Whether sync is configured *and* has actually pushed at least once.

        Configured-but-never-pushed is the interesting failure: it looks fine
        in every settings screen and produces no data.
        """
        return self.backend != "none" and self.pushed


def _read_state(path: Path) -> dict[str, object]:
    """Return the parsed sync-state cache, or an empty dict.

    A missing or corrupt cache means "nothing known", never an exception: this
    feeds a status display, and a broken cache must not stop the window from
    opening.
    """
    try:
        parsed = json.loads(path.read_text())
    except FileNotFoundError:
        _logger.warning(
            "No sync state at %s — this machine has not completed a push yet",
            path,
        )
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        _logger.warning(
            "Sync state at %s is unreadable (%s) — the status window will "
            "report this machine as never having pushed",
            path,
            exc,
        )
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _backend(*, firebase_config: Path, token_file: Path) -> str:
    """Return the highest backend this machine is configured for."""
    if firebase_config.is_file():
        return "firebase"
    if token_file.is_file():
        return "github"
    return "none"


def gather_sync_status(
    *,
    state_file: Path = SYNC_STATE_FILE,
    token_file: Path = SYNC_TOKEN_FILE,
    firebase_config: Path = FIREBASE_CONFIG_FILE,
) -> SyncStatus:
    """Read this machine's sync posture from local state only.

    Args:
        state_file: The revision cache written after each push.
        token_file: The GitHub PAT, present only on the mirror path.
        firebase_config: The shared Firebase credential.

    Returns:
        A :class:`SyncStatus`. Never raises and never touches the network.
    """
    state = _read_state(state_file)
    peers = state.get("peer_revs")
    peer_count = len(peers) if isinstance(peers, dict) else 0
    last_push: str | None = None
    try:
        mtime = state_file.stat().st_mtime
    except FileNotFoundError:
        _logger.warning("No sync state at %s — last-push time is unknown", state_file)
        mtime = None
    except OSError as exc:
        _logger.warning(
            "Cannot stat sync state at %s (%s) — last-push time will be blank",
            state_file,
            exc,
        )
        mtime = None
    if mtime is not None:
        # astimezone() with no argument resolves the system local zone, which
        # is what a human reading the status window expects to see.
        last_push = (
            dt.datetime.fromtimestamp(mtime, tz=dt.timezone.utc)
            .astimezone()
            .strftime("%Y-%m-%d %H:%M")
        )

    return SyncStatus(
        device_id=device_identity().device_id,
        backend=_backend(firebase_config=firebase_config, token_file=token_file),
        pushed=bool(state.get("pushed_rev")),
        peer_count=peer_count,
        last_push=last_push,
    )


def format_sync_line(status: SyncStatus) -> str:
    """Render [status] as one line for the status window and i3blocks.

    Args:
        status: The gathered sync posture.

    Returns:
        A single line naming the backend, the last push, and the peer count.
    """
    if status.backend == "none":
        return "sync not configured"
    if not status.pushed:
        return f"{status.backend} · configured but never pushed"
    peers = "no peers" if not status.peer_count else f"{status.peer_count} peer(s)"
    return f"{status.backend} · pushed {status.last_push} · {peers}"
