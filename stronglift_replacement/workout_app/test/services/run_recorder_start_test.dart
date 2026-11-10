import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/position_source.dart';
import 'package:workout_app/services/run_recorder.dart';

import '../run_test_fixtures.dart';

RunRecorder _recorder(ManualPositionSource source, {List<int>? km}) =>
    RunRecorder(sourceFor: (_) => source, onKilometre: km?.add);

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
