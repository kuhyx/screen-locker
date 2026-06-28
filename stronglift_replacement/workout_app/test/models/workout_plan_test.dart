import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/workout_plan.dart';

void main() {
  group('Workout plans', () {
    test('workoutA has 4 exercises', () {
      expect(workoutA.length, 4);
    });

    test('workoutB has 4 exercises', () {
      expect(workoutB.length, 4);
    });

    test('kSitupMaxWeight is 10', () {
      expect(kSitupMaxWeight, 10);
    });

    test('workoutA exercises have positive sets/reps/weight', () {
      for (final ex in workoutA) {
        expect(ex.sets, greaterThan(0));
        expect(ex.reps, greaterThan(0));
        expect(ex.weight, greaterThan(0));
      }
    });

    test('workoutB Situp uses kSitupMaxWeight', () {
      final situp = workoutB.where((e) => e.name == 'Situp').first;
      expect(situp.maxWeight, kSitupMaxWeight);
    });
  });
}
