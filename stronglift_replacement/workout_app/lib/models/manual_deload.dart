/// A deload the user asked for, as opposed to one a fail streak earned.
///
/// Only ever a step DOWN: there is deliberately no manual step up, so the
/// target can only climb through finished workouts. The step is
/// `targetAfterFailure`, the same rule a fail streak runs, so a manual deload
/// lands exactly where the automatic one would have.
library;

import 'package:workout_app/models/exercise_state.dart';

/// Where a manual deload was started from; stored in `progression_events`.
enum DeloadSource {
  /// The settings sheet opened from an exercise tile mid-workout.
  workout('workout'),

  /// The settings sheet opened from the Settings screen.
  settings('settings');

  const DeloadSource(this.storageKey);

  /// Value stored in SQLite. Never rename: stored rows hold it.
  final String storageKey;
}

/// `progression_events.kind` of a manual deload.
const String kManualDeloadKind = 'manual_deload';

/// The outcome of `StorageService.manualDeload`.
class ManualDeloadResult {
  /// Creates a result; [state] is null when nothing was changed.
  const ManualDeloadResult({required this.state, required this.reason});

  /// The exercise's state after the deload, or null when it did not apply.
  final ExerciseState? state;

  /// What happened, as a sentence a human can act on.
  final String reason;

  /// Whether the target actually went down.
  bool get applied => state != null;
}

/// One row of `progression_events`: a target change and what caused it.
class ProgressionEvent {
  /// Creates a [ProgressionEvent].
  const ProgressionEvent({
    required this.at,
    required this.exercise,
    required this.kind,
    required this.source,
    required this.fromWeight,
    required this.fromReps,
    required this.toWeight,
    required this.toReps,
  });

  /// When it happened (local time).
  final DateTime at;

  /// Exercise name.
  final String exercise;

  /// What kind of change; [kManualDeloadKind] is the only one so far.
  final String kind;

  /// [DeloadSource.storageKey] of where it was started.
  final String source;

  /// Weight before, in kg.
  final double fromWeight;

  /// Reps before.
  final int fromReps;

  /// Weight after, in kg.
  final double toWeight;

  /// Reps after.
  final int toReps;
}
