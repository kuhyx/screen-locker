import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/sandbox/sandbox.dart';
import 'package:workout_app/services/position_source_scripted.dart';
import 'package:workout_app/services/run_recorder.dart';

import '../run_test_fixtures.dart';

RunRecorder _recorder(ManualPositionSource source, {List<int>? km}) =>
    RunRecorder(sourceFor: () => source, onKilometre: km?.add);

void main() {
  group('a scripted run', () {
    test('records points, moving time and distance, then finishes', () async {
      final kms = <int>[];
      final recorder = RunRecorder(
        sourceFor: () => ScriptedPositionSource(straightRun(340)),
        onKilometre: kms.add,
      );
      expect(await recorder.start(), isTrue);
      await pumpEventQueue();

      expect(recorder.phase, RunPhase.recording);
      expect(kms, [1, 2]);
      expect(recorder.livePoints.value, hasLength(340));
      expect(recorder.distanceM, closeTo(2034, 5));
      expect(recorder.seconds, 678);

      final track = (await recorder.finish())!;
      expect(recorder.phase, RunPhase.finished);
      expect(track.sport, RunSport.running);
      expect(track.points, hasLength(340));
      expect(track.totalSeconds, 678);
      expect(track.distanceM, closeTo(2034, 5));
      expect(track.startedAt, DateTime.utc(2026, 11, 9, 12));
      expect(track.id, '2026-11-09T12:00:00Z');
      expect(track.source, RunSource.app);
      recorder.dispose();
    });

    test(
      'a stream that ends early is logged, the run is still savable',
      () async {
        final recorder = RunRecorder(
          sourceFor: () => ScriptedPositionSource(straightRun(5)),
        );
        await recorder.start();
        await pumpEventQueue();
        expect(recorder.phase, RunPhase.recording);
        expect(await recorder.finish(), isNotNull);
        recorder.dispose();
      },
    );

    test('the sandbox trace labels distance in metres, not km', () async {
      TestWidgetsFlutterBinding.ensureInitialized();
      final printed = <String>[];
      debugPrint = (message, {wrapWidth}) => printed.add(message ?? '');
      Sandbox.enabled = true;
      addTearDown(() {
        debugPrint = debugPrintThrottled;
        Sandbox.enabled = false;
      });
      final recorder = RunRecorder(
        sourceFor: () => ScriptedPositionSource(straightRun(340)),
      );
      await recorder.start();
      await pumpEventQueue();
      await recorder.finish();
      final lines = printed.where(
        (l) => l.contains('run stream ended') || l.contains('run finished'),
      );
      expect(lines, hasLength(2));
      expect(
        lines.first,
        startsWith('WorkoutSandbox: run stream ended {m: 20'),
      );
      expect(lines.last, startsWith('WorkoutSandbox: run finished {m: 20'));
      expect(lines.join(), isNot(contains('km:')));
      recorder.dispose();
    });

    test('a stream closing after finish is ignored', () async {
      final source = ManualPositionSource();
      final recorder = _recorder(source);
      await recorder.start();
      source.controller
        ..add(fixAt(0, 0))
        ..add(fixAt(2, 6));
      await pumpEventQueue();
      await recorder.finish();
      await source.controller.close();
      await pumpEventQueue();
      expect(recorder.phase, RunPhase.finished);
      recorder.dispose();
    });
  });

  group('filtering', () {
    test('a mock fix is dropped and flagged until a real one lands', () async {
      final source = ManualPositionSource();
      final recorder = _recorder(source);
      await recorder.start();
      source.controller
        ..add(fixAt(0, 0))
        ..add(fixAt(2, 6, mocked: true))
        ..add(fixAt(4, 12, mocked: true));
      await pumpEventQueue();
      expect(recorder.issue, RunIssue.mockedLocation);
      expect(recorder.livePoints.value, hasLength(1));

      source.controller.add(fixAt(6, 18));
      await pumpEventQueue();
      expect(recorder.issue, RunIssue.none);
      expect(recorder.livePoints.value, hasLength(2));
      recorder.dispose();
    });

    test('a GPS jump is dropped without crediting the leap', () async {
      final source = ManualPositionSource();
      final recorder = _recorder(source);
      await recorder.start();
      source.controller
        ..add(fixAt(0, 0))
        ..add(fixAt(2, 6))
        ..add(fixAt(4, 5000))
        ..add(fixAt(6, 18));
      await pumpEventQueue();
      expect(recorder.livePoints.value, hasLength(3));
      expect(recorder.distanceM, closeTo(18, 0.5));
      expect(recorder.seconds, 6);
      recorder.dispose();
    });

    test('an inaccurate fix is dropped', () async {
      final source = ManualPositionSource();
      final recorder = _recorder(source);
      await recorder.start();
      source.controller
        ..add(fixAt(0, 0, accuracy: 80))
        ..add(fixAt(2, 6, accuracy: 90));
      await pumpEventQueue();
      expect(recorder.livePoints.value, isEmpty);
      expect(recorder.issue, RunIssue.none);
      recorder.dispose();
    });
  });

  group('pause', () {
    test('credits nothing while paused or across the resume', () async {
      final source = ManualPositionSource();
      final recorder = _recorder(source);
      await recorder.start();
      source.controller
        ..add(fixAt(0, 0))
        ..add(fixAt(2, 6))
        ..add(fixAt(4, 12));
      await pumpEventQueue();
      expect(recorder.seconds, 4);

      recorder.pause();
      expect(recorder.phase, RunPhase.paused);
      source.controller
        ..add(fixAt(6, 18))
        ..add(fixAt(8, 24));
      await pumpEventQueue();
      expect(recorder.livePoints.value, hasLength(3));

      recorder.resume();
      expect(recorder.phase, RunPhase.recording);
      source.controller
        ..add(fixAt(10, 30))
        ..add(fixAt(12, 36));
      await pumpEventQueue();
      expect(recorder.livePoints.value, hasLength(5));
      // 4 s before the pause, 2 s after the first post-resume fix.
      expect(recorder.seconds, 6);
      expect(recorder.distanceM, closeTo(18, 0.5));
      expect(source.subscriptions, 1);

      final track = (await recorder.finish())!;
      expect(track.totalSeconds, 6);
      recorder.dispose();
    });

    test(
      'finish works from paused; pause and resume elsewhere are no-ops',
      () async {
        final source = ManualPositionSource();
        final recorder = _recorder(source)
          ..pause()
          ..resume();
        expect(recorder.phase, RunPhase.idle);
        await recorder.start();
        recorder.resume();
        expect(recorder.phase, RunPhase.recording);
        source.controller
          ..add(fixAt(0, 0))
          ..add(fixAt(2, 6));
        await pumpEventQueue();
        recorder.pause();
        expect(await recorder.finish(), isNotNull);
        recorder.pause();
        expect(recorder.phase, RunPhase.finished);
        expect(await recorder.finish(), isNull);
        recorder.dispose();
      },
    );
  });
}
