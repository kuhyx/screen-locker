import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/foreground_run_client.dart';
import 'package:workout_app/services/foreground_run_client_flutter.dart';
import 'package:workout_app/services/position_source.dart';
import 'package:workout_app/services/run_controller.dart';
import 'package:workout_app/services/run_phase.dart';
import 'package:workout_app/services/storage_service.dart';

import '../fake_audio_platform.dart';
import '../fake_run_service.dart';
import '../run_controller_rig.dart';
import '../run_test_fixtures.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late FakeAudioRecorder audio;
  late List<RunTrack> saved;

  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    StorageService.resetForTesting();
    await StorageService.init();
    audio = installFakeAudioPlatform();
    saved = [];
  });

  Future<void> feed(ManualPositionSource source, List<int> northM) async {
    for (final (i, m) in northM.indexed) {
      source.controller.add(fixAt(i * 2, m.toDouble()));
    }
    await pumpEventQueue();
    await pumpEventQueue();
  }

  RunController build(
    ManualPositionSource source,
    FakeForegroundRunClient service,
  ) => buildRunController(source: source, service: service, saved: saved);

  group('the run outlives the controller', () {
    test('disposing mid-run never stops the service or the run', () async {
      final source = ManualPositionSource();
      final service = FakeForegroundRunClient();
      final controller = build(source, service);
      await controller.start();
      await feed(source, [0, 6]);
      controller.dispose();

      expect(service.calls, isNot(contains('stop')));
      expect(saved, isEmpty);
      // The fix stream is still being listened to.
      source.controller.add(fixAt(4, 12));
      await pumpEventQueue();
    });

    test('a second start while a run is going changes nothing', () async {
      final source = ManualPositionSource();
      final service = FakeForegroundRunClient();
      final controller = build(source, service);
      await controller.start();
      await controller.start();
      expect(service.starts, hasLength(1));
      expect(source.subscriptions, 1);
      controller.dispose();
    });

    test('attach gives up when no host ever answers', () async {
      final controller = buildSilentController();
      await controller.attach();
      expect(controller.attachGaveUp, isTrue);
      expect(controller.view.synced, isFalse);
      controller.dispose();
    });

    test('a start nobody answers times out loudly, run untouched', () async {
      final controller = buildSilentController();
      await controller.start();
      expect(controller.active, isFalse);
      controller.dispose();
    });

    test('a pace target change and an ack are commands', () async {
      final source = ManualPositionSource();
      final controller = build(source, FakeForegroundRunClient());
      await controller.start(paceTarget: 330);
      expect(controller.view.paceTarget, 330);
      controller
        ..setPaceTarget(300)
        ..ackPrompt();
      await pumpEventQueue();
      expect(controller.view.paceTarget, 300);
      controller.dispose();
    });
  });
}
