/// All set results for one exercise in a workout session.
library;

import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/models/set_result.dart';

/// Aggregated results for a single exercise across all its sets in a session.
class ExerciseResult {
  /// Creates a result for [exercise] with the given [sets] outcomes.
  const ExerciseResult({
    required this.exercise,
    required this.sets,
    this.warmupDone = false,
  });

  /// The exercise definition this result belongs to.
  final Exercise exercise;

  /// Results for each individual set.
  final List<SetResult> sets;

  /// Whether the warmup set was completed before the working sets.
  final bool warmupDone;

  /// True when every set was fully completed.
  bool get succeeded => sets.isNotEmpty && sets.every((s) => s.succeeded);

  /// Serializes this exercise result to a JSON map.
  Map<String, dynamic> toJson() => {
    'name': exercise.name,
    'targetSets': exercise.sets,
    'targetReps': exercise.reps,
    'targetWeight': exercise.weight,
    'warmupDone': warmupDone,
    'sets': sets.map((s) => s.toJson()).toList(),
    'succeeded': succeeded,
  };
}
