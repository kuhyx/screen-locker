// ExerciseState's injury-pause and rest-length fields and their formatting
// helpers. Split from progression_test.dart for the 250-line cap.
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/models/exercise_state.dart';

// ExerciseState.initial starts in weight mode, the same as the progression
// tests' default.
final _base = ExerciseState.initial(
  const Exercise(name: 'X', sets: 3, reps: 8, weight: 20),
);

void main() {
  group('injury pause', () {
    final now = DateTime(2026, 9, 27, 17, 30);

    test('pauseEnd is local midnight n days on', () {
      expect(pauseEnd(now, 14), DateTime(2026, 10, 11));
    });

    test('isPausedAt is true until that midnight, false from it', () {
      final s = _base.copyWith(pausedUntil: pauseEnd(now, 14));
      expect(s.isPausedAt(now), isTrue);
      expect(s.isPausedAt(DateTime(2026, 10, 10, 23, 59)), isTrue);
      expect(s.isPausedAt(DateTime(2026, 10, 11)), isFalse);
      expect(_base.isPausedAt(now), isFalse);
    });

    test('copyWith keeps a pause, and resume clears it', () {
      final paused = _base.copyWith(pausedUntil: DateTime(2026, 10, 11));
      expect(paused.copyWith(reps: 3).pausedUntil, DateTime(2026, 10, 11));
      expect(paused.copyWith(resume: true).pausedUntil, isNull);
    });

    test('dates round-trip through storage format', () {
      final d = DateTime(2026, 1, 5);
      expect(formatPauseDate(d), '2026-01-05');
      expect(parsePauseDate(formatPauseDate(d)), d);
    });

    test('null, garbage and non-strings read as not paused', () {
      expect(parsePauseDate(null), isNull);
      expect(parsePauseDate('soon'), isNull);
      expect(parsePauseDate(42), isNull);
    });

    test('rests default to the old fixed lengths and survive copyWith', () {
      final s = _base;
      expect(
        (s.restSuccessSecs, s.restFailSecs, s.restWarmupSecs),
        (180, 300, 180),
      );
      final edited = s.copyWith(restFailSecs: 240);
      expect(edited.restFailSecs, 240);
      expect(edited.copyWith(reps: 3).restFailSecs, 240);
    });

    test('formatRest', () {
      expect(formatRest(30), '0:30');
      expect(formatRest(195), '3:15');
      expect(formatRest(600), '10:00');
    });

    test('formatShortDate', () {
      expect(formatShortDate(DateTime(2026, 10, 11)), '11 Oct');
      expect(formatShortDate(DateTime(2026, 1, 1)), '1 Jan');
      expect(formatShortDate(DateTime(2026, 12, 31)), '31 Dec');
    });
  });
}
