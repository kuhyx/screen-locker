import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/gps_filter.dart';
import 'package:workout_app/services/position_source.dart';
import 'package:workout_app/services/run_checkpoint.dart';
import 'package:workout_app/services/run_recorder.dart';

import '../run_test_fixtures.dart';

final DateTime _t0 = DateTime.utc(2026, 11, 9, 12);

/// A recorder plus everything it reports, on a clock the test moves.
class _Host {
  _Host({
    ManualPositionSource? source,
    DateTime? at,
    Duration autoEnd = const Duration(hours: 5),
  }) : source = source ?? ManualPositionSource(),
       now = at ?? _t0 {
    recorder = RunRecorder(
      sourceFor: () => this.source,
      onKilometre: km.add,
      onSuggestFinish: suggestions.add,
      onAutoEnd: () => autoEnds++,
      onCheckpoint: checkpoints.add,
      clock: () => now,
      autoEndAfter: autoEnd,
    );
  }

  final ManualPositionSource source;
  late final RunRecorder recorder;
  DateTime now;
  final km = <int>[];
  final suggestions = <RunSuggestion>[];
  final checkpoints = <RunCheckpoint>[];
  int autoEnds = 0;

  /// Finishes inside `testWidgets`, where awaiting a stream cancel hangs the
  /// fake-async zone: it runs in the real one instead.
  Future<RunTrack?> finishIn(WidgetTester tester) async =>
      await tester.runAsync<RunTrack?>(recorder.finish);

  /// Delivers [fixes]; inside `testWidgets` pass the tester, whose pump
  /// drains the queue where a real-time `pumpEventQueue` would hang.
  Future<void> feed(Iterable<GpsFix> fixes, {WidgetTester? tester}) async {
    for (final fix in fixes) {
      source.controller.add(fix);
    }
    await (tester?.pump() ?? pumpEventQueue());
  }
}

RunCheckpoint _viaJson(RunCheckpoint c) => RunCheckpoint.fromJson(
  jsonDecode(jsonEncode(c.toJson())) as Map<String, Object?>,
);

Future<RunCheckpoint> _checkpointAfter(int fixes, {bool pause = false}) async {
  final h = _Host();
  await h.recorder.start();
  await h.feed(straightRun(fixes));
  if (pause) h.recorder.pause();
  final c = h.recorder.checkpoint()!;
  await h.recorder.finish();
  h.recorder.dispose();
  return _viaJson(c);
}

