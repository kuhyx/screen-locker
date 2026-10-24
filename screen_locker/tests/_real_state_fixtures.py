"""Autouse fixtures whose one job is keeping tests off real user state.

Split out of ``conftest.py`` for the 250-line cap, and grouped because they
answer the same question in two different ways: what stops this suite from
reading or overwriting the developer's own files? Loaded through
``pytest_plugins`` in ``conftest.py``, so both stay autouse for every test.

The two seams are genuinely different, which is why neither subsumes the
other. ``_isolate_home`` covers paths resolved at *call* time from
``Path.home()``; ``_no_free_days_by_default`` covers paths bound into module
constants at *import* time, which redirecting home afterwards cannot reach.

``pre_ladder`` and ``leetcode_gate_off`` are the opt-in fixtures here:
``pre_ladder`` keeps a test off the real calendar's ladder cutover, the
date-dependent half of the same question; ``leetcode_gate_off`` keeps
ledger-plumbing tests off LeetCode's paid-in-full rule.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
import sys
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _no_free_days_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Never let the lock chain read the developer's real free-day pool.

    ``_isolate_home`` cannot cover this one. freedays binds its paths from
    ``Path.home()`` at *import* time into module constants, so redirecting
    home afterwards leaves them pointing at the real
    ``~/.local/share/freedays``. Every writer resolves through
    ``resolve_paths``, so that is the seam.

    Without it, a real free day on this machine would short-circuit the lock
    chain in every test here -- it is the very first check in the chain --
    and the failures would name early-bird and sick-day logic instead.
    """
    import freedays._api

    monkeypatch.setattr(
        freedays._api,
        "resolve_paths",
        lambda paths: paths or freedays.Paths.under(tmp_path / "freedays"),
    )


