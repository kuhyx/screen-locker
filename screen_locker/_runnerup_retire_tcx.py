"""What the RunnerUp retirement reads off disk: app runs, the marker, the anchor.

Split from :mod:`screen_locker._runnerup_retire` (250-line cap). Everything
here is read-only; nothing touches the phone.

Telling the two sources apart is done on the TCX *content* (``<Author>`` or
``<Creator>`` named ``kuhy workout_app``, the app's ``kRunSourceName``), never
on the file name: the app may name its files however it likes.

The anchor is "when the PC first CREDITED an app run". The credit chokepoint
(``log.json``) stores a run's TCX end as ``completed_at`` on its
``runnerup_verified`` entry and stamps the entry itself with the moment the PC
wrote it. So the anchor is the ``timestamp`` of the entry whose
``completed_at`` equals an app TCX's last trackpoint. Joining on the end time
(not the day) is what makes a same-day RunnerUp run, which fills the day's one
credit slot first, correctly yield no anchor for the app run.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import logging
import re
from typing import TYPE_CHECKING, Any

from screen_locker._log_io import load_workout_log
from screen_locker._runnerup_tcx import parse_tcx_file

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

_logger = logging.getLogger(__name__)

APP_SOURCE_NAME = "kuhy workout_app"
_APP_RE = re.compile(
    rb"<(?:Author|Creator)\b[^>]*>\s*<Name>\s*"
    + re.escape(APP_SOURCE_NAME.encode())
    + rb"\s*</Name>"
)
# The WebDAV copy of a RunnerUp export may carry the device name
# (RunnerUp_Pixel_6a_2026-...) that the phone's own copy lacks.
_DEVICE_PREFIX = re.compile(r"^RunnerUp_(?:[A-Za-z0-9]+_)*?(?=\d{4}-\d{2}-\d{2}-)")
_END_TOLERANCE_S = 1.0


def run_key(name: str) -> str:
    """A run's identity: its file name without any device-name prefix."""
    return _DEVICE_PREFIX.sub("RunnerUp_", name)


def list_tcx(directory: Path) -> list[Path]:
    """Finished ``*.tcx`` files directly in ``directory`` (dotfiles are partial)."""
    if not directory.is_dir():
        return []
    return sorted(
        p for p in directory.glob("*.tcx") if p.is_file() and not p.name.startswith(".")
    )


def is_app_tcx(path: Path) -> bool:
    """Whether the TCX names the new app as its author or creator."""
    try:
        data = path.read_bytes()
    except OSError as exc:
        _logger.warning(
            "Cannot read %s (%s): counting it as a RunnerUp file", path, exc
        )
        return False
    return bool(_APP_RE.search(data))


def _ended_at(path: Path) -> float | None:
    """The run's end exactly as the credit path computed it (same parser)."""
    data = parse_tcx_file(str(path))
    if data is None or data.get("ended_at") is None:
        _logger.warning("App TCX %s has no usable end time: it cannot anchor", path)
        return None
    return float(data["ended_at"])


def _credited_at(entry: dict[str, Any]) -> datetime | None:
    try:
        stamp = datetime.fromisoformat(str(entry["timestamp"]))
    except (KeyError, ValueError) as exc:
        _logger.warning("Credit entry has no usable timestamp (%r): skipped", exc)
        return None
    return stamp if stamp.tzinfo else stamp.astimezone()


def _as_unix(raw: object) -> float | None:
    """A unix time from a number or numeric string (the log stores both)."""
    if isinstance(raw, int | float) and not isinstance(raw, bool):
        return float(raw)
    if isinstance(raw, str) and re.fullmatch(r"\d+(\.\d+)?", raw):
        return float(raw)
    return None


