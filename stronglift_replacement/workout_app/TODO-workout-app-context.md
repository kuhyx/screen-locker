# Workout App Context

## Current Task
Implementing design_v2.md improvements.

## Key Decisions
- Active session persisted to SQLite on every tap so force-kill is safe
- PopScope removed — back button returns to home, workout continues in DB
- Auto-resume: HomeScreen auto-navigates to workout on first load if session exists

## Deferred / Not Yet Implemented
- **Background notifications + break sound when phone is sleeping**: Dart timers
  suspend when app is backgrounded. Needs a native Android foreground service
  (e.g. `flutter_foreground_task` or custom Kotlin service) to keep the break
  countdown running and fire the alert even when the screen is off.
  File as a separate task before marking the app "done."

## Next Steps
- Clarify user intent on "no break between sets" (contradicts design_v2.md which
  explicitly requested per-set breaks)
