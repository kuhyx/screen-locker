import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/exercise.dart';

void main() {
  group('Exercise', () {
    const e = Exercise(name: 'Squat', sets: 5, reps: 5, weight: 20.0);

    test('constructor stores fields', () {
      expect(e.name, 'Squat');
      expect(e.sets, 5);
      expect(e.reps, 5);
      expect(e.weight, 20.0);
      expect(e.maxWeight, kDefaultMaxWeight);
    });

    test('custom maxWeight', () {
      const e2 = Exercise(
        name: 'Situp',
        sets: 3,
        reps: 30,
        weight: 10,
        maxWeight: 10,
      );
      expect(e2.maxWeight, 10);
    });

    test('warmupWeight rounds down to nearest 2.5', () {
      // 20 * 4/5 = 16 → floor to 15
      expect(e.warmupWeight, 15.0);
    });

    test('warmupWeight of 27.5 → 20.0', () {
      const e2 = Exercise(name: 'A', sets: 1, reps: 1, weight: 27.5);
      // 27.5 * 0.8 = 22.0, then floor(22.0 / 2.5) * 2.5 = 8 * 2.5 = 20.0
      expect(e2.warmupWeight, 20.0);
    });

    test('copyWith replaces specified fields', () {
      final copy = e.copyWith(weight: 25.0, reps: 6);
      expect(copy.weight, 25.0);
      expect(copy.reps, 6);
      expect(copy.name, e.name);
      expect(copy.sets, e.sets);
      expect(copy.maxWeight, e.maxWeight);
    });

    test('copyWith with no args returns identical values', () {
      final copy = e.copyWith();
      expect(copy.name, e.name);
      expect(copy.weight, e.weight);
    });

    test('toJson round-trips via fromJson', () {
      final json = e.toJson();
      final restored = Exercise.fromJson(json);
      expect(restored.name, e.name);
      expect(restored.sets, e.sets);
      expect(restored.reps, e.reps);
      expect(restored.weight, e.weight);
      expect(restored.maxWeight, e.maxWeight);
    });

    test('fromJson uses default maxWeight when absent', () {
      final json = {'name': 'Test', 'sets': 3, 'reps': 10, 'weight': 5.0};
      final ex = Exercise.fromJson(json);
      expect(ex.maxWeight, kDefaultMaxWeight);
    });

    test('kDefaultMaxWeight and kWeightIncrement have expected values', () {
      expect(kDefaultMaxWeight, 27.5);
      expect(kWeightIncrement, 2.5);
    });
  });
}
