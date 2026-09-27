/// Per-exercise progression state, as stored in SQLite and synced to
/// Firebase.
library;

import 'dart:developer';

import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/models/progression.dart';

/// Default rest after a set that hit its target reps.
const int kDefaultRestSuccessSecs = 180;

/// Default rest after a set that fell short: the longer one.
const int kDefaultRestFailSecs = 300;

/// Default rest after the warmup set.
const int kDefaultRestWarmupSecs = 180;

/// Shortest rest the settings sheet offers.
const int kMinRestSecs = 30;

/// Longest rest the settings sheet offers.
const int kMaxRestSecs = 600;

/// Step of the settings sheet's rest steppers.
const int kRestStepSecs = 15;

/// Per-exercise progression state stored in SQLite.
///
/// Every field is `required` deliberately: a state rebuilt field by field
/// (a threshold edit, a restore) that forgot one would silently reset it,
/// and a required parameter makes the compiler find every such site.
class ExerciseState implements ProgressionInputs {
  /// Creates an [ExerciseState] with all progression fields.
  ExerciseState({
    required this.name,
    required this.weight,
    required this.reps,
    required this.successStreak,
    required this.failStreak,
    required this.maxWeight,
    required this.successThreshold,
    required this.failThreshold,
    required this.mode,
    required this.repsHigh,
    required this.repsLow,
    required this.hasWarmup,
    required this.pausedUntil,
    required this.restSuccessSecs,
    required this.restFailSecs,
    required this.restWarmupSecs,
  });

  /// The state a never-trained [ex] starts from.
  factory ExerciseState.initial(Exercise ex) => ExerciseState(
    name: ex.name,
    weight: ex.weight,
    reps: ex.reps,
    successStreak: 0,
    failStreak: 0,
    maxWeight: ex.maxWeight,
    successThreshold: 3,
    failThreshold: 2,
    mode: ProgressionMode.weight,
    repsHigh: kDefaultRepsHigh,
    repsLow: kDefaultRepsLow,
    hasWarmup: ex.hasWarmup,
    pausedUntil: null,
    restSuccessSecs: kDefaultRestSuccessSecs,
    restFailSecs: kDefaultRestFailSecs,
    restWarmupSecs: kDefaultRestWarmupSecs,
  );

  /// Exercise name (matches [Exercise.name], used as primary key).
  final String name;

  /// Current working weight in kg.
  @override
  double weight;

  /// Current target reps per set.
  @override
  int reps;

  /// Consecutive successful workouts since last progression.
  int successStreak;

  /// Consecutive failed workouts since last regression.
  int failStreak;

  /// Weight cap; reps increase instead of weight when this is reached.
  @override
  final double maxWeight;

  /// Successes needed in a row before the target goes up.
  int successThreshold;

  /// Failures needed in a row before the target goes down.
  int failThreshold;

  /// How the target goes up and down.
  @override
  final ProgressionMode mode;

  /// Double progression: reps at which the weight goes up (`n`).
  @override
  final int repsHigh;

  /// Double progression: reps the heavier weight starts at (`m`).
  @override
  final int repsLow;

  /// Whether this exercise gets a warmup set (and its rest).
  final bool hasWarmup;

  /// The first day the exercise is back after an injury pause (a local
  /// midnight), or null when it is not paused. While paused it is recorded
  /// as FAILED in every workout, so progression steps down instead of the
  /// exercise coming back at the load it left with.
  final DateTime? pausedUntil;

  /// Rest after a set that hit its target reps, in seconds.
  final int restSuccessSecs;

  /// Rest after a set that fell short, in seconds.
  final int restFailSecs;

  /// Rest after the warmup set, in seconds.
  final int restWarmupSecs;

  /// Whether the exercise is paused at [now].
  bool isPausedAt(DateTime now) {
    final until = pausedUntil;
    return until != null && now.isBefore(until);
  }

  /// Returns a copy with the given fields replaced.
  ExerciseState copyWith({
    double? weight,
    int? reps,
    int? successStreak,
    int? failStreak,
    int? successThreshold,
    int? failThreshold,
    ProgressionMode? mode,
    int? repsHigh,
    int? repsLow,
    bool? hasWarmup,
    DateTime? pausedUntil,
    int? restSuccessSecs,
    int? restFailSecs,
    int? restWarmupSecs,
    bool resume = false,
  }) => ExerciseState(
    name: name,
    weight: weight ?? this.weight,
    reps: reps ?? this.reps,
    successStreak: successStreak ?? this.successStreak,
    failStreak: failStreak ?? this.failStreak,
    maxWeight: maxWeight,
    successThreshold: successThreshold ?? this.successThreshold,
    failThreshold: failThreshold ?? this.failThreshold,
    mode: mode ?? this.mode,
    repsHigh: repsHigh ?? this.repsHigh,
    repsLow: repsLow ?? this.repsLow,
    hasWarmup: hasWarmup ?? this.hasWarmup,
    // `resume` exists because a null argument cannot mean "clear it".
    pausedUntil: resume ? null : (pausedUntil ?? this.pausedUntil),
    restSuccessSecs: restSuccessSecs ?? this.restSuccessSecs,
    restFailSecs: restFailSecs ?? this.restFailSecs,
    restWarmupSecs: restWarmupSecs ?? this.restWarmupSecs,
  );
}

/// First local midnight [days] days after [now]: the day a pause started at
/// [now] ends.
DateTime pauseEnd(DateTime now, int days) =>
    DateTime(now.year, now.month, now.day + days);

/// `2026-10-11` for storage; the inverse of [parsePauseDate].
String formatPauseDate(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-'
    '${d.month.toString().padLeft(2, '0')}-'
    '${d.day.toString().padLeft(2, '0')}';

/// Reads a stored pause date; null means not paused.
///
/// Anything unreadable is reported and treated as "not paused": the
/// exercise then shows up in the workout, which is the visible failure.
DateTime? parsePauseDate(Object? raw) {
  if (raw == null) return null;
  final parsed = raw is String ? DateTime.tryParse(raw) : null;
  if (parsed == null) {
    log(
      'ExerciseState: unreadable paused_until "$raw" — treating the '
      'exercise as not paused.',
      level: 900,
    );
  }
  return parsed;
}

const _months = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
];

/// `11 Oct`: how a pause's end date is shown.
String formatShortDate(DateTime d) => '${d.day} ${_months[d.month - 1]}';

/// `3:00`: how a rest length is shown.
String formatRest(int secs) =>
    '${secs ~/ 60}:${(secs % 60).toString().padLeft(2, '0')}';
