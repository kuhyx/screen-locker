# Workout App Context

## Current Task
Implementing design_v2.md improvements.

## Key Decisions
- Active session persisted to SQLite on every tap so force-kill is safe
- Back button: PopScope is still present and pins the route in lock mode
  (workout_screen.dart) — the older "PopScope removed" note here was wrong
- Auto-resume: HomeScreen auto-navigates to workout on first load if session exists
- Break timing is wall-clock (`BreakClock`), never a tick counter: Android
  throttles and Doze suspends timers in a backgrounded isolate
- A `flutter_foreground_task` service owns the deadline for the whole
  workout and shows the status-bar notification; notification presses go
  through a durable prefs queue, never straight into sqflite (the CRDT
  sync layer owns that database's ordering)

## Next Steps
- Clarify user intent on "no break between sets" (contradicts design_v2.md which
  explicitly requested per-set breaks)

REMOVE ME AFTER FINISH
