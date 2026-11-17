// The adapter over the real recorder: what the host relies on.
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/pace_band.dart';
import 'package:workout_app/services/run_engine.dart';
import 'package:workout_app/services/run_engine_recorder.dart';
import 'package:workout_app/services/run_phase.dart';

import '../run_test_fixtures.dart';

RunEngineHooks _hooks({
  void Function()? onAutoEnd,
  List<String>? advice,
  List<int>? km,
}) => RunEngineHooks(
  onKilometre: (k) => km?.add(k),
  onPaceCue: (PaceCue _) {},
  onSuggest: (why) => advice?.add(why),
  onAutoEnd: onAutoEnd ?? () {},
);

void main() {
  test('mirrors the recorder and ends cleanly', () async {
    final source = ManualPositionSource();
    final engine = recorderEngineFactory(() => source)(_hooks());
    expect(engine.phase, RunPhase.idle);
    expect(engine.checkpoint(), isNull);

    var changes = 0;
    void listener() => changes++;
    engine
      ..addListener(listener)
      ..setPaceTarget(330);
    expect(await engine.start(), isTrue);
    straightRun(20).forEach(source.controller.add);
    await pumpEventQueue();

    expect(engine.phase, RunPhase.recording);
    expect(engine.issue, RunIssue.none);
    expect(engine.points, hasLength(20));
    expect(engine.seconds, greaterThan(0));
    expect(engine.distanceM, greaterThan(0));
    expect(engine.paceTarget, 330);
    expect(engine.pace, isNotNull);
    expect(engine.band, isNotNull);
    expect(engine.checkpoint(), isNotNull);

    engine
      ..pause()
      ..resume();
    expect(engine.phase, RunPhase.recording);
    final track = await engine.finish();
    expect(track!.points, hasLength(20));
    expect(changes, greaterThan(0));
    engine
      ..removeListener(listener)
      ..dispose();
  });

  test('a checkpoint resumes the run in a fresh engine', () async {
    final source = ManualPositionSource();
    final first = recorderEngineFactory(() => source)(_hooks());
    await first.start();
    straightRun(20).forEach(source.controller.add);
    await pumpEventQueue();
    final checkpoint = first.checkpoint()!;
    first.dispose();

    final second = recorderEngineFactory(() => ManualPositionSource())(
      _hooks(),
    );
    expect(await second.restore(checkpoint), isTrue);
    expect(second.phase, RunPhase.recording);
    expect(second.points, hasLength(20));
    await second.finish();
    second.dispose();
  });

  test('the 5 h limit and advice reach the hooks', () async {
    final source = ManualPositionSource();
    var now = DateTime.utc(2026, 11, 9, 12);
    final advice = <String>[];
    var ended = 0;
    final engine = recorderEngineFactory(
      () => source,
      clock: () => now,
      autoEndAfter: const Duration(hours: 1),
    )(_hooks(advice: advice, onAutoEnd: () => ended++));
    await engine.start();
    now = now.add(const Duration(hours: 2));
    await Future<void>.delayed(const Duration(seconds: 6));
    expect(ended, 1);
    await engine.finish();
    engine.dispose();
  });
}
