// The recorder's side of the pace target: the current pace, the band, the cues
// (throttled on fix time) and the reset around a pause.
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/pace_band.dart';
import 'package:workout_app/services/run_recorder.dart';

import '../run_test_fixtures.dart';

void main() {
  late ManualPositionSource source;
  late List<PaceCue> cues;
  late RunRecorder recorder;

  setUp(() {
    source = ManualPositionSource();
    cues = [];
    recorder = RunRecorder(sourceFor: () => source, onPaceCue: cues.add);
  });

  tearDown(() => recorder.dispose());

  Future<void> feed(int count, {int from = 0, double mps = 3}) async {
    for (var i = 0; i < count; i++) {
      final s = from + i * 2;
      source.controller.add(fixAt(s, s * mps));
    }
    await pumpEventQueue();
  }

  test(
    'no target: a pace is tracked but there is no band and no cue',
    () async {
      await recorder.start();
      await feed(30);
      expect(recorder.coach.pace, closeTo(1000 / 3, 0.01));
      expect(recorder.coach.target, isNull);
      expect(recorder.coach.band, isNull);
      expect(cues, isEmpty);
    },
  );

  test('warm-up: no band until 20 s of fixes', () async {
    recorder.setPaceTarget(300);
    await recorder.start();
    await feed(5);
    expect(recorder.coach.pace, isNull);
    expect(recorder.coach.band, isNull);
    expect(cues, isEmpty);
  });

  test('too slow cues once, then every 30 s of fix time', () async {
    recorder.setPaceTarget(300);
    await recorder.start();
    await feed(11); // t = 20 s
    expect(recorder.coach.band, PaceBand.tooSlow);
    expect(cues, [PaceCue.tooSlow]);
    await feed(14, from: 22); // up to t = 48 s
    expect(cues, hasLength(1));
    await feed(2, from: 50); // t = 52 s, 32 s after the first
    expect(cues, [PaceCue.tooSlow, PaceCue.tooSlow]);
  });

  test('too fast uses the other cue; on pace is silent', () async {
    recorder.setPaceTarget(420);
    await recorder.start();
    await feed(15);
    expect(cues, [PaceCue.tooFast]);

    cues.clear();
    recorder.setPaceTarget(335); // within +-10 of 5:33
    await feed(5, from: 30);
    expect(recorder.coach.band, PaceBand.onPace);
    expect(cues, isEmpty);
  });

  test('clearing the target drops the band', () async {
    recorder.setPaceTarget(300);
    await recorder.start();
    await feed(15);
    recorder.setPaceTarget(null);
    expect(recorder.coach.band, isNull);
    expect(recorder.coach.target, isNull);
  });

  test('a pause does not read as too slow when the run resumes', () async {
    recorder.setPaceTarget(335);
    await recorder.start();
    await feed(15);
    recorder.pause();
    recorder.resume();
    // 12 s later, same speed: the stretch standing still is not in the window.
    await feed(8, from: 42);
    expect(recorder.coach.pace, isNull); // warming up again
    await feed(8, from: 58);
    expect(recorder.coach.band, PaceBand.onPace);
    expect(cues, isEmpty);
  });

  test('a new target forgets the last cue so it can speak at once', () async {
    recorder.setPaceTarget(300);
    await recorder.start();
    await feed(12);
    expect(cues, hasLength(1));
    recorder.setPaceTarget(420);
    await feed(1, from: 24);
    expect(cues, [PaceCue.tooSlow, PaceCue.tooFast]);
  });
}
