#!/usr/bin/env python3
"""Print the shutdown the locker would derive -- today, or a simulated day.

READ-ONLY on the real system: it never runs the sudo helper, never writes
``/etc``, ``shutdown_base.json``, ``grace_floor.json``, ``rest_days.json``,
``log.json`` or the real workout ledger. Simulations run the real code paths
(TCX parsing + walk summing via the RunnerUp backfill, rest-day signing and
verification, ``_shutdown_target.derive``, the grace floor and its lift
bookkeeping) against a temporary directory, with an in-memory shutdown config.

    python -m scripts.preview_shutdown            # today, real ledgers
    python -m scripts.preview_shutdown --day D --walk 25,20
    python -m scripts.preview_shutdown --day D --rest-day
    python -m scripts.preview_shutdown --day D --first-done 18:55 --done anki
    python -m scripts.preview_shutdown --day D --first-done 18:55 --sick-day
    python -m scripts.preview_shutdown --day D --sequence anki@21:00,reading@21:20

Run it with ``PYTHONPATH=~/src/utils/earned_time`` to preview the ladder
(earned_time working tree) instead of the installed version.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta
from pathlib import Path
import sys
import tempfile

import earned_time

from screen_locker import _earned, _grace_floor, _shutdown
from screen_locker._constants import EXTRA_BENEFITS_FILE, SHUTDOWN_CONFIG_FILE
from screen_locker._day import today_str
from screen_locker._earned import hhmm
from screen_locker._extra_benefits import weekly_shutdown_bonus_hours
from screen_locker._rest_day import declare, is_rest_day
from screen_locker._shutdown import read_shutdown_config
from screen_locker._shutdown_target import (
    DayInputs,
    Target,
    day_credit_count,
    derive,
    gather,
)
from scripts._preview_sim import (
    HELPER_CEILING,
    SimRunnerUp,
    SimShutdown,
    sick_history,
    stamp,
    write_walk,
)

_LOG = Path(__file__).resolve().parents[1] / "screen_locker" / "log.json"
_SICK_STEP, _SICK_FLOOR = 60, 18 * 60  # _shutdown's sick-day step and floor


def _say(text: str) -> None:
    sys.stdout.write(f"{text}\n")


def _report(label: str, target: Target) -> None:
    res = target.resolution
    terms = ", ".join(
        f"{t.earner.name}={t.answer}:+{t.shutdown_minutes}" for t in res.terms
    )
    first = (
        datetime.fromtimestamp(target.first_done_at).astimezone().strftime("%H:%M")
        if target.first_done_at
        else "-"
    )
    grace = hhmm(target.grace) if target.grace is not None else "-"
    _say(f"[{label}] {res.day} base {hhmm(res.base.shutdown_minutes)} | {terms}")
    _say(
        f"    rest_day={target.rest_day} earned={hhmm(target.earned)} "
        f"first_done={first} grace={grace} -> SHUTDOWN {hhmm(target.minutes)}"
    )


def _simulate(args: argparse.Namespace, tmp: Path) -> None:
    day = date.fromisoformat(args.day)
    # Every ledger (the workout one included) resolves under the temp dir.
    vars(_earned)["LEDGER_HOME"] = tmp
    log = tmp / "log.json"
    if args.walk:
        drop = tmp / "drop"
        drop.mkdir()
        for index, minutes in enumerate(int(m) for m in args.walk.split(",")):
            write_walk(drop, day, f"{8 + index * 9:02d}:15", minutes)
        SimRunnerUp(drop).fill(day.isoformat(), log)
    rest_file = tmp / "rest_days.json"
    if args.rest_day:
        eve = datetime.combine(day - timedelta(days=1), time(12)).astimezone()
        _say(f"    declare: {declare(day, now=eve, path=rest_file).reason}")
    rest = is_rest_day(day, rest_file)
    done = {n for n in (args.done or "").split(",") if n}
    flat = {e.name: e.name in done for e in _earned.flat_earners()}
    first = stamp(day, args.first_done) if args.first_done else None
    logged = _grace_floor.workout_done_at(log, day)
    times = [t for t in (first, logged) if t is not None]
    target = derive(
        DayInputs(
            day,
            flat,
            day_credit_count(log, day),
            rest_day=rest,
            first_done=min(times, default=None),
            sick_day=sick_history(day, tmp, sick_day=args.sick_day),
        )
    )
    _report("simulated", target)
    if args.sick_day:
        # What the lock screen's sick-day choice then does to that (the
        # existing _apply_earlier_shutdown rule); no grace floor lifts it back.
        after = max(_SICK_FLOOR, target.minutes - _SICK_STEP)
        _say(f"    sick-day step at the lock screen -> SHUTDOWN {hhmm(after)}")


def _sequence(args: argparse.Namespace, tmp: Path) -> None:
    day = date.fromisoformat(args.day)
    for module in (_grace_floor, _shutdown):
        vars(module)["today_str"] = lambda: args.day
    vars(_grace_floor)["GRACE_STATE_FILE"] = tmp / "grace_floor.json"
    done = {e.name: False for e in _earned.flat_earners()}
    start = derive(DayInputs(day, done))
    sim = SimShutdown(start.minutes)
    _say(f"[sequence] {day} start {hhmm(start.minutes)} (nothing done)")
    workouts, first = 0, None
    for step in args.sequence.split(","):
        name, _, at = step.partition("@")
        first = min(first or stamp(day, at), stamp(day, at))
        if name == earned_time.WORKOUT.name:
            workouts += 1
        else:
            done[name] = True
        sim.credit(name, day, first)
        want = derive(DayInputs(day, done, workouts, first_done=first))
        verdict = "" if sim.config[0] == want.minutes else " MISMATCH"
        _say(
            f"    {name}@{at}: config {hhmm(sim.config[0])} "
            f"(derived {hhmm(want.minutes)}{verdict})"
        )


def main() -> int:
    """Print the requested preview. Returns 0."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--day", default=None, help="simulate this day (YYYY-MM-DD)")
    parser.add_argument("--walk", help="moving minutes per walk leg, e.g. 25,20")
    parser.add_argument("--rest-day", action="store_true")
    parser.add_argument("--sick-day", action="store_true")
    parser.add_argument("--first-done", help="HH:MM a ledger earner was first done")
    parser.add_argument("--done", help="flat earners done, e.g. anki,leetcode")
    parser.add_argument("--sequence", help="name@HH:MM,... live passes in order")
    args = parser.parse_args()
    ladder = getattr(earned_time, "on_ladder", None)
    _say(f"earned_time from {Path(earned_time.__file__).parent}")
    if args.day is None:
        today = date.fromisoformat(today_str())
        on = ladder(today) if ladder else False
        _say(f"    ladder in force today: {on}")
        live = read_shutdown_config(SHUTDOWN_CONFIG_FILE)
        _say(
            f"    live config: {tuple(hhmm(m) for m in live) if live else 'unreadable'}"
        )
        target = gather(today, _LOG)
        _report("today, real ledgers", target)
        weekly = weekly_shutdown_bonus_hours(EXTRA_BENEFITS_FILE) * 60
        _say(
            f"    + banked weekly bonus {weekly} min (layered after the reset, "
            f"absorbs the grace lift) -> expected config "
            f"{hhmm(min(HELPER_CEILING, max(target.earned + weekly, target.minutes)))}"
        )
        return 0
    day = date.fromisoformat(args.day)
    _say(f"    ladder in force on {day}: {ladder(day) if ladder else False}")
    with tempfile.TemporaryDirectory(prefix="preview_shutdown_") as raw:
        if args.sequence:
            _sequence(args, Path(raw))
        else:
            _simulate(args, Path(raw))
    return 0


if __name__ == "__main__":
    sys.exit(main())
