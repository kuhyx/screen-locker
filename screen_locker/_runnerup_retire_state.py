"""The retirement's own memory: the anchor, the backup, the done stamp.

One small JSON file (path: ``_runnerup_retire.STATE_FILE``). Written
atomically and only by a real run (``--status`` and ``--dry-run`` never write),
so the file is also the proof that a run happened. The anchor is stored once
and never moved: a later, earlier-looking credit must not push the deadline.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import tempfile

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetireState:
    """What a previous run recorded (all ISO strings, empty until known)."""

    anchor_at: str = ""
    backup_path: str = ""
    done_at: str = ""
    done_reason: str = ""

    @property
    def anchor(self) -> datetime | None:
        """The stored anchor as an aware datetime, or None."""
        return datetime.fromisoformat(self.anchor_at) if self.anchor_at else None


def load_state(path: Path) -> RetireState:
    """Read the state; a missing file is a fresh start, a bad one is loud."""
    if not path.exists():
        return RetireState()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _logger.warning(
            "Retire state %s is unreadable (%s): starting from scratch, so the "
            "anchor is re-derived and the uninstall re-checked",
            path,
            exc,
        )
        return RetireState()
    if not isinstance(raw, dict):
        _logger.warning("Retire state %s is not a JSON object: ignored", path)
        return RetireState()
    known = {f.name for f in fields(RetireState)}
    clean = {k: v for k, v in raw.items() if k in known and isinstance(v, str)}
    try:
        state = RetireState(**clean)
        _ = state.anchor
    except ValueError as exc:
        _logger.warning("Retire state %s holds a bad anchor (%s): ignored", path, exc)
        return RetireState()
    return state


def save_state(path: Path, state: RetireState) -> None:
    """Atomically replace the state file (creates the directory on first write)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".retire-", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(asdict(state), handle, indent=2)
    Path(tmp).replace(path)
