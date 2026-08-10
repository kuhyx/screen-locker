"""Record/payload builders shared by the workout-sync test modules.

Split out of ``test_workout_sync`` (and imported by it and its ``_part2``)
so neither file exceeds the repo's 400-line limit. Everything here builds
crdt-sync wire data the way the phone app actually emits it -- in
particular ``_session_payload`` carries NO ``kind`` field, because session
detection is by shape, and a fixture that invented a ``kind`` would hide
the very bug these tests exist to pin down.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from crdt_sync import Hlc, Record

if TYPE_CHECKING:
    from pathlib import Path
    from types import ModuleType

    import pytest


def _record_json(payload: dict, *, wall_time_ms: int = 1000) -> dict:
    hlc = Hlc(wall_time_ms=wall_time_ms, counter=0, node_id="phone")
    record = Record(id="x", fields={"payload": (payload, hlc)})
    return record.to_dict()


def _session_payload(**extra: object) -> dict:
    """A StrongLifts session as the phone app's ``toJson()`` actually emits it.

    Deliberately carries NO ``kind`` field: session detection is by shape (an
    ``exercises`` list), and keying it on ``kind`` is the bug that made real
    sessions invisible.
    """
    payload: dict = {
        "exercises": [{"name": "Squat", "sets": 5}],
        "duration_seconds": 1800,
    }
    payload.update(extra)
    return payload


def _session_record_dict(
    record_id: str, payload: dict, *, wall_time_ms: int = 1000
) -> dict:
    hlc = Hlc(wall_time_ms=wall_time_ms, counter=0, node_id="phone")
    return Record(id=record_id, fields={"payload": (payload, hlc)}).to_dict()


def _manual_payload(**extra: object) -> dict:
    payload = {"kind": "manual_workout", "date": "2026-07-13"}
    payload.update(extra)
    return payload


def _manual_record_dict(
    record_id: str, payload: dict, *, wall_time_ms: int = 1000
) -> dict:
    hlc = Hlc(wall_time_ms=wall_time_ms, counter=0, node_id="phone")
    return Record(id=record_id, fields={"payload": (payload, hlc)}).to_dict()


def _multi_device_client(device_logs: dict[str, object]) -> MagicMock:
    """A client whose ``devices/<id>/log.json`` tree is ``device_logs``.

    An ``Exception`` value is raised on fetch, so a single dict describes
    healthy, missing and unreachable devices at once.
    """
    client = MagicMock()
    client.list_directory.return_value = list(device_logs)

    def _get(path: str) -> object:
        device = path.split("/")[-2]
        value = device_logs[device]
        if isinstance(value, Exception):
            raise value
        return value

    client.get_file_text.side_effect = _get
    return client


def _firebase_config(
    module: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Point CONFIG_FILE at a real file so the Firebase branch is taken.

    The autouse ``_no_real_firebase_config`` fixture aims it at a nonexistent
    path, so any test wanting the Firebase side must opt back in explicitly.
    """
    config = tmp_path / "firebase.json"
    config.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(module, "CONFIG_FILE", config)
    return config
