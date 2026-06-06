/// All set results for one exercise in a workout session.
library;

import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/models/set_result.dart';

class ExerciseResult {
  const ExerciseResult({
    required this.exercise,
    required this.sets,
    this.warmupDone = false,
  });

  final Exercise exercise;
  final List<SetResult> sets;
  final bool warmupDone;

  /// True when every set was fully completed.
  bool get succeeded => sets.isNotEmpty && sets.every((s) => s.succeeded);

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
