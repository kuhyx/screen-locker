import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/gap_deload.dart';
import 'package:workout_app/models/progression.dart';

import '../services/_deload_test_fixtures.dart';

DateTime _d(int day) => DateTime(2026, 11, day, 18);

void main() {
  group('gapCalendarDays', () {
    test('counts calendar days, not 24 h blocks', () {
      expect(gapCalendarDays(DateTime(2026, 11, 1, 23), DateTime(2026, 11, 8, 1)), 7);
      expect(gapCalendarDays(_d(8), _d(8)), 0);
    });
  });

  group('gapDeloadSteps', () {
    test('tiers: <7 none, 7-13 one, 14-20 two, +1 per week', () {
      expect(gapDeloadSteps(0), 0);
      expect(gapDeloadSteps(6), 0);
      expect(gapDeloadSteps(7), 1);
      expect(gapDeloadSteps(13), 1);
      expect(gapDeloadSteps(14), 2);
      expect(gapDeloadSteps(20), 2);
      expect(gapDeloadSteps(21), 3);
      expect(gapDeloadSteps(60), 8);
    });
  });

  group('gapDeloadTarget', () {
    test('weight mode: one step per tier', () {
      final t = gapDeloadTarget(deloadState(weight: 100), 2);
      expect(t.weight, 95);
      expect(t.reps, 5);
    });

    test('weight mode: stops at a hard 40% loss', () {
      // 10 kg: 7.5 is 25% off, 5 would be 50% -> stop at 7.5.
      expect(gapDeloadTarget(deloadState(weight: 10), 8).weight, 7.5);
      // 100 kg with 20 steps would be 50 kg; the floor is 60.
      expect(gapDeloadTarget(deloadState(weight: 100), 20).weight, 60);
    });

    test('one step that alone exceeds the cap means no cut', () {
      final t = gapDeloadTarget(deloadState(weight: 5), 1);
      expect(t.weight, 5);
    });

    test('reps mode: same steps, same 40% cap on reps', () {
      final s = deloadState(weight: 0, reps: 10, mode: ProgressionMode.reps);
      expect(gapDeloadTarget(s, 2).reps, 8);
      expect(gapDeloadTarget(s, 10).reps, 6);
    });

    test('double progression: reps first, weight capped at 40%', () {
      final s = deloadState(
        weight: 20,
        reps: 8,
        mode: ProgressionMode.doubleProgression,
      );
      final two = gapDeloadTarget(s, 2);
      expect((two.weight, two.reps), (20.0, 6));
      final three = gapDeloadTarget(s, 3);
      expect((three.weight, three.reps), (17.5, 12));
      expect(gapDeloadTarget(s, 99).weight, greaterThanOrEqualTo(12));
    });

    test('zero steps is the saved target', () {
      final t = gapDeloadTarget(deloadState(weight: 50), 0);
      expect((t.weight, t.reps), (50.0, 5));
    });
  });

  group('missedGapSteps', () {
    SessionMark m(int day, double w, {int reps = 5}) =>
        SessionMark(endedAt: _d(day), weight: w, reps: reps);

    test('a gap followed by an unchanged target is owed', () {
      // 7-day gap (1 step), trained again at the same weight.
      expect(missedGapSteps([m(1, 50), m(8, 50)]), 1);
    });

    test('debts add up while the target never moved', () {
      expect(missedGapSteps([m(1, 50), m(8, 50), m(10, 50)]), 1);
      expect(missedGapSteps([m(1, 50), m(8, 50), m(22, 50)]), 3);
    });

    test('any target change after the gap clears the debt', () {
      expect(missedGapSteps([m(1, 50), m(8, 50), m(10, 52.5)]), 0);
      expect(missedGapSteps([m(1, 50), m(8, 47.5)]), 0);
    });

    test('no history, one session or short gaps owe nothing', () {
      expect(missedGapSteps([]), 0);
      expect(missedGapSteps([m(1, 50)]), 0);
      expect(missedGapSteps([m(1, 50), m(4, 50)]), 0);
    });
  });
}
