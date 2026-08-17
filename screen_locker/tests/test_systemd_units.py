"""Tests for the systemd unit files that ARM enforcement.

These exist because of a real outage: on 2026-08-04 systemd logged

    timers.target: Found ordering cycle: early-bird-workout-check.timer/start
      after graphical-session.target/start after basic.target/start after
      timers.target/start - after early-bird-workout-check.timer
    timers.target: Job early-bird-workout-check.timer/start deleted to break
      ordering cycle starting with timers.target/start

and left the timer *disabled*. The Python lock-decision chain was perfectly
healthy the whole time — it simply was never invoked again, so the screen
locker stopped locking for days without a single failing unit or error line.

A timer that is ``WantedBy=timers.target`` must not be ordered ``After=`` a
target that itself comes after ``timers.target``; that closes a dependency
loop and systemd resolves it by silently deleting the job. Parsing is plain
text on purpose: this must run in CI, where no systemd is present. The
complementary *runtime* check ("is it actually enabled and scheduled right
now?") cannot run in a container and lives in
``scripts/check_enforcement_armed.py`` instead.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Targets that are ordered AFTER timers.target. A timer pulled in by
# timers.target may never declare After= on any of these.
_TARGETS_AFTER_TIMERS = frozenset(
    {
        "graphical-session.target",
        "basic.target",
        "graphical.target",
        "multi-user.target",
        "default.target",
    }
)

# Every timer unit that schedules the locker, i.e. every file whose breakage
# silently disarms enforcement.
_ENFORCEMENT_TIMERS = ("early-bird-workout-check.timer", "workout-locker.timer")


def _directive_values(unit_text: str, key: str) -> list[str]:
    """Return every value assigned to ``key``, ignoring comments.

    systemd allows a directive to repeat (``OnCalendar=`` does, deliberately),
    so this returns a list rather than a single value.
    """
    values: list[str] = []
    for raw_line in unit_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        name, sep, value = line.partition("=")
        if sep and name.strip() == key:
            values.append(value.strip())
    return values


@pytest.mark.parametrize("timer_name", _ENFORCEMENT_TIMERS)
class TestEnforcementTimersAreCycleFree:
    """Every locker timer must be installable without an ordering cycle."""

    def test_timer_file_exists(self, timer_name: str) -> None:
        """The unit file ships in the repo, so install_systemd.sh can copy it."""
        assert (REPO_ROOT / timer_name).is_file(), (
            f"{timer_name} is missing; enforcement cannot be scheduled without it"
        )

    def test_no_ordering_cycle_with_timers_target(self, timer_name: str) -> None:
        """No After= on a target that is itself ordered after timers.target.

        This is the exact regression from 2026-08-04. Without this assertion the
        failure is invisible: the unit file looks reasonable, nothing errors, and
        the timer just quietly never fires.
        """
        text = (REPO_ROOT / timer_name).read_text(encoding="utf-8")
        wanted_by = set()
        for value in _directive_values(text, "WantedBy"):
            wanted_by.update(value.split())
        if "timers.target" not in wanted_by:
            pytest.skip(f"{timer_name} is not pulled in by timers.target")

        ordered_after = set()
        for value in _directive_values(text, "After"):
            ordered_after.update(value.split())

        offenders = sorted(ordered_after & _TARGETS_AFTER_TIMERS)
        assert not offenders, (
            f"{timer_name} declares After={offenders} while being "
            f"WantedBy=timers.target. timers.target is ordered before "
            f"basic.target before graphical-session.target, so this closes an "
            f"ordering cycle and systemd deletes the timer job to break it — "
            f"silently disabling enforcement (see 2026-08-04)."
        )

    def test_triggers_the_locker_service(self, timer_name: str) -> None:
        """The timer must actually start the locker, not some other unit."""
        text = (REPO_ROOT / timer_name).read_text(encoding="utf-8")
        assert _directive_values(text, "Unit") == ["workout-locker.service"], (
            f"{timer_name} must trigger workout-locker.service"
        )

    def test_survives_a_missed_trigger(self, timer_name: str) -> None:
        """Persistent=true, so a suspend across the trigger still re-checks.

        A laptop asleep at 08:30 would otherwise skip the re-check entirely and
        leave the early-bird marker banked for the rest of the day.
        """
        assert _directive_values(
            text := (REPO_ROOT / timer_name).read_text(encoding="utf-8"), "Persistent"
        ) == ["true"], (
            f"{timer_name} must set Persistent=true so a missed trigger is "
            f"still run after resume; text was:\n{text}"
        )


class TestEarlyBirdTimerWindows:
    """The early-bird timer must keep closing both grace windows."""

    def test_covers_normal_and_extended_windows(self) -> None:
        """08:30 closes the normal window; 09:05 closes the extended one."""
        text = (REPO_ROOT / "early-bird-workout-check.timer").read_text(
            encoding="utf-8"
        )
        calendars = _directive_values(text, "OnCalendar")
        assert "*-*-* 08:30:00" in calendars
        assert "*-*-* 09:05:00" in calendars


class TestPeriodicLockerTimer:
    """A day/week boundary crossed mid-session must be re-evaluated."""

    def test_repeats_through_the_day(self) -> None:
        """OnCalendar repeats, so enforcement is not login-only.

        The 2026-08-16 -> 08-17 rollover was missed precisely because the
        service is WantedBy=graphical-session.target (one shot per login) and
        the only other trigger was the broken early-bird timer.
        """
        text = (REPO_ROOT / "workout-locker.timer").read_text(encoding="utf-8")
        calendars = _directive_values(text, "OnCalendar")
        assert calendars, "workout-locker.timer must define at least one OnCalendar"