def _credit_ends(log_file: Path) -> list[tuple[float, datetime]]:
    """``(TCX end, PC credit time)`` of every credited run that recorded its end."""
    found: list[tuple[float, datetime]] = []
    for entries in load_workout_log(log_file).values():
        for entry in entries:
            data = entry.get("workout_data") or {}
            if data.get("type") != "runnerup_verified":
                continue
            end = _as_unix(data.get("completed_at"))
            if end is None:
                continue  # an older entry that never stored its run's end
            when = _credited_at(entry)
            if when is not None:
                found.append((end, when))
    return found


def app_run_ends(dirs: Iterable[Path]) -> list[float]:
    """The end time of every app-authored TCX that has a usable one."""
    return [
        end
        for directory in dirs
        for path in list_tcx(directory)
        if is_app_tcx(path) and (end := _ended_at(path)) is not None
    ]


def find_anchor(log_file: Path, dirs: Iterable[Path]) -> datetime | None:
    """When the PC first credited an app-recorded run, or None if it never did."""
    ends = app_run_ends(dirs)
    credited = [
        when
        for run_end, when in _credit_ends(log_file)
        if any(abs(run_end - end) <= _END_TOLERANCE_S for end in ends)
    ]
    return min(credited) if credited else None


@dataclass(frozen=True)
class MarkerCheck:
    """Verdict on the app's historic-import marker."""

    ok: bool
    reason: str


def _bad(reason: str) -> MarkerCheck:
    return MarkerCheck(ok=False, reason=reason)


def _marker_names(marker: object) -> tuple[list[str] | None, str]:
    """The marker's ``tcx_names`` if its shape is valid, else a reason."""
    if not isinstance(marker, dict):
        return None, "marker is not a JSON object"
    names, count = marker.get("tcx_names"), marker.get("count")
    if not isinstance(marker.get("completed_at"), str) or not marker["completed_at"]:
        return None, "marker has no completed_at"
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        return None, "marker tcx_names is not a list of names"
    if isinstance(count, bool) or not isinstance(count, int) or count != len(names):
        return None, f"marker count {count!r} != {len(names)} listed names"
    if any("/" in n or n.startswith(".") for n in names):
        return None, "marker tcx_names must be bare file names"
    return names, ""


def _read_marker(marker_file: Path) -> tuple[object, str]:
    """The parsed marker JSON, or ``(None, why it could not be read)``."""
    if not marker_file.exists():
        why = f"{marker_file} is missing: the app has not imported yet"
    else:
        try:
            return json.loads(marker_file.read_text(encoding="utf-8")), ""
        except (OSError, ValueError) as exc:
            why = f"{marker_file} is unreadable ({exc})"
            _logger.warning("Import marker problem: %s", why)
            return None, why
    _logger.warning("Import marker problem: %s", why)
    return None, why


def _compare(names: list[str], processed: Path) -> MarkerCheck:
    listed = {run_key(n) for n in names}
    if len(listed) != len(names):
        return _bad("marker lists the same run more than once")
    have = {run_key(p.name) for p in list_tcx(processed) if not is_app_tcx(p)}
    if absent := sorted(listed - have):
        return _bad(f"{len(absent)} listed run(s) not in processed/: {absent[:3]}")
    if unlisted := sorted(have - listed):
        return _bad(
            f"{len(unlisted)} RunnerUp run(s) in processed/ are not in the "
            f"marker ({unlisted[:3]}): re-run the app's import"
        )
    return MarkerCheck(ok=True, reason=f"{len(listed)} runs match")


def check_marker(marker_file: Path, processed: Path) -> MarkerCheck:
    """Validate the app's import marker against what ``processed/`` really holds.

    Valid means: the file parses, ``count`` equals the number of listed names,
    and the listed runs are exactly the RunnerUp-recorded (non-app) runs in
    ``processed/``. A run is counted once however many copies exist (the
    device-prefixed WebDAV twin and the phone-named copy are one run).
    """
    marker, why = _read_marker(marker_file)
    if why:
        return _bad(why)
    names, reason = _marker_names(marker)
    return _compare(names, processed) if names is not None else _bad(reason)
