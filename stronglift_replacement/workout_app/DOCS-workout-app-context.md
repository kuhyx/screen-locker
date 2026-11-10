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
- The app records one mode: every GPS activity is a run (25 km/h jump cap,
  `Sport="Running"`, `_Running.tcx`); the PC credits all with one rule. No
  run/walk toggle. `decodeTcx` still reads old `_Walking.tcx` imports. Optional
  pace target (`pace_band.dart`, picker `run_pace_picker.dart`); idle map follows
  the user's fix (`idle_location.dart`, display-only); location refused = no
  map and no start, only the red icon. The app uploads a TCX the PC credits unchanged.
  Contract = the PC parser, pinned by `screen_locker/tests/fixtures/run_tcx/`
  (Dart `test/services/tcx_golden_fixture_test.dart` <-> pytest
  `screen_locker/tests/test_run_tcx_golden.py`). Regenerate after a deliberate
  codec change: `UPDATE_GOLDEN=1 flutter test test/services/tcx_golden_fixture_test.dart`.
- File name `RunnerUp_YYYY-MM-DD-HH-MM-SS_<Running>.tcx` (historic: `Walking`), stamp in
  LOCAL time; `<Id>`/`<Time>` UTC `Z`; source tag `kuhy workout_app` in
  `Author/Name` + `Creator/Name`.
- Trackpoints must be <= 30 s apart with cumulative `DistanceMeters`, or the PC
  credits no moving time (`lib/services/run_math.dart` mirrors that rule).
- Thresholds that decide credit live on the PC only, one rule for runs and
  walks alike: a day's summed distance >= 3.5 km OR summed moving time >= 25 min (pairs
  faster than 25 km/h count neither)
  (`screen_locker/_walk_tcx.py`); sport and file-name suffix never matter.
- GPS sits behind `PositionSource` (`position_source*.dart`); imported
  RunnerUp runs are stored with `upload_state='never'` (table CHECK).
- RunnerUp history import (`runnerup_importer.dart`): once, on app start, on
  the phone only (never the sandbox). PROPFINDs `/RunnerUp/processed/`, stores
  every `.tcx` as `runnerup_import`/`never`, then PUTs the dotfile marker
  `/RunnerUp/.workout_app_import.json` = `{"completed_at": ISO-UTC, "count": N,
  "tcx_names": [...]}`. The importer never PUTs a `.tcx` (a top-level one would
  be credited by `runnerup_watch.sh`). A reinstall re-imports and rewrites the
  marker with a new `completed_at`: the PC must not use it as a clock.
- `runs`/`run_points` travel in backup.json (app-made runs only; the RunnerUp
  history comes back from the PC) and in the user export (version 3, all runs).
  Points are one compact JSON string per run.
- dufs login: `dufs_credentials.dart` (`dufs_url`, `dufs_user`, `dufs_password`
  in secure storage).
