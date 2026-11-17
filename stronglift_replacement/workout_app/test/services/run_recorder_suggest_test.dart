import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/gps_filter.dart';
import 'package:workout_app/services/position_source.dart';
import 'package:workout_app/services/run_checkpoint.dart';
import 'package:workout_app/services/run_recorder.dart';
import '../run_test_fixtures.dart';
import '../run_recorder_persist_rig.dart';

void main() {
  group('suggestions and auto end, off the timer and the clock', () {
    testWidgets('no fix for 5 min suggests finishing, never ends', (
      tester,
    ) async {
      final h = PersistHost();
      await h.recorder.start();
      await h.feed(straightRun(3), tester: tester);
      for (var i = 0; i < 61; i++) {
        h.now = h.now.add(const Duration(seconds: 5));
        await tester.pump(const Duration(seconds: 5));
      }
      expect(h.suggestions, [RunSuggestion.gpsLost]);
      expect(h.recorder.phase, RunPhase.recording);
      await h.finishAfter(tester);
      h.recorder.dispose();
    });

    testWidgets('5 h wall clock ends the run once, pauses included', (
      tester,
    ) async {
      final h = PersistHost(autoEnd: const Duration(minutes: 2));
      await h.recorder.start();
      await h.feed(straightRun(3), tester: tester);
      h.recorder.pause();
      for (var i = 0; i < 30; i++) {
        h.now = h.now.add(const Duration(seconds: 5));
        await tester.pump(const Duration(seconds: 5));
      }
      expect(h.autoEnds, 1);
      expect(h.suggestions, isEmpty); // paused: only the auto end
      expect(await h.finishAfter(tester), isNotNull);
      h.recorder.dispose();
    });

    testWidgets('finish() stops the timer: nothing fires afterwards', (
      tester,
    ) async {
      final h = PersistHost(autoEnd: const Duration(minutes: 1));
      await h.recorder.start();
      await h.feed(straightRun(3), tester: tester);
      await h.finishAfter(tester);
      h.now = h.now.add(const Duration(hours: 1));
      await tester.pump(const Duration(minutes: 10));
      expect(h.autoEnds, 0);
      expect(h.suggestions, isEmpty);
      h.recorder.dispose();
    });

    test('a car (jump-rejected fixes) suggests finishing', () async {
      final h = PersistHost();
      await h.recorder.start();
      await h.feed(straightRun(2));
      await h.feed([for (var s = 4; s <= 100; s += 2) fixAt(s, s * 10.0)]);
      expect(h.suggestions, [RunSuggestion.vehicleSpeed]);
      h.recorder.dispose();
    });

    testWidgets('dispose cancels the watchdog timer', (tester) async {
      final h = PersistHost(autoEnd: const Duration(seconds: 1));
      await h.recorder.start();
      h.now = h.now.add(const Duration(hours: 1));
      h.recorder.dispose();
      await tester.pump(const Duration(seconds: 30));
      expect(h.autoEnds, 0);
    });
  });
}
