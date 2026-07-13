/// Shared constants for manual (off-app) workout logging.
///
/// These mirror the Python source of truth in the screen-locker package
/// (`screen_locker/_constants.py`, the `MANUAL_WORKOUT_*` values). The two
/// languages cannot share a constants file, so this is a hand-maintained
/// mirror; the cross-language sync-payload fixture (see the manual_workout
/// model test here and its Python twin,
/// `test_manual_workout.py::TestSyncWireFormat`) is the tripwire that catches
/// drift. Keep these values in sync with `_constants.py`.
library;

/// Max manual workouts allowed in any rolling 7-day window.
const int kManualWorkoutBudgetPer7Days = 2;

/// Max manual workouts allowed in any rolling 30-day window.
const int kManualWorkoutBudgetPer30Days = 5;

/// Minimum session length, in minutes, for a manual workout to count.
const int kManualWorkoutMinDurationMinutes = 20;

/// Minimum characters for the "other sport" activity description.
const int kManualWorkoutDescriptionMinChars = 40;

/// Minimum characters required in each reflection field.
const int kManualWorkoutReflectionMinChars = 20;

/// Lowest valid RPE (rate of perceived exertion).
const int kManualWorkoutRpeMin = 1;

/// Highest valid RPE (rate of perceived exertion).
const int kManualWorkoutRpeMax = 10;

/// Record `kind` discriminator marking a manual-workout sync record.
///
/// A StrongLifts session payload has no `kind`; the ingesting PC routes on this
/// value before any session logic, so a manual can never be stamped as a
/// verified session.
const String kManualWorkoutSyncKind = 'manual_workout';
