import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/gps_filter.dart';
import 'package:workout_app/services/run_recorder.dart';
import 'package:workout_app/services/run_watchdog.dart';

import '../run_test_fixtures.dart';

final DateTime _start = DateTime.utc(2026, 11, 9, 12);

class _Rig {
  _Rig({this.autoEnd = const Duration(hours: 5)}) {
    dog = RunWatchdog(
      clock: () => now,
      onSuggest: suggestions.add,
      onAutoEnd: () => autoEnds++,
      autoEndAfter: autoEnd,
    );
  }

  final Duration autoEnd;
  late final RunWatchdog dog;
  DateTime now = _start;
  final suggestions = <RunSuggestion>[];
  int autoEnds = 0;
  double metres = 0;

  void advance(Duration d) {
    now = now.add(d);
    dog.check();
  }

  /// [minutes] minutes with a fresh, motionless fix every minute.
  void idle(int minutes) {
    for (var i = 0; i < minutes; i++) {
      now = now.add(const Duration(minutes: 1));
      fix();
      dog.check();
    }
  }

  /// An accepted fix at the current clock, [stepM] further on.
  void fix({double stepM = 0, int secondsIntoRun = 0}) {
    metres += stepM;
    dog.onFix(fixAt(secondsIntoRun, metres), FixVerdict.accepted, metres);
  }
}

