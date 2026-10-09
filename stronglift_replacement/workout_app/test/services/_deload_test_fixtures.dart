import 'package:workout_app/models/exercise_state.dart';
import 'package:workout_app/models/progression.dart';

/// A synthetic exercise state for deload tests; [maxWeight] is high enough
/// that `targetAfterFailure`'s clamp never interferes.
ExerciseState deloadState({
  String name = 'Deload Lift',
  double weight = 100,
  int reps = 5,
  ProgressionMode mode = ProgressionMode.weight,
  int repsHigh = 12,
  int repsLow = 6,
  int successStreak = 2,
  int failStreak = 1,
}) => ExerciseState(
  name: name,
  weight: weight,
  reps: reps,
  successStreak: successStreak,
  failStreak: failStreak,
  maxWeight: 200,
  successThreshold: 3,
  failThreshold: 2,
  mode: mode,
  repsHigh: repsHigh,
  repsLow: repsLow,
  hasWarmup: true,
  pausedUntil: null,
  restSuccessSecs: kDefaultRestSuccessSecs,
  restFailSecs: kDefaultRestFailSecs,
  restWarmupSecs: kDefaultRestWarmupSecs,
);