void main() {
  group('checkpoint()', () {
    test('is null when idle and after finish', () async {
      final h = _Host();
      expect(h.recorder.checkpoint(), isNull);
      await h.recorder.start();
      expect(h.recorder.checkpoint(), isNotNull);
      await h.recorder.finish();
      expect(h.recorder.checkpoint(), isNull);
      h.recorder.dispose();
    });

    test('holds the whole recording state', () async {
      final h = _Host(at: _t0.add(const Duration(minutes: 3)));
      await h.recorder.start();
      h.recorder.setPaceTarget(330);
      await h.feed(straightRun(10));
      final c = h.recorder.checkpoint()!;
      expect(c.startedAt, _t0.add(const Duration(minutes: 3)));
      expect(c.savedAt, h.now);
      expect(c.phase, RunPhase.recording);
      expect(c.points, hasLength(10));
      expect(c.distanceM, closeTo(54, 0.5));
      expect(c.movingSeconds, 18);
      expect(c.paceTargetSeconds, 330);
      expect(c.segmentBreak, isFalse);
      expect(c.id, '2026-11-09T12:00:00Z');
      h.recorder.dispose();
    });

    test('a pause is recorded with its segment break', () async {
      final c = await _checkpointAfter(5, pause: true);
      expect(c.phase, RunPhase.paused);
      expect(c.segmentBreak, isTrue);
    });
  });

  group('onCheckpoint', () {
    test('fires on start, every accepted fix, pause and resume', () async {
      final h = _Host();
      await h.recorder.start();
      expect(h.checkpoints, hasLength(1));
      await h.feed(straightRun(3));
      expect(h.checkpoints, hasLength(4));
      await h.feed([fixAt(6, 18, accuracy: 99)]); // dropped: no checkpoint
      expect(h.checkpoints, hasLength(4));
      h.recorder.pause();
      h.recorder.resume();
      expect(h.checkpoints.map((c) => c.phase), [
        RunPhase.recording,
        RunPhase.recording,
        RunPhase.recording,
        RunPhase.recording,
        RunPhase.paused,
        RunPhase.recording,
      ]);
      h.recorder.dispose();
    });
  });

  group('restore()', () {
    test('re-enters recording with the state and tells the host', () async {
      final saved = await _checkpointAfter(10);
      final h = _Host(at: _t0.add(const Duration(minutes: 10)));
      expect(await h.recorder.restore(saved), isTrue);
      expect(h.recorder.phase, RunPhase.recording);
      expect(h.recorder.seconds, 18);
      expect(h.recorder.distanceM, closeTo(54, 0.5));
      expect(h.recorder.livePoints.value, hasLength(10));
      expect(h.source.subscriptions, 1);
      expect(h.suggestions, [RunSuggestion.restored]);
      expect(h.autoEnds, 0);
      h.recorder.dispose();
    });

    test('the dead time is bridged and credited at a running pace', () async {
      final saved = await _checkpointAfter(10); // last fix: 18 s, 54 m
      final h = _Host(at: _t0.add(const Duration(minutes: 10)));
      await h.recorder.restore(saved);
      await h.feed([fixAt(318, 954)]); // 300 s later, 900 m on: 3 m/s
      expect(h.recorder.distanceM, closeTo(954, 1));
      expect(h.recorder.seconds, 18 + 300);
      expect(h.recorder.livePoints.value.last.link, RunLink.bridge);
      h.recorder.dispose();
    });

    test('a vehicle-speed gap is drawn but earns nothing', () async {
      final saved = await _checkpointAfter(10);
      final h = _Host(at: _t0.add(const Duration(minutes: 10)));
      await h.recorder.restore(saved);
      await h.feed([fixAt(78, 54 + 600)]); // 60 s, 600 m: 36 km/h
      expect(h.recorder.distanceM, closeTo(54, 0.5));
      expect(h.recorder.seconds, 18);
      expect(h.recorder.livePoints.value, hasLength(11));
      h.recorder.dispose();
    });

    test('kilometres already announced are not announced again', () async {
      final h0 = _Host();
      await h0.recorder.start();
      await h0.feed(straightRun(340)); // 2 km
      final saved = _viaJson(h0.recorder.checkpoint()!);
      expect(h0.km, [1, 2]);
      await h0.recorder.finish();
      h0.recorder.dispose();

      final h = _Host(at: _t0.add(const Duration(hours: 1)));
      await h.recorder.restore(saved);
      await h.feed([fixAt(681, 2043)]); // still km 2
      expect(h.km, isEmpty);
      await h.feed([fixAt(1000, 2043 + 1000)]); // km 3 across a bridge
      expect(h.km, [3]);
      h.recorder.dispose();
    });

    test('a paused run comes back paused, ignoring fixes', () async {
      final saved = await _checkpointAfter(5, pause: true);
      final h = _Host(at: _t0.add(const Duration(minutes: 5)));
      expect(await h.recorder.restore(saved), isTrue);
      expect(h.recorder.phase, RunPhase.paused);
      await h.feed([fixAt(300, 900)]);
      expect(h.recorder.livePoints.value, hasLength(5));
      h.recorder.resume();
      await h.feed([fixAt(310, 930)]);
      expect(h.recorder.livePoints.value.last.link, RunLink.segmentStart);
      expect(h.recorder.distanceM, closeTo(24, 0.5)); // nothing for the walk
      h.recorder.dispose();
    });

    test('the pace target comes back', () async {
      final h0 = _Host();
      await h0.recorder.start();
      h0.recorder.setPaceTarget(300);
      await h0.feed(straightRun(3));
      final saved = _viaJson(h0.recorder.checkpoint()!);
      h0.recorder.dispose();
      final h = _Host(at: _t0.add(const Duration(minutes: 1)));
      await h.recorder.restore(saved);
      expect(h.recorder.coach.target, 300);
      h.recorder.dispose();
    });

    test('a run with no fix yet restores and then records', () async {
      final h0 = _Host();
      await h0.recorder.start();
      final saved = _viaJson(h0.recorder.checkpoint()!);
      h0.recorder.dispose();
      final h = _Host(at: _t0.add(const Duration(minutes: 1)));
      expect(await h.recorder.restore(saved), isTrue);
      await h.feed(straightRun(3));
      expect(h.recorder.livePoints.value, hasLength(3));
      final track = (await h.recorder.finish())!;
      expect(track.points, hasLength(3));
      h.recorder.dispose();
    });

    test('finishing a restored run saves one track with the bridge', () async {
      final saved = await _checkpointAfter(10);
      final h = _Host(at: _t0.add(const Duration(minutes: 10)));
      await h.recorder.restore(saved);
      await h.feed([fixAt(318, 954), fixAt(320, 960)]);
      final track = (await h.recorder.finish())!;
      expect(track.points, hasLength(12));
      expect(track.id, '2026-11-09T12:00:00Z');
      expect(track.totalSeconds, 18 + 300 + 2);
      expect(track.distanceM, closeTo(960, 1));
      h.recorder.dispose();
    });

    test(
      'is refused (false, issue set) when location access is gone',
      () async {
        final saved = await _checkpointAfter(3);
        final source = ManualPositionSource(access: LocationAccess.denied);
        final h = _Host(source: source);
        expect(await h.recorder.restore(saved), isFalse);
        expect(h.recorder.phase, RunPhase.idle);
        expect(h.recorder.issue, RunIssue.denied);
        expect(h.suggestions, isEmpty);
        expect(source.subscriptions, 0);
        h.recorder.dispose();
      },
    );

    test('is false when opening the source throws', () async {
      final saved = await _checkpointAfter(3);
      final h = _Host(source: _ThrowingSource());
      expect(await h.recorder.restore(saved), isFalse);
      expect(h.recorder.phase, RunPhase.idle);
      expect(h.recorder.issue, RunIssue.streamError);
      h.recorder.dispose();
    });

    test('is false when a run is already going', () async {
      final saved = await _checkpointAfter(3);
      final h = _Host();
      await h.recorder.start();
      expect(await h.recorder.restore(saved), isFalse);
      expect(h.recorder.phase, RunPhase.recording);
      h.recorder.dispose();
    });

    test(
      'runs afterAccess (the foreground service) before listening',
      () async {
        final saved = await _checkpointAfter(3);
        final h = _Host();
        var served = false;
        await h.recorder.restore(saved, afterAccess: () async => served = true);
        expect(served, isTrue);
        h.recorder.dispose();
      },
    );

    test('past 5 h of wall clock it auto-ends at once on restore', () async {
      final saved = await _checkpointAfter(10);
      final h = _Host(at: _t0.add(const Duration(hours: 5, seconds: 1)));
      await h.recorder.restore(saved);
      expect(h.autoEnds, 1);
      expect(h.suggestions, isEmpty);
      // The host now finishes; the run saves like a manual finish.
      expect(await h.recorder.finish(), isNotNull);
      h.recorder.dispose();
    });
  });

  group('suggestions and auto end, off the timer and the clock', () {
    testWidgets('no fix for 5 min suggests finishing, never ends', (
      tester,
    ) async {
      final h = _Host();
      await h.recorder.start();
      await h.feed(straightRun(3), tester: tester);
      for (var i = 0; i < 61; i++) {
        h.now = h.now.add(const Duration(seconds: 5));
        await tester.pump(const Duration(seconds: 5));
      }
      expect(h.suggestions, [RunSuggestion.gpsLost]);
      expect(h.recorder.phase, RunPhase.recording);
      await h.finishIn(tester);
      h.recorder.dispose();
    });

    testWidgets('5 h wall clock ends the run once, pauses included', (
      tester,
    ) async {
      final h = _Host(autoEnd: const Duration(minutes: 2));
      await h.recorder.start();
      await h.feed(straightRun(3), tester: tester);
      h.recorder.pause();
      for (var i = 0; i < 30; i++) {
        h.now = h.now.add(const Duration(seconds: 5));
        await tester.pump(const Duration(seconds: 5));
      }
      expect(h.autoEnds, 1);
      expect(h.suggestions, isEmpty); // paused: only the auto end
      expect(await h.finishIn(tester), isNotNull);
      h.recorder.dispose();
    });

    testWidgets('finish() stops the timer: nothing fires afterwards', (
      tester,
    ) async {
      final h = _Host(autoEnd: const Duration(minutes: 1));
      await h.recorder.start();
      await h.feed(straightRun(3), tester: tester);
      await h.finishIn(tester);
      h.now = h.now.add(const Duration(hours: 1));
      await tester.pump(const Duration(minutes: 10));
      expect(h.autoEnds, 0);
      expect(h.suggestions, isEmpty);
      h.recorder.dispose();
    });

    test('a car (jump-rejected fixes) suggests finishing', () async {
      final h = _Host();
      await h.recorder.start();
      await h.feed(straightRun(2));
      await h.feed([for (var s = 4; s <= 100; s += 2) fixAt(s, s * 10.0)]);
      expect(h.suggestions, [RunSuggestion.vehicleSpeed]);
      h.recorder.dispose();
    });

    testWidgets('dispose cancels the watchdog timer', (tester) async {
      final h = _Host(autoEnd: const Duration(seconds: 1));
      await h.recorder.start();
      h.now = h.now.add(const Duration(hours: 1));
      h.recorder.dispose();
      await tester.pump(const Duration(seconds: 30));
      expect(h.autoEnds, 0);
    });
  });
}

class _ThrowingSource extends ManualPositionSource {
  @override
  Stream<GpsFix> fixes({Duration interval = const Duration(seconds: 2)}) =>
      throw StateError('provider gone');
}
