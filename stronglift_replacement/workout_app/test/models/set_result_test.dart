import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/set_result.dart';

void main() {
  group('SetResult', () {
    const full = SetResult(targetReps: 5, doneReps: 5, weight: 20.0);
    const partial = SetResult(targetReps: 5, doneReps: 3, weight: 20.0);

    test('succeeded is true when doneReps >= targetReps', () {
      expect(full.succeeded, isTrue);
    });

    test('succeeded is false when doneReps < targetReps', () {
      expect(partial.succeeded, isFalse);
    });

    test('copyWith replaces doneReps', () {
      final copy = full.copyWith(doneReps: 2);
      expect(copy.doneReps, 2);
      expect(copy.targetReps, full.targetReps);
      expect(copy.weight, full.weight);
    });

    test('copyWith with null keeps original doneReps', () {
      final copy = full.copyWith();
      expect(copy.doneReps, full.doneReps);
    });

    test('toJson round-trips via fromJson', () {
      final json = full.toJson();
      expect(json['succeeded'], isTrue);
      final restored = SetResult.fromJson(json);
      expect(restored.targetReps, full.targetReps);
      expect(restored.doneReps, full.doneReps);
      expect(restored.weight, full.weight);
    });

    test('toJson includes succeeded field', () {
      final json = partial.toJson();
      expect(json['succeeded'], isFalse);
    });

    test('fromJson with num weight converts to double', () {
      final json = {'targetReps': 5, 'doneReps': 5, 'weight': 20};
      final s = SetResult.fromJson(json);
      expect(s.weight, 20.0);
    });
  });
}
