/// A completed workout session — serialised to JSON for PC sync.
library;

import 'dart:convert';
import 'package:workout_app/models/exercise_result.dart';

/// Immutable record of a finished workout session with all its results.
class WorkoutSession {
  /// Creates a workout session record.
  const WorkoutSession({
    required this.workoutType,
    required this.startTime,
    required this.endTime,
    required this.exercises,
  });

  /// 'A' or 'B'.
  final String workoutType;

  /// Wall-clock time when the session started.
  final DateTime startTime;

  /// Wall-clock time when the session ended.
  final DateTime endTime;

  /// Ordered list of exercise results, one per exercise in the plan.
  final List<ExerciseResult> exercises;

  /// Total elapsed time of the session.
  Duration get duration => endTime.difference(startTime);

  /// True when every exercise succeeded.
  bool get fullySucceeded => exercises.every((e) => e.succeeded);

  /// Serializes this session to a JSON map.
  Map<String, dynamic> toJson() => {
    'workout_type': workoutType,
    'date': startTime.toIso8601String().substring(0, 10),
    'start_time': startTime.toIso8601String(),
    'end_time': endTime.toIso8601String(),
    'duration_seconds': duration.inSeconds,
    'succeeded': fullySucceeded,
    'exercises': exercises.map((e) => e.toJson()).toList(),
  };

  /// Serializes this session to a pretty-printed JSON string.
  String toJsonString() => const JsonEncoder.withIndent('  ').convert(toJson());
}
