import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/models/exercise_result.dart';
import 'package:workout_app/models/set_result.dart';
import 'package:workout_app/models/workout_session.dart';

void main() {
  final start = DateTime(2024, 6, 1, 9, 0, 0);
  final end = DateTime(2024, 6, 1, 9, 45, 30);
  const exercise = Exercise(name: 'Press', sets: 3, reps: 5, weight: 15.0);

  final successResult = ExerciseResult(
    exercise: exercise,
    sets: List.generate(
      3,
      (_) => const SetResult(targetReps: 5, doneReps: 5, weight: 15),
    ),
  );
  final failResult = ExerciseResult(
    exercise: exercise,
    sets: List.generate(
      3,
      (_) => const SetResult(targetReps: 5, doneReps: 3, weight: 15),
    ),
  );

  group('WorkoutSession', () {
    test('duration computes correctly', () {
      final s = WorkoutSession(
        workoutType: 'A',
        startTime: start,
        endTime: end,
        exercises: [],
      );
      expect(s.duration, const Duration(minutes: 45, seconds: 30));
    });

    test('fullySucceeded true when all exercises succeeded', () {
      final s = WorkoutSession(
        workoutType: 'A',
        startTime: start,
        endTime: end,
        exercises: [successResult],
      );
      expect(s.fullySucceeded, isTrue);
    });

    test('fullySucceeded false when any exercise failed', () {
      final s = WorkoutSession(
        workoutType: 'B',
        startTime: start,
        endTime: end,
        exercises: [successResult, failResult],
      );
      expect(s.fullySucceeded, isFalse);
    });

    test('toJson contains expected keys', () {
      final s = WorkoutSession(
        workoutType: 'A',
        startTime: start,
        endTime: end,
        exercises: [successResult],
      );
      final json = s.toJson();
      expect(json['workout_type'], 'A');
      expect(json['date'], '2024-06-01');
      expect(json['duration_seconds'], 45 * 60 + 30);
      expect(json['succeeded'], isTrue);
      expect((json['exercises'] as List).length, 1);
    });

    test('toJsonString is valid pretty-printed JSON', () {
      final s = WorkoutSession(
        workoutType: 'B',
        startTime: start,
        endTime: end,
        exercises: [],
      );
      final str = s.toJsonString();
      expect(str, contains('\n'));
      final decoded = jsonDecode(str) as Map<String, dynamic>;
      expect(decoded['workout_type'], 'B');
    });
  });
}
