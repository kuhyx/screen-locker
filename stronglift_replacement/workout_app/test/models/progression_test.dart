import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/models/exercise_state.dart';
import 'package:workout_app/models/progression.dart';

ExerciseState _s({
  required ProgressionMode mode,
  double weight = 20,
  int reps = 8,
  double maxWeight = 27.5,
  int repsHigh = 12,
  int repsLow = 6,
}) => ExerciseState(
  name: 'X',
  weight: weight,
  reps: reps,
  successStreak: 0,
  failStreak: 0,
  maxWeight: maxWeight,
  successThreshold: 3,
  failThreshold: 2,
  mode: mode,
  repsHigh: repsHigh,
  repsLow: repsLow,
  hasWarmup: true,
  pausedUntil: null,
);

void _expectTarget(ProgressionTarget t, double weight, int reps) {
  expect((t.weight, t.reps), (weight, reps), reason: '$t');
}

void main() {
  group('ProgressionMode.parse', () {
    test('reads every storage key back to its mode', () {
      for (final m in ProgressionMode.values) {
        expect(ProgressionMode.parse(m.storageKey), m);
      }
    });

    test('null (a row from before modes existed) is weight', () {
      expect(ProgressionMode.parse(null), ProgressionMode.weight);
    });

    test('an unknown value falls back to weight', () {
      expect(ProgressionMode.parse('sideways'), ProgressionMode.weight);
    });
  });

  group('weight mode (unchanged behaviour)', () {
    test('success below the cap adds 2.5 kg', () {
      _expectTarget(targetAfterSuccess(_s(mode: ProgressionMode.weight)), 22.5, 8);
    });

    test('success above the cap clamps to it', () {
      final s = _s(mode: ProgressionMode.weight, weight: 26);
      _expectTarget(targetAfterSuccess(s), 27.5, 8);
    });

    test('success at the cap adds a rep instead', () {
      final s = _s(mode: ProgressionMode.weight, weight: 27.5);
      _expectTarget(targetAfterSuccess(s), 27.5, 9);
    });

    test('failure drops 2.5 kg, never below zero', () {
      _expectTarget(targetAfterFailure(_s(mode: ProgressionMode.weight)), 17.5, 8);
      final light = _s(mode: ProgressionMode.weight, weight: 1);
      _expectTarget(targetAfterFailure(light), 0, 8);
    });
  });

  group('reps mode', () {
    test('success adds a rep and never touches the weight', () {
      _expectTarget(targetAfterSuccess(_s(mode: ProgressionMode.reps)), 20, 9);
    });

    test('failure removes a rep, floored at 1', () {
      _expectTarget(targetAfterFailure(_s(mode: ProgressionMode.reps)), 20, 7);
      final one = _s(mode: ProgressionMode.reps, reps: 1);
      _expectTarget(targetAfterFailure(one), 20, 1);
    });
  });

  group('double progression', () {
    const mode = ProgressionMode.doubleProgression;

    test('below n: +1 rep', () {
      _expectTarget(targetAfterSuccess(_s(mode: mode, reps: 11)), 20, 12);
    });

    test('at n: +2.5 kg and back to m', () {
      _expectTarget(targetAfterSuccess(_s(mode: mode, reps: 12)), 22.5, 6);
    });

    test('above n (switched in at 30 reps) still promotes', () {
      _expectTarget(targetAfterSuccess(_s(mode: mode, reps: 30)), 22.5, 6);
    });

    test('at n on the weight cap keeps adding reps', () {
      final s = _s(mode: mode, reps: 12, weight: 27.5);
      _expectTarget(targetAfterSuccess(s), 27.5, 13);
    });

    test('failure above m removes a rep', () {
      _expectTarget(targetAfterFailure(_s(mode: mode, reps: 9)), 20, 8);
    });

    test('failure at m is the exact inverse of a step up', () {
      final s = _s(mode: mode, reps: 6);
      final down = targetAfterFailure(s);
      _expectTarget(down, 17.5, 12);
      final back = targetAfterSuccess(
        s.copyWith(weight: down.weight, reps: down.reps),
      );
      _expectTarget(back, 20, 6);
    });

    test('failure at m with no weight left stays put', () {
      _expectTarget(targetAfterFailure(_s(mode: mode, reps: 6, weight: 0)), 0, 6);
    });
  });

  group('describeTargetChange', () {
    final from = _s(mode: ProgressionMode.weight, weight: 20, reps: 8);

    test('weight and reps', () {
      expect(
        describeTargetChange(from, const ProgressionTarget(22.5, 6)),
        '22.5 kg × 6',
      );
    });

    test('weight only drops a trailing .0', () {
      expect(describeTargetChange(from, const ProgressionTarget(25, 8)), '25 kg');
    });

    test('reps only', () {
      expect(describeTargetChange(from, const ProgressionTarget(20, 9)), '9 reps');
    });

    test('no change', () {
      expect(describeTargetChange(from, const ProgressionTarget(20, 8)), 'same');
    });

    test('toString names both fields', () {
      expect(const ProgressionTarget(20, 8).toString(), contains('20'));
    });
  });

  group('ExerciseState', () {
    test('initial copies the plan and the plan warmup', () {
      const ex = Exercise(
        name: 'Situp',
        sets: 3,
        reps: 30,
        weight: 10,
        maxWeight: 10,
        hasWarmup: false,
      );
      final s = ExerciseState.initial(ex);
      expect(s.weight, 10);
      expect(s.reps, 30);
      expect(s.maxWeight, 10);
      expect(s.hasWarmup, isFalse);
      expect(s.mode, ProgressionMode.weight);
      expect((s.repsHigh, s.repsLow), (kDefaultRepsHigh, kDefaultRepsLow));
      expect((s.successThreshold, s.failThreshold), (3, 2));
    });

    test('copyWith replaces each field and keeps the rest', () {
      final s = _s(mode: ProgressionMode.weight);
      final c = s.copyWith(
        weight: 1,
        reps: 2,
        successStreak: 3,
        failStreak: 4,
        successThreshold: 5,
        failThreshold: 1,
        mode: ProgressionMode.reps,
        repsHigh: 20,
        repsLow: 10,
        hasWarmup: false,
      );
      expect(c.name, 'X');
      expect(c.maxWeight, 27.5);
      expect((c.weight, c.reps, c.successStreak, c.failStreak), (1, 2, 3, 4));
      expect((c.successThreshold, c.failThreshold), (5, 1));
      expect((c.mode, c.repsHigh, c.repsLow, c.hasWarmup), (
        ProgressionMode.reps,
        20,
        10,
        false,
      ));
      final same = s.copyWith();
      expect((same.weight, same.reps, same.mode, same.hasWarmup), (
        20,
        8,
        ProgressionMode.weight,
        true,
      ));
    });
  });

  group('injury pause', () {
    final now = DateTime(2026, 9, 27, 17, 30);

    test('pauseEnd is local midnight n days on', () {
      expect(pauseEnd(now, 14), DateTime(2026, 10, 11));
    });

    test('isPausedAt is true until that midnight, false from it', () {
      final s = _s(mode: ProgressionMode.weight).copyWith(
        pausedUntil: pauseEnd(now, 14),
      );
      expect(s.isPausedAt(now), isTrue);
      expect(s.isPausedAt(DateTime(2026, 10, 10, 23, 59)), isTrue);
      expect(s.isPausedAt(DateTime(2026, 10, 11)), isFalse);
      expect(_s(mode: ProgressionMode.weight).isPausedAt(now), isFalse);
    });

    test('copyWith keeps a pause, and resume clears it', () {
      final paused = _s(mode: ProgressionMode.weight).copyWith(
        pausedUntil: DateTime(2026, 10, 11),
      );
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

    test('formatShortDate', () {
      expect(formatShortDate(DateTime(2026, 10, 11)), '11 Oct');
      expect(formatShortDate(DateTime(2026, 1, 1)), '1 Jan');
      expect(formatShortDate(DateTime(2026, 12, 31)), '31 Dec');
    });
  });
}
