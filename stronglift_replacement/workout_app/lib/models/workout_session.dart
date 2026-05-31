/// A completed workout session — serialised to JSON for PC sync.
library;

import 'dart:convert';
import 'package:workout_app/models/exercise_result.dart';

class WorkoutSession {
  const WorkoutSession({
    required this.workoutType,
    required this.startTime,
    required this.endTime,
    required this.exercises,
  });

  /// 'A' or 'B'.
  final String workoutType;
  final DateTime startTime;
  final DateTime endTime;
  final List<ExerciseResult> exercises;

  Duration get duration => endTime.difference(startTime);

  /// True when every exercise succeeded.
  bool get fullySucceeded => exercises.every((e) => e.succeeded);

  Map<String, dynamic> toJson() => {
        'workout_type': workoutType,
        'date': startTime.toIso8601String().substring(0, 10),
        'start_time': startTime.toIso8601String(),
        'end_time': endTime.toIso8601String(),
        'duration_seconds': duration.inSeconds,
        'succeeded': fullySucceeded,
        'exercises': exercises.map((e) => e.toJson()).toList(),
      };

  String toJsonString() => const JsonEncoder.withIndent('  ').convert(toJson());
}
