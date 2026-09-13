import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/break_clock.dart';

void main() {
  final start = DateTime(2026, 9, 12, 14);

  group('BreakClock', () {
    test('reports the full duration for its whole first second', () {
      final clock = BreakClock.startingAt(start, 180);
      // Rounded up, matching what the old decrementing counter displayed.
      expect(clock.remainingSecsAt(start), 180);
      expect(
        clock.remainingSecsAt(start.add(const Duration(milliseconds: 500))),
        180,
      );
      expect(clock.remainingSecsAt(start.add(const Duration(seconds: 1))), 179);
    });

    test('floors at zero rather than going negative', () {
      final clock = BreakClock.startingAt(start, 60);
      expect(clock.remainingSecsAt(start.add(const Duration(seconds: 60))), 0);
      expect(clock.remainingSecsAt(start.add(const Duration(hours: 3))), 0);
    });

    test('expires exactly at the deadline, not a tick later', () {
      final clock = BreakClock.startingAt(start, 60);
      final end = start.add(const Duration(seconds: 60));
      expect(clock.expiredAt(end.subtract(const Duration(microseconds: 1))),
          isFalse);
      expect(clock.expiredAt(end), isTrue);
    });

    test('reports how late it is, and zero while still running', () {
      final clock = BreakClock.startingAt(start, 60);
      expect(clock.secondsOverdueAt(start.add(const Duration(seconds: 30))), 0);
      expect(clock.secondsOverdueAt(start.add(const Duration(seconds: 105))), 45);
    });

    test('withDuration re-cuts from the original start, not from now', () {
      // This is the 3-min -> 5-min switch. A restart would hand the user two
      // extra minutes of rest they never earned.
      final clock = BreakClock.startingAt(start, 180);
      final longer = clock.withDuration(300);
      expect(longer.startTime, start);
      expect(longer.endTime, start.add(const Duration(seconds: 300)));
      expect(
        longer.remainingSecsAt(start.add(const Duration(seconds: 21))),
        279,
      );
    });

    test('startTime is derived from the deadline', () {
      final clock = BreakClock(
        endTime: start.add(const Duration(seconds: 180)),
        durationSecs: 180,
      );
      expect(clock.startTime, start);
    });

    test('value equality and hashCode track both fields', () {
      final a = BreakClock.startingAt(start, 180);
      final b = BreakClock.startingAt(start, 180);
      final c = BreakClock.startingAt(start, 300);
      expect(a, b);
      expect(a.hashCode, b.hashCode);
      expect(a, isNot(c));
      expect(a, isNot(Object()));
      expect(a.toString(), contains('180s'));
    });
  });
}
