#!/usr/bin/env python3
"""Print the shutdown the locker would derive -- today, or a simulated day.

READ-ONLY on the real system: it never runs the sudo helper, never writes
``/etc``, ``shutdown_base.json``, ``grace_floor.json``, ``rest_days.json``,
``log.json`` or the real workout ledger. Simulations run the real code paths
(TCX parsing + walk summing via the RunnerUp backfill, rest-day signing and
verification, ``_shutdown_target.derive``, the sick floor, late credits and the
lift bookkeeping, a temporary ``sickdays`` pool) against a temporary
directory, with an in-memory shutdown config.

    python -m scripts.preview_shutdown            # today, real ledgers, as-is
                                                  # plus as sick / not sick
    python -m scripts.preview_shutdown --day D --walk 25,20
    python -m scripts.preview_shutdown --day D --rest-day
    python -m scripts.preview_shutdown --day D --first-done 18:55 --done anki
    python -m scripts.preview_shutdown --day D --walk 45 --sick-day
    python -m scripts.preview_shutdown --day D --sequence anki@21:00,reading@21:20
    python -m scripts.preview_shutdown --day D --sequence sick@10:00,workout@18:00

Run it with ``PYTHONPATH=~/src/utils/earned_time`` to preview the ladder
(earned_time working tree) instead of the installed version.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from pathlib import Path
import sys
import tempfile

import earned_time

from screen_locker import _earned, _grace_floor, _late_credit, _shutdown, _sick_floor
from screen_locker._constants import SHUTDOWN_CONFIG_FILE
from screen_locker._day import today_str
from screen_locker._earned import hhmm
from screen_locker._rest_day import declare, is_rest_day
from screen_locker._shutdown import read_shutdown_config
from screen_locker._shutdown_target import (
    DayInputs,
    Target,
    day_credit_count,
    derive,
    gather_inputs,
)
from screen_locker._sick import is_sick
from scripts._preview_sim import (
    SICK_STEP,
    SimRunnerUp,
    SimShutdown,
    sick_pool,
    stamp,
    use_temp_pool,
    write_walk,
)

_LOG = Path(__file__).resolve().parents[1] / "screen_locker" / "log.json"


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
    _say(f"[{label}] {res.day} base {hhmm(res.base.shutdown_minutes)} | {terms}")
    _say(
        f"    rest_day={target.rest_day} sick={res.sick} earned={hhmm(target.earned)} "
        f"first_done={first} lift={target.lift} "
        f"-> SHUTDOWN {hhmm(target.minutes)}"
    )


def _simulate(args: argparse.Namespace, tmp: Path) -> None:
    day = date.fromisoformat(args.day)
    # Every ledger (the workout one included) resolves under the temp dir.
    vars(_earned)["LEDGER_HOME"] = tmp
    use_temp_pool(tmp)
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
            sick_day=sick_pool(day, sick_day=args.sick_day),
        )
    )
    _report("simulated", target)


def hhmm_minutes(text: str) -> int:
    """``HH:MM`` as minutes after midnight."""
    hour, minute = (int(p) for p in text.split(":"))
    return hour * 60 + minute


def _sequence(args: argparse.Namespace, tmp: Path) -> None:
    day = date.fromisoformat(args.day)
    for module in (_grace_floor, _late_credit, _shutdown, _sick_floor):
        vars(module)["today_str"] = lambda: args.day
        vars(module)["GRACE_STATE_FILE"] = tmp / "grace_floor.json"
    use_temp_pool(tmp)
    done = {e.name: False for e in _earned.flat_earners()}
    start = derive(DayInputs(day, done))
    sim = SimShutdown(start.minutes)
    _say(f"[sequence] {day} start {hhmm(start.minutes)} (nothing done, not sick)")
    workouts, first, went_late = 0, None, False
    # The real target reads today's real ledgers; the sim's are ``done``.
    vars(_sick_floor)["sick_target"] = lambda d, _log: (
        derive(DayInputs(d, done, workouts, sick_day=True)).minutes
    )
    for step in args.sequence.split(","):
        name, _, at = step.partition("@")
        if name == earned_time.WORKOUT.name:
            workouts += 1
        elif name != SICK_STEP:
            done[name] = True
        if name != SICK_STEP:
            first = min(first or stamp(day, at), stamp(day, at))
        late = name != SICK_STEP and hhmm_minutes(at) >= sim.config[0]
        sim.credit(name, day, stamp(day, at))
        want = derive(
            DayInputs(day, done, workouts, first_done=first, sick_day=is_sick(day))
        )
        # A late credit is live-only, so from it on the derived sum is no judge.
        went_late = went_late or late
        if late:
            verdict = " LATE: from its own time"
        elif went_late:
            verdict = " live, after a late credit"
        else:
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
    parser.add_argument("--log", type=Path, default=_LOG, help="log.json (read-only)")
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
        inputs = gather_inputs(today, args.log)
        target = derive(inputs)
        _report("today, real ledgers", target)
        _say(f"    expected config after the next reset: {hhmm(target.minutes)}")
        for label, sick in (("as sick", True), ("as not sick", False)):
            _report(f"today {label}", derive(replace(inputs, sick_day=sick)))
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
