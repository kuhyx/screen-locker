import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/position_source.dart';
import 'package:workout_app/services/run_recorder.dart';

import '../run_test_fixtures.dart';

RunRecorder _recorder(ManualPositionSource source, {List<int>? km}) =>
    RunRecorder(sourceFor: () => source, onKilometre: km?.add);

void main() {
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

    test('every recording is a run, whatever the speed', () async {
      final source = ManualPositionSource();
      final recorder = _recorder(source);
      await recorder.start();
      // 6.5 m/s (23 km/h) is over any walking cap, under the 25 km/h one.
      for (var i = 0; i < 6; i++) {
        source.controller.add(fixAt(i * 2, i * 13.0));
      }
      await pumpEventQueue();
      final track = await recorder.finish();
      expect(track!.sport, RunSport.running);
      expect(recorder.distanceM, closeTo(65, 1));
      recorder.dispose();
    });
  });

  group('noteAccess', () {
    test('a refusal while idle becomes the issue, a grant clears it', () {
      final recorder = _recorder(ManualPositionSource());
      recorder.noteAccess(LocationAccess.deniedForever);
      expect(recorder.issue, RunIssue.deniedForever);
      expect(recorder.issue.isAccess, isTrue);
      recorder.noteAccess(LocationAccess.granted);
      expect(recorder.issue, RunIssue.none);
      // A grant with nothing to clear leaves other issues alone.
      recorder.noteAccess(LocationAccess.granted);
      expect(recorder.issue, RunIssue.none);
      recorder.dispose();
    });

    test('is ignored once a recording has begun', () async {
      final recorder = _recorder(ManualPositionSource());
      await recorder.start();
      recorder.noteAccess(LocationAccess.denied);
      expect(recorder.issue, RunIssue.none);
      recorder.dispose();
    });

    test('every refusal maps to its issue', () {
      expect(RunIssue.forAccess(LocationAccess.denied), RunIssue.denied);
      expect(
        RunIssue.forAccess(LocationAccess.serviceOff),
        RunIssue.serviceOff,
      );
      expect(RunIssue.none.isAccess, isFalse);
      expect(RunIssue.tooShort.isAccess, isFalse);
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
