"""Builders for the RunnerUp retirement tests: TCX files, marker, credit log."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import json
from typing import TYPE_CHECKING, Any

from screen_locker._runnerup_retire import Paths
from screen_locker._runnerup_retire_adb import AdbError, Device

if TYPE_CHECKING:
    from pathlib import Path

_NS = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
APP = "kuhy workout_app"
# 2026-11-01T10:30:00Z, the end of every TCX built by default.
END_UNIX = 1793529000.0


def tcx_text(
    *, author: str = "RunnerUp", creator: str = "", end: str = "2026-11-01T10:30:00Z"
) -> str:
    """A tiny TCX: two trackpoints (the last is the run's end) and an author."""
    creator_xml = f"<Creator><Name>{creator}</Name></Creator>" if creator else ""
    return (
        f'<?xml version="1.0"?><TrainingCenterDatabase xmlns="{_NS}"><Activities>'
        '<Activity Sport="Running"><Id>2026-11-01T10:00:00Z</Id>'
        "<Lap><TotalTimeSeconds>1800</TotalTimeSeconds>"
        "<DistanceMeters>5000</DistanceMeters><Track>"
        "<Trackpoint><Time>2026-11-01T10:00:00Z</Time>"
        "<DistanceMeters>0</DistanceMeters></Trackpoint>"
        f"<Trackpoint><Time>{end}</Time><DistanceMeters>5000</DistanceMeters>"
        f"</Trackpoint></Track></Lap>{creator_xml}</Activity></Activities>"
        f'<Author xsi:type="Application_t" xmlns:xsi="x"><Name>{author}</Name>'
        "</Author></TrainingCenterDatabase>"
    )


def put_tcx(folder: Path, name: str, **kwargs: str) -> Path:
    """Write a TCX named ``name`` into ``folder`` (created if needed)."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(tcx_text(**kwargs), encoding="utf-8")
    return path


def put_marker(watch: Path, names: list[str], count: int | None = None) -> Path:
    """Write the app's import marker into the drop folder."""
    watch.mkdir(parents=True, exist_ok=True)
    marker = watch / ".workout_app_import.json"
    body = {
        "completed_at": "2026-11-02T08:00:00Z",
        "count": len(names) if count is None else count,
        "tcx_names": names,
    }
    marker.write_text(json.dumps(body), encoding="utf-8")
    return marker


def put_log(log_file: Path, entries: dict[str, list[dict[str, Any]]]) -> None:
    """Write a day-keyed credit log."""
    log_file.write_text(json.dumps(entries), encoding="utf-8")


def credit(
    timestamp: str, completed_at: object = None, kind: str = "runnerup_verified"
) -> dict[str, Any]:
    """One log entry as the credit chokepoint writes it."""
    data: dict[str, Any] = {"type": kind}
    if completed_at is not None:
        data["completed_at"] = completed_at
    return {"timestamp": timestamp, "workout_data": data}


ANCHOR = datetime(2026, 11, 1, 10, 45, tzinfo=UTC)
DUE = ANCHOR + timedelta(days=7)
RUN = "RunnerUp_2026-08-12-17-42-11_Running.tcx"


@dataclass
class FakePhone:
    """Records what the retirement asked of the phone."""

    adb: bool = True
    device: Device = field(default_factory=lambda: Device("S", "attached"))
    present: bool = True
    ask_error: AdbError | None = None
    backup_error: Exception | None = None
    uninstall_error: AdbError | None = None
    calls: list[str] = field(default_factory=list)

    def available(self) -> bool:
        """Available."""
        return self.adb

    def find_device(self) -> Device:
        """Find device."""
        if self.ask_error:
            raise self.ask_error
        return self.device

    def installed(self, dev: str, *, hidden: bool = True) -> bool:
        """Installed."""
        self.calls.append(f"installed {dev}")
        return self.present

    def backup(self, dev: str, final: Path) -> tuple[Path, int]:
        """Backup."""
        self.calls.append("backup")
        if self.backup_error:
            raise self.backup_error
        final.mkdir(parents=True)
        return final, 3

    def uninstall(self, dev: str) -> None:
        """Uninstall."""
        self.calls.append("uninstall")
        if self.uninstall_error:
            raise self.uninstall_error


def world(tmp_path: Path, *, anchored: bool = True, marker: bool = True) -> Paths:
    """A drop folder with one RunnerUp run, one app run, and the credit log."""
    paths = Paths(
        tmp_path / "state" / "s.json", tmp_path / "drop", tmp_path / "log.json"
    )
    put_tcx(paths.processed, RUN)
    put_tcx(paths.processed, "app.tcx", author=APP)
    put_log(
        paths.log_file,
        {"d": [credit(ANCHOR.isoformat(), END_UNIX)]} if anchored else {},
    )
    if marker:
        put_marker(paths.watch_dir, [RUN])
    return paths