void main() {
  group('stationary (under 50 m in 10 min)', () {
    test('fires after 10 idle minutes and then every 10, with no limit', () {
      final r = _Rig()..dog.begin(_start);
      r.idle(30);
      expect(r.suggestions, List.filled(3, RunSuggestion.stationary));
    });

    test('does not fire before 10 minutes', () {
      final r = _Rig()..dog.begin(_start);
      r.idle(9);
      expect(r.suggestions, isEmpty);
    });

    test('50 m of progress in the window stays quiet and re-arms', () {
      final r = _Rig()..dog.begin(_start);
      r.idle(4);
      r.fix(stepM: 50);
      r.idle(6);
      expect(r.suggestions, isEmpty);
      // The next window starts at 10:00 with 50 m banked: 49 m is too few.
      r.fix(stepM: 49);
      r.idle(10);
      expect(r.suggestions, [RunSuggestion.stationary]);
    });

    test('nothing fires while paused, and resume restarts the window', () {
      final r = _Rig()..dog.begin(_start);
      r.idle(8);
      r.dog.pause();
      r.advance(const Duration(minutes: 30));
      expect(r.suggestions, isEmpty);
      r.dog.resume();
      r.idle(9);
      expect(r.suggestions, isEmpty);
      r.idle(1);
      expect(r.suggestions, [RunSuggestion.stationary]);
    });
  });

  group('no GPS fix for 5 min', () {
    test('fires once per loss, not before 5 minutes', () {
      final r = _Rig()..dog.begin(_start);
      r.advance(const Duration(minutes: 4, seconds: 59));
      expect(r.suggestions, isEmpty);
      r.advance(const Duration(seconds: 1));
      expect(r.suggestions, [RunSuggestion.gpsLost]);
      r.advance(const Duration(minutes: 2));
      expect(r.suggestions, [RunSuggestion.gpsLost]);
    });

    test('a fix re-arms it', () {
      final r = _Rig()..dog.begin(_start);
      r.advance(const Duration(minutes: 5));
      r.fix();
      r.advance(const Duration(minutes: 5));
      expect(
        r.suggestions.where((s) => s == RunSuggestion.gpsLost),
        hasLength(2),
      );
    });

    test('fixes the filter rejects as too inaccurate do not count', () {
      final r = _Rig()..dog.begin(_start);
      r.advance(const Duration(minutes: 4));
      r.dog.onFix(fixAt(0, 0), FixVerdict.inaccurate, 0);
      r.dog.onFix(fixAt(2, 0), FixVerdict.mocked, 0);
      r.advance(const Duration(minutes: 1));
      expect(r.suggestions, contains(RunSuggestion.gpsLost));
    });

    test('nothing fires while paused', () {
      final r = _Rig()..dog.begin(_start);
      r.dog.pause();
      r.advance(const Duration(minutes: 20));
      expect(r.suggestions, isEmpty);
    });
  });

  group('vehicle speed (over 25 km/h for 60 s)', () {
    // 10 m/s is 36 km/h. Rejected jump fixes still count: a car never
    // produces an accepted fix, the filter drops it as too fast.
    void drive(_Rig r, {required int seconds, required double mps}) {
      for (var s = 0; s <= seconds; s += 2) {
        r.dog.onFix(fixAt(s, s * mps), FixVerdict.tooFast, r.metres);
      }
    }

    test('fires once after 60 s of it', () {
      final r = _Rig()..dog.begin(_start);
      drive(r, seconds: 120, mps: 10);
      expect(r.suggestions, [RunSuggestion.vehicleSpeed]);
    });

    test('59 s is not sustained', () {
      final r = _Rig()..dog.begin(_start);
      drive(r, seconds: 58, mps: 10);
      expect(r.suggestions, isEmpty);
    });

    test('slowing down resets it', () {
      final r = _Rig()..dog.begin(_start);
      drive(r, seconds: 50, mps: 10);
      r.dog.onFix(fixAt(52, 500), FixVerdict.accepted, 0); // standing
      for (var s = 54; s <= 100; s += 2) {
        r.dog.onFix(fixAt(s, 500 + (s - 52) * 10.0), FixVerdict.tooFast, 0);
      }
      expect(r.suggestions, isEmpty);
    });

    test('running speed never fires it', () {
      final r = _Rig()..dog.begin(_start);
      drive(r, seconds: 300, mps: 3);
      expect(r.suggestions, isEmpty);
    });

    test('a second ride after slowing fires again', () {
      final r = _Rig()..dog.begin(_start);
      drive(r, seconds: 70, mps: 10);
      r.dog.onFix(fixAt(72, 700), FixVerdict.accepted, 0);
      for (var s = 74; s <= 200; s += 2) {
        r.dog.onFix(fixAt(s, 700 + (s - 72) * 10.0), FixVerdict.tooFast, 0);
      }
      expect(r.suggestions, [
        RunSuggestion.vehicleSpeed,
        RunSuggestion.vehicleSpeed,
      ]);
    });

    test('same-second fixes and mocked fixes are ignored', () {
      final r = _Rig()..dog.begin(_start);
      r.dog.onFix(fixAt(0, 0), FixVerdict.accepted, 0);
      r.dog.onFix(fixAt(0, 500), FixVerdict.tooFast, 0);
      r.dog.onFix(fixAt(2, 900), FixVerdict.mocked, 0);
      expect(r.suggestions, isEmpty);
    });
  });

  group('auto end after 5 h of wall clock', () {
    test('fires once at 5 h, pauses and gaps included', () {
      final r = _Rig()..dog.begin(_start);
      r.dog.pause();
      r.advance(const Duration(hours: 4, minutes: 59));
      expect(r.autoEnds, 0);
      r.advance(const Duration(minutes: 1));
      expect(r.autoEnds, 1);
      r.advance(const Duration(hours: 1));
      expect(r.autoEnds, 1);
    });

    test('a shortened limit is honoured', () {
      final r = _Rig(autoEnd: const Duration(minutes: 3))..dog.begin(_start);
      r.advance(const Duration(minutes: 3));
      expect(r.autoEnds, 1);
    });

    test('restored past the limit ends at once, with no restore hint', () {
      final r = _Rig();
      r.now = _start.add(const Duration(hours: 6));
      r.dog.restored(_start, paused: false, distanceM: 0);
      expect(r.autoEnds, 1);
      expect(r.suggestions, isEmpty);
    });

    test('restored inside the limit suggests finishing', () {
      final r = _Rig();
      r.now = _start.add(const Duration(hours: 1));
      r.dog.restored(_start, paused: false, distanceM: 2000);
      expect(r.autoEnds, 0);
      expect(r.suggestions, [RunSuggestion.restored]);
    });

    test('restored while paused stays paused: only the restore hint', () {
      final r = _Rig();
      r.now = _start.add(const Duration(minutes: 30));
      r.dog.restored(_start, paused: true, distanceM: 0);
      r.advance(const Duration(hours: 1));
      expect(r.suggestions, [RunSuggestion.restored]);
    });

    test('stop() silences everything and is safe twice', () {
      final r = _Rig()..dog.begin(_start);
      r.dog.stop();
      r.dog.stop();
      r.advance(const Duration(hours: 6));
      expect(r.suggestions, isEmpty);
      expect(r.autoEnds, 0);
    });

    test('fix and pause calls before begin are harmless', () {
      final r = _Rig();
      r.dog.pause();
      r.dog.resume();
      r.fix();
      r.dog.check();
      expect(r.suggestions, isEmpty);
    });
  });

  testWidgets('the timer, not a fix, drives the checks', (tester) async {
    var now = _start;
    final suggestions = <RunSuggestion>[];
    final dog = RunWatchdog(
      clock: () => now,
      onSuggest: suggestions.add,
      onAutoEnd: () {},
    )..begin(_start);
    for (var i = 0; i < 61; i++) {
      now = now.add(const Duration(seconds: 5));
      await tester.pump(const Duration(seconds: 5));
    }
    expect(suggestions, contains(RunSuggestion.gpsLost));
    dog.stop();
  });
}
