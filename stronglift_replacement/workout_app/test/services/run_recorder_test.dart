import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/position_source.dart';
import 'package:workout_app/services/position_source_scripted.dart';
import 'package:workout_app/services/run_recorder.dart';

import '../run_test_fixtures.dart';

RunRecorder _recorder(ManualPositionSource source, {List<int>? km}) =>
    RunRecorder(sourceFor: (_) => source, onKilometre: km?.add);

void main() {
  group('a scripted run', () {
    test('records points, moving time and distance, then finishes', () async {
      final kms = <int>[];
      final recorder = RunRecorder(
        sourceFor: (_) => ScriptedPositionSource(straightRun(340)),
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
          sourceFor: (_) => ScriptedPositionSource(straightRun(5)),
        );
        await recorder.start();
        await pumpEventQueue();
        expect(recorder.phase, RunPhase.recording);
        expect(await recorder.finish(), isNotNull);
        recorder.dispose();
      },
    );

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

  group('start', () {
    test('refusals stay idle and say why', () async {
      for (final (access, issue) in [
        (LocationAccess.denied, RunIssue.denied),
        (LocationAccess.deniedForever, RunIssue.deniedForever),
        (LocationAccess.serviceOff, RunIssue.serviceOff),
      ]) {
        var served = false;
        final recorder = _recorder(ManualPositionSource(access: access));
        expect(
          await recorder.start(afterAccess: () async => served = true),
          isFalse,
        );
        expect(recorder.phase, RunPhase.idle);
        expect(recorder.issue, issue);
        expect(served, isFalse);
        recorder.dispose();
      }
    });

    test(
      'afterAccess runs once access is held, and a retry can succeed',
      () async {
        final order = <String>[];
        final recorder = _recorder(ManualPositionSource());
        expect(
          await recorder.start(afterAccess: () async => order.add('service')),
          isTrue,
        );
        expect(order, ['service']);
        expect(recorder.issue, RunIssue.none);
        recorder.dispose();
      },
    );

    test('a double tap starts one recording', () async {
      final source = ManualPositionSource();
      final recorder = _recorder(source);
      final first = recorder.start();
      final second = recorder.start();
      expect(await first, isTrue);
      expect(await second, isFalse);
      expect(await recorder.start(), isFalse);
      expect(source.subscriptions, 1);
      recorder.dispose();
    });

    test('the sport is chosen while idle only, and picks the source', () async {
      final seen = <RunSport>[];
      final recorder = RunRecorder(
        sourceFor: (sport) {
          seen.add(sport);
          return ManualPositionSource();
        },
      );
      expect(recorder.selectSport(RunSport.walking), isTrue);
      await recorder.start();
      expect(recorder.selectSport(RunSport.running), isFalse);
      expect(recorder.sport, RunSport.walking);
      expect(seen, [RunSport.walking]);
      recorder.dispose();
    });
  });

  group('trouble', () {
    test('a stream error is flagged and clears with the next fix', () async {
      final source = ManualPositionSource();
      final recorder = _recorder(source);
      await recorder.start();
      source.controller
        ..add(fixAt(0, 0))
        ..addError(StateError('gps off'));
      await pumpEventQueue();
      expect(recorder.issue, RunIssue.streamError);
      source.controller.add(fixAt(2, 6));
      await pumpEventQueue();
      expect(recorder.issue, RunIssue.none);
      recorder.dispose();
    });

    test('finishing with under two fixes saves nothing', () async {
      final source = ManualPositionSource();
      final recorder = _recorder(source);
      await recorder.start();
      source.controller.add(fixAt(0, 0));
      await pumpEventQueue();
      expect(await recorder.finish(), isNull);
      expect(recorder.issue, RunIssue.tooShort);
      recorder.dispose();
    });

    test('finish before any start is a no-op', () async {
      final recorder = _recorder(ManualPositionSource());
      expect(await recorder.finish(), isNull);
      expect(recorder.distanceM, 0);
      recorder.dispose();
    });
  });
}
