#!/usr/bin/env python3
"""Pull or restore the workout app's pre-gap-deload ``exercise_state`` export.

The phone's one-time gap deload backfill saves the pre-cut weights as
``exercise_state_pre_gap_deload.json`` in the app's external files dir
before it cuts anything.

    restore_exercise_state.py pull      # copy it to ~/.local/state/screen-locker/
    restore_exercise_state.py restore   # put those weights back on the phone

``restore`` stamps every row with a newer ``updated_at`` (so the app's import
lets it win) and a fresh ``last_deloaded_at`` (so the gap deload does not cut
the restored weights again before the next session), pushes it as
``restore_exercise_state.json``, restarts the app, and checks that the app
consumed the file. The app then pushes the restored state to Firebase.
Restore goes through the phone, not Firebase: after its first reconcile the
phone never pulls progression, so a Firebase-side write would never land.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

APP_ID = "com.kuhy.workout_app"
REMOTE_DIR = f"/sdcard/Android/data/{APP_ID}/files"
EXPORT_NAME = "exercise_state_pre_gap_deload.json"
RESTORE_NAME = "restore_exercise_state.json"
STATE_DIR = Path.home() / ".local/state/screen-locker"
LOCAL_EXPORT = STATE_DIR / EXPORT_NAME
CONSUME_WAIT_S = 20


def prepare_restore(export: dict[str, Any], now: dt.datetime) -> dict[str, Any]:
    """Return an import document that makes every exported row win."""
    rows = export.get("exercise_state")
    if not isinstance(rows, list) or not rows:
        msg = "export has no exercise_state rows; nothing to restore"
        raise ValueError(msg)
    stamp_ms = int(now.timestamp() * 1000)
    stamp_iso = now.replace(tzinfo=None).isoformat(timespec="microseconds")
    return {
        "format": export.get("format", "workout_app-export"),
        "version": export.get("version", 3),
        "exported_at": stamp_iso,
        "exercise_state": [
            {**row, "updated_at": stamp_ms, "last_deloaded_at": stamp_iso} for row in rows
        ],
    }


def _adb(*args: str) -> subprocess.CompletedProcess[str]:
    serial = os.environ.get("ADB_SERIAL", "23181JEGR08034")
    return subprocess.run(
        ["adb", "-s", serial, *args], check=True, capture_output=True, text=True, timeout=30
    )


def pull() -> Path:
    """Copy the phone's pre-cut export to ``LOCAL_EXPORT``."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _adb("pull", f"{REMOTE_DIR}/{EXPORT_NAME}", str(LOCAL_EXPORT))
    print(f"[OK] pre-deload export saved: {LOCAL_EXPORT}")
    return LOCAL_EXPORT


def restore(source: Path) -> None:
    """Push ``source`` back to the phone and confirm the app imported it."""
    export = json.loads(source.read_text(encoding="utf-8"))
    doc = prepare_restore(export, dt.datetime.now().astimezone())
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / RESTORE_NAME
        path.write_text(json.dumps(doc), encoding="utf-8")
        _adb("push", str(path), f"{REMOTE_DIR}/{RESTORE_NAME}")
    # Force-stop keeps the app's data; the next start imports the file.
    _adb("shell", "am", "force-stop", APP_ID)
    _adb("shell", "monkey", "-p", APP_ID, "-c", "android.intent.category.LAUNCHER", "1")
    deadline = time.monotonic() + CONSUME_WAIT_S
    while time.monotonic() < deadline:
        listing = _adb("shell", "ls", REMOTE_DIR).stdout.split()
        if RESTORE_NAME not in listing:
            names = ", ".join(r["name"] for r in doc["exercise_state"])
            print(f"[OK] restored {len(doc['exercise_state'])} exercise(s): {names}")
            return
        time.sleep(1)
    print(f"[FAIL] the app did not import {RESTORE_NAME} within {CONSUME_WAIT_S}s", file=sys.stderr)
    sys.exit(1)


def main(argv: list[str] | None = None) -> None:
    """Parse the command line and run ``pull`` or ``restore``."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pull", help="copy the phone's pre-deload export to the PC")
    rest = sub.add_parser("restore", help="write the exported weights back")
    rest.add_argument("--file", type=Path, default=LOCAL_EXPORT)
    args = parser.parse_args(argv)
    if args.cmd == "pull":
        pull()
    else:
        restore(args.file)


if __name__ == "__main__":
    main()
