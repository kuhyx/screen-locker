/// Shared rig of the run watchdog tests.
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/gps_filter.dart';
import 'package:workout_app/services/run_recorder.dart';
import 'package:workout_app/services/run_watchdog.dart';
import 'run_test_fixtures.dart';

final DateTime watchdogStart = DateTime.utc(2026, 11, 9, 12);

class WatchdogRig {
  WatchdogRig({this.autoEnd = const Duration(hours: 5)}) {
    dog = RunWatchdog(
      clock: () => now,
      onSuggest: suggestions.add,
      onAutoEnd: () => autoEnds++,
      autoEndAfter: autoEnd,
    );
  }

  final Duration autoEnd;
  late final RunWatchdog dog;
  DateTime now = watchdogStart;
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
