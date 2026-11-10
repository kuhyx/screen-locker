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

## GPS runs (foundation, 2026-11-10)
- The app records runs/walks itself and uploads a TCX the PC credits unchanged.
  Contract = the PC parser, pinned by `screen_locker/tests/fixtures/run_tcx/`
  (Dart `test/services/tcx_golden_fixture_test.dart` <-> pytest
  `screen_locker/tests/test_run_tcx_golden.py`). Regenerate after a deliberate
  codec change: `UPDATE_GOLDEN=1 flutter test test/services/tcx_golden_fixture_test.dart`.
- File name `RunnerUp_YYYY-MM-DD-HH-MM-SS_<Running|Walking>.tcx`, stamp in
  LOCAL time; `<Id>`/`<Time>` UTC `Z`; source tag `kuhy workout_app` in
  `Author/Name` + `Creator/Name`.
- Trackpoints must be <= 30 s apart with cumulative `DistanceMeters`, or the PC
  credits no walking time (`lib/services/run_math.dart` mirrors that rule).
- Thresholds that decide credit (3.5 km / 25 min) live on the PC only.
- GPS sits behind `PositionSource` (`position_source*.dart`); imported
  RunnerUp runs are stored with `upload_state='never'` (table CHECK).
