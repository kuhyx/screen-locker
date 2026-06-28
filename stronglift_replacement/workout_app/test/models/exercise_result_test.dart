import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/models/exercise_result.dart';
import 'package:workout_app/models/set_result.dart';

void main() {
  const exercise = Exercise(name: 'Press', sets: 3, reps: 5, weight: 15.0);

  group('ExerciseResult.succeeded', () {
    test('true when all sets succeeded', () {
      const r = ExerciseResult(
        exercise: exercise,
        sets: [
          SetResult(targetReps: 5, doneReps: 5, weight: 15),
          SetResult(targetReps: 5, doneReps: 5, weight: 15),
        ],
      );
      expect(r.succeeded, isTrue);
    });

    test('false when empty sets', () {
      const r = ExerciseResult(exercise: exercise, sets: []);
      expect(r.succeeded, isFalse);
    });

    test('false when any set failed', () {
      const r = ExerciseResult(
        exercise: exercise,
        sets: [
          SetResult(targetReps: 5, doneReps: 5, weight: 15),
          SetResult(targetReps: 5, doneReps: 3, weight: 15),
        ],
      );
      expect(r.succeeded, isFalse);
    });
  });

  group('ExerciseResult.toJson', () {
    test('serializes all fields', () {
      const r = ExerciseResult(
        exercise: exercise,
        warmupDone: true,
        sets: [SetResult(targetReps: 5, doneReps: 5, weight: 15)],
      );
      final json = r.toJson();
      expect(json['name'], 'Press');
      expect(json['targetSets'], 3);
      expect(json['targetReps'], 5);
      expect(json['targetWeight'], 15.0);
      expect(json['warmupDone'], isTrue);
      expect((json['sets'] as List).length, 1);
      expect(json['succeeded'], isTrue);
    });

    test('warmupDone defaults to false', () {
      const r = ExerciseResult(exercise: exercise, sets: []);
      expect(r.toJson()['warmupDone'], isFalse);
    });
  });
}
