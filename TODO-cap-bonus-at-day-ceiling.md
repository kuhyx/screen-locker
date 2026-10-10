# Cap every live shutdown bonus at the day's ceiling, not 24:00 / 23:00

Carried over from the 2026-10-10 tutor-cutover handoff (item 1a, optional).

## what
The live bonus paths clamp at 24:00 (`_shutdown.py` `_MIDNIGHT`, ~:152) and
then at `adjust_shutdown_schedule.sh`'s fixed `RESTORE_CEILING=1380` (23:00).
If `WAKE_MINUTES` ever moves the earned_time ceiling below 23:00, a bonus could
push shutdown past the real ceiling. Cap them at
`earned_time.shutdown_ceiling_for(day)` instead (already wrapped in
`_earned.py` ~:167).

## where
`screen_locker/_shutdown.py`, `screen_locker/adjust_shutdown_schedule.sh`,
`scripts/_preview_sim.py` (`HELPER_CEILING` mirrors `RESTORE_CEILING`).

## must
- The 168-case "do every task => 23:00" invariant test (fc54534) stays green.
- must not: loosen anything — the shell ceiling remains a hard upper bound.

## done
A test that sets a ceiling below 23:00 shows no bonus path exceeding it.

REMOVE ME AFTER FINISH
