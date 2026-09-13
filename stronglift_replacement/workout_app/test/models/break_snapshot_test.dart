import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/break_snapshot.dart';

const _full = BreakSnapshot(
  workoutType: 'B',
  breakEndMs: 1789432100123,
  breakDurationSecs: 180,
  breakLabel: 'Rest (3 min — well done!)',
  breakForExIdx: 0,
  breakForSetIdx: 1,
  nextExIdx: 0,
  nextSetIdx: 2,
  nextExName: 'Squat',
  nextSetNumber: 3,
  nextTotalSets: 5,
  nextReps: 5,
  nextWeight: 42.5,
  lastExIdx: 0,
  lastSetIdx: 1,
  setsRemaining: 7,
  finished: true,
);

void main() {
  test('survives the trip across the isolate boundary', () {
    final decoded = BreakSnapshot.tryFromMap(_full.toMap())!;
    expect(decoded.workoutType, 'B');
    expect(decoded.breakEndMs, 1789432100123);
    expect(decoded.breakLabel, contains('well done'));
    expect(decoded.nextWeight, 42.5);
    expect(decoded.setsRemaining, 7);
    expect(decoded.finished, isTrue);
  });

  test('accepts an int weight — the channel may narrow a whole number', () {
    final map = _full.toMap()..['nextWeight'] = 40;
    expect(BreakSnapshot.tryFromMap(map)!.nextWeight, 40.0);
  });

  // Returning null rather than throwing keeps a bad payload from taking the
  // foreground service isolate down mid-workout.
  test('returns null rather than throwing on a malformed payload', () {
    expect(BreakSnapshot.tryFromMap(const {}), isNull);
    for (final key in _full.toMap().keys) {
      if (key == 'finished') continue; // absent means false, by design
      final map = _full.toMap()..remove(key);
      expect(BreakSnapshot.tryFromMap(map), isNull, reason: 'missing $key');
    }
    expect(
      BreakSnapshot.tryFromMap(_full.toMap()..['workoutType'] = 1),
      isNull,
    );
    expect(
      BreakSnapshot.tryFromMap(_full.toMap()..['nextExName'] = 1),
      isNull,
    );
    expect(BreakSnapshot.tryFromMap(_full.toMap()..['breakLabel'] = 1), isNull);
    expect(BreakSnapshot.tryFromMap(_full.toMap()..['nextWeight'] = 'x'), isNull);
    expect(BreakSnapshot.tryFromMap(_full.toMap()..['breakEndMs'] = 'x'), isNull);
  });

  test('a missing finished flag reads as not finished', () {
    final map = _full.toMap()..remove('finished');
    expect(BreakSnapshot.tryFromMap(map)!.finished, isFalse);
  });

  test('hasBreak and hasNextSet describe what the buttons can do', () {
    expect(_full.hasBreak, isTrue);
    expect(_full.copyWith(breakEndMs: 0).hasBreak, isFalse);
    expect(_full.hasNextSet, isTrue);
  });

  test('copyWith replaces only what it is given', () {
    final recut = _full.copyWith(
      breakEndMs: 1,
      breakDurationSecs: 300,
      breakLabel: 'Rest (5 min — keep going!)',
      setsRemaining: 6,
      finished: false,
    );
    expect(recut.breakEndMs, 1);
    expect(recut.breakDurationSecs, 300);
    expect(recut.breakLabel, contains('keep going'));
    expect(recut.setsRemaining, 6);
    expect(recut.finished, isFalse);
    expect(recut.nextExName, 'Squat', reason: 'untouched fields carry over');

    final same = _full.copyWith();
    expect(same.breakEndMs, _full.breakEndMs);
    expect(same.breakLabel, _full.breakLabel);
    expect(same.breakDurationSecs, _full.breakDurationSecs);
    expect(same.setsRemaining, _full.setsRemaining);
    expect(same.finished, _full.finished);
  });

  test('no next set is representable', () {
    const done = BreakSnapshot(
      workoutType: 'A',
      breakEndMs: 0,
      breakDurationSecs: 0,
      breakLabel: '',
      breakForExIdx: -1,
      breakForSetIdx: -1,
      nextExIdx: -1,
      nextSetIdx: -1,
      nextExName: '',
      nextSetNumber: 0,
      nextTotalSets: 0,
      nextReps: 0,
      nextWeight: 0,
      lastExIdx: -1,
      lastSetIdx: -1,
      setsRemaining: 0,
    );
    expect(done.hasNextSet, isFalse);
    expect(done.hasBreak, isFalse);
  });
}
