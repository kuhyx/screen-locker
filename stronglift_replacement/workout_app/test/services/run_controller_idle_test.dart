// The controller's idle side (display-only position, blocked state) and the
// pace cue wiring.
import 'package:audioplayers/audioplayers.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/feedback_cues.dart';
import 'package:workout_app/services/pace_band.dart';
import 'package:workout_app/services/position_source.dart';
import 'package:workout_app/services/run_controller.dart';
import 'package:workout_app/services/run_recorder.dart';
import 'package:workout_app/services/run_saver.dart';

import '../fake_audio_platform.dart';
import '../fake_run_service.dart';
import '../run_test_fixtures.dart';

class _CueSpy extends FeedbackCues {
  _CueSpy() : super(AudioPlayer());

  final paced = <PaceCue>[];

  @override
  Future<void> load() async {}

  @override
  Future<void> paceOff(PaceCue cue) async => paced.add(cue);
}

RunController _build(
  ManualPositionSource source, {
  PositionSource Function()? idleSourceFor,
  FeedbackCues? cues,
  FakeForegroundRunClient? service,
}) => RunController(
  sourceFor: () => source,
  idleSourceFor: idleSourceFor,
  service: service ?? FakeForegroundRunClient(),
  cues: cues ?? _CueSpy(),
  save: (_) async => const RunSaveResult(stored: true, reason: 'saved'),
);

void main() {
  setUp(installFakeAudioPlatform);

  group('idle location', () {
    test('watching asks for access and tracks the position', () async {
      final source = ManualPositionSource();
      final controller = _build(source);
      expect(controller.canStart, isFalse);
      await controller.watchIdle();
      expect(controller.canStart, isTrue);
      expect(controller.blocked, isFalse);
      source.controller.add(fixAt(0, 0));
      await pumpEventQueue();
      expect(controller.position.value, isNotNull);
      controller.dispose();
    });

    test('a refusal blocks until a silent recheck finds a grant', () async {
      final source = ManualPositionSource(access: LocationAccess.deniedForever);
      final controller = _build(source);
      await controller.watchIdle();
      expect(controller.blocked, isTrue);
      expect(controller.canStart, isFalse);
      expect(controller.recorder.issue, RunIssue.deniedForever);

      source.access = LocationAccess.granted;
      await controller.recheckAccess();
      expect(controller.blocked, isFalse);
      expect(controller.canStart, isTrue);
      expect(source.requests, 1);
      controller.dispose();
    });

    test(
      'starting ends the idle watch; a recording is not rechecked',
      () async {
        final source = ManualPositionSource();
        final controller = _build(source);
        await controller.watchIdle();
        await controller.start();
        source.controller.add(fixAt(0, 0));
        await pumpEventQueue();
        // Only the recorder listens now, and the display dot did not move.
        expect(controller.position.value, isNull);
        final checks = source.checks;
        await controller.recheckAccess();
        expect(source.checks, checks);
        controller.dispose();
      },
    );

    test('a separate idle source feeds the idle map only', () async {
      final run = ManualPositionSource();
      final idle = ManualPositionSource();
      final controller = _build(run, idleSourceFor: () => idle);
      await controller.watchIdle();
      expect(idle.requests, 1);
      expect(run.requests, 0);
      controller.dispose();
    });
  });

  test('pace cues reach the cue player and the notification', () async {
    final source = ManualPositionSource();
    final service = FakeForegroundRunClient();
    final cues = _CueSpy();
    final controller = _build(source, cues: cues, service: service);
    controller.recorder.setPaceTarget(300);
    await controller.start();
    for (var i = 0; i < 12; i++) {
      source.controller.add(fixAt(i * 2, i * 6.0));
    }
    await pumpEventQueue();
    expect(cues.paced, [PaceCue.tooSlow]);
    expect(service.drawn.last, endsWith('5:35'));
    controller.dispose();
  });

  test('without a target the notification carries no current pace', () async {
    final source = ManualPositionSource();
    final service = FakeForegroundRunClient();
    final controller = _build(source, service: service);
    await controller.start();
    for (var i = 0; i < 12; i++) {
      source.controller.add(fixAt(i * 2, i * 6.0));
    }
    await pumpEventQueue();
    expect(service.drawn.last.split('  '), hasLength(2));
    controller.dispose();
  });
}