@pytest.fixture(autouse=True)
def _no_sick_days_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Never let a test read or write the developer's real sick-day pool.

    Same seam and same reason as ``_no_free_days_by_default``: sickdays binds
    ``~/.local/share/sickdays`` at import time, so only its ``resolve_paths``
    can redirect it. A real sick day would otherwise stand the whole lock
    chain down, and the lock screen's "I'm sick" tests would mark the
    developer's real today sick. ``sync_quietly`` is stubbed so the button's
    background push never reaches Firebase.
    """
    import sickdays
    import sickdays.gui  # so its modules are in sys.modules below

    pool = sickdays.Paths.under(tmp_path / "sickdays")
    # Every sickdays module that bound ``resolve_paths`` by name: the readers
    # (``_api``, which ``stands_down`` / ``kept_lockers`` load through), the
    # writers (``set_kept_lockers`` lives in ``_keep_api``) and the embedded
    # KeepPanel (``sickdays.gui._panel``). Patching only ``_api`` once let a
    # keep edit land in the developer's real pool. ``sync_quietly`` is bound
    # by name the same way (the panel's background push), so it goes too.
    for name, module in list(sys.modules.items()):
        if not name.startswith("sickdays"):
            continue
        if hasattr(module, "resolve_paths"):
            monkeypatch.setattr(module, "resolve_paths", lambda paths: paths or pool)
        if hasattr(module, "sync_quietly"):
            monkeypatch.setattr(module, "sync_quietly", lambda **_kw: False)


@pytest.fixture(autouse=True)
def _no_real_keep_panel() -> Iterator[None]:
    """Never build sickdays' real ``KeepPanel`` (a real ``tk.Frame``) in a test.

    The lock's "choose lockers" overlay embeds it; under the mocked ``tk`` a
    real one would still reach Tcl and write the pool on a click. Tests that
    drive the panel swap in their own recording fake on top of this one.
    """
    with patch("screen_locker._ui_flows_sick_panel.KeepPanel"):
        yield


@pytest.fixture(autouse=True)
def _isolate_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point ``$HOME`` and ``Path.home()`` at tmp_path for every test.

    ``ISOLATED_STATE`` cannot cover this. Everything under ``~/.config`` is
    resolved at *call* time by ``crdt_sync.credential_store_for``
    (``Path.home() / ".config" / app / "firebase_auth.json"``), not bound to a
    module-level constant, so there is no attribute to patch -- the only seam
    is home itself.

    What this protects is a live credential, not a scratch file. A test that
    reaches ``credential_store_for("screen_locker")`` and saves would overwrite
    the machine's real Firebase session with fixture values, and the damage is
    invisible until the next sync fails with HTTP 401. The same redirect also
    covers the sync PAT and the shared ``~/.config/crdt-sync/`` password and
    OAuth secret, which are read the same way.

    ``Path.home()`` is patched as well as ``$HOME``: it consults ``os.environ``
    on POSIX, but only via ``expanduser``, and a test that patches the
    environment differently must not silently regain access to the real one.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    with patch.object(Path, "home", lambda: tmp_path):
        yield


@pytest.fixture(autouse=True)
def _no_real_runnerup_webdav_dir(tmp_path: Path) -> Iterator[None]:
    """Never let the RunnerUp scan read the developer's real WebDAV drop dir.

    ``RUNNERUP_WEBDAV_DIRS`` is bound from ``Path.home()`` at *import* time,
    so ``_isolate_home`` cannot reach it. On this machine the real directory
    holds today's run, which made every "phone absent → not verified" test
    pass verification the day the source was added (2026-09-16). Tests that
    want the local source point the tuple at directories they populate.
    """
    absent = (tmp_path / "no-runnerup-webdav",)
    with patch("screen_locker._runnerup_verification.RUNNERUP_WEBDAV_DIRS", absent):
        yield


@pytest.fixture(autouse=True)
def _no_desktop_notifications(tmp_path: Path) -> Iterator[None]:
    """Keep the credit path off the real desktop and the real lock file.

    Every workout credit ends in ``_credit_notify.send_notification``, which
    runs ``notify-send`` -- without this the suite would pop hundreds of
    "Workout credited" bubbles on the developer's screen, and its budget
    sum would read ledgers and log fail-closed warnings into caplog -- so
    ``notify_workout_credit`` itself is stubbed. The credit also takes
    ``bonus_lock`` on ``_workout_credit.SHUTDOWN_BASE_FILE``, bound at import
    time, so that is redirected too. Tests of the notifier itself capture the
    real function at import time.
    """
    with (
        patch("screen_locker._credit_notify.notify_workout_credit", return_value=True),
        patch(
            "screen_locker._workout_credit.SHUTDOWN_BASE_FILE",
            tmp_path / "credit_shutdown_base.json",
        ),
    ):
        yield


@pytest.fixture
def pre_ladder(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve every day on the pre-ladder rules (the first workout = +2h).

    From ``earned_time.LADDER_FROM`` (2026-10-10) shutdown is read down from
    sleep and each earner's minutes change, so a test pinning the old figures
    would go red on that date by the calendar alone. ``on_ladder`` reads the
    constant at call time and every ladder decision goes through it, so moving
    it out of reach freezes the rules without faking "today" -- which comes
    from several clocks, including the ledger windows the credit rows must hit.
    Opt-in: tests that assert the ladder itself must keep the real cutover.
    """
    monkeypatch.setattr("earned_time._ladder.LADDER_FROM", date.max)


@pytest.fixture
def leetcode_gate_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let a bare LeetCode credit earn, as on a free or stood-down sick day.

    These tests pin the shared ledger plumbing with one credit row per earner.
    Since earned_time 0.18.0 a LeetCode credit alone earns only while the gate
    is off; the paid-in-full rule itself is ``test_leetcode_gate_off.py``.
    """
    monkeypatch.setattr("screen_locker._earned.gate_off", lambda _earner, _day: True)


@pytest.fixture(autouse=True)
def _no_real_night_lockdown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Never let the lock chain read the machine's real night-lockdown stamp.

    ``/var/lib/night-lockdown/locked_at_epoch`` is world-readable, so without
    this every enforce-path test would skip the lock on any evening after the
    real lockdown fired -- and pass in the morning.
    """
    import screen_locker._night_lockdown

    monkeypatch.setattr(
        screen_locker._night_lockdown,
        "NIGHT_LOCKDOWN_STAMP",
        tmp_path / "locked_at_epoch",
    )
