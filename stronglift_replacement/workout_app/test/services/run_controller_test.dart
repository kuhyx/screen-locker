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

  test('starts the service after access and before the first fix', () async {
    final source = ManualPositionSource();
    var subscribedAtStart = -1;
    final service = FakeForegroundRunClient(
      onStart: () => subscribedAtStart = source.subscriptions,
    );
    final controller = build(source, service);

    await controller.start();

    expect(subscribedAtStart, 0);
    expect(source.subscriptions, 1);
    expect(service.starts, [true]);
    expect(controller.serviceState, RunServiceState.running);
    expect(service.calls, ['has', 'start']);
    expect(service.drawn.single, '0.00|0:00  -:--');
    expect(controller.active, isTrue);
    controller.dispose();
  });

  test('the notification follows the run, redrawing only on change', () async {
    final source = ManualPositionSource();
    final service = FakeForegroundRunClient();
    final controller = build(source, service);
    await controller.start();

    await feed(source, [0, 6, 12, 18, 24, 30, 36]);

    expect(service.drawn.last, '0.04|0:12  5:33');
    expect(service.drawn.toSet(), hasLength(service.drawn.length));
    controller.dispose();
  });

  test('a refused permission never reaches the service', () async {
    final service = FakeForegroundRunClient();
    final controller = build(
      ManualPositionSource(access: LocationAccess.deniedForever),
      service,
    );
    await controller.watchIdle();
    await controller.start();
    expect(controller.view.issue, RunIssue.deniedForever);
    expect(controller.active, isFalse);
    controller.dispose();
  });

  test('denied notifications still record but draw nothing', () async {
    final source = ManualPositionSource();
    final service = FakeForegroundRunClient(
      permissionGranted: false,
      grantOnRequest: false,
    );
    final controller = build(source, service);
    await controller.start();
    await feed(source, [0, 6, 12]);

    expect(service.calls, ['has', 'request', 'start']);
    expect(controller.serviceState, RunServiceState.runningHidden);
    expect(service.drawn.first, '0.00|0:00  -:--');
    expect(controller.view.livePoints.value, hasLength(3));
    controller.dispose();
  });

  test('a service that will not start is flagged, the run goes on', () async {
    final source = ManualPositionSource();
    final controller = build(
      source,
      FakeForegroundRunClient(startSucceeds: false),
    );
    await controller.start();
    await feed(source, [0, 6]);
    expect(controller.serviceState, RunServiceState.failed);
    expect(controller.view.phase, RunPhase.recording);
    expect(controller.view.livePoints.value, hasLength(2));
    await controller.finish();
    expect(controller.serviceState, RunServiceState.failed);
    controller.dispose();
  });

  test('a platform without services records without one', () async {
    final source = ManualPositionSource();
    final service = FakeForegroundRunClient(isSupported: false);
    final controller = build(source, service);
    await controller.start();
    await feed(source, [0, 6]);
    await controller.finish();
    expect(controller.serviceState, RunServiceState.unsupported);
    expect(service.calls, isEmpty);
    expect(saved, hasLength(1));
    controller.dispose();
  });

  test('every start asks for the location service type', () async {
    final service = FakeForegroundRunClient();
    final controller = build(ManualPositionSource(), service);
    await controller.start();
    expect(service.starts, [true]);
    controller.dispose();
  });

  test('a kilometre buzzes and chimes once', () async {
    final source = ManualPositionSource();
    final controller = build(source, FakeForegroundRunClient());
    await controller.start();

    await feed(source, [for (var i = 0; i <= 170; i++) i * 6]);
    await Future<void>.delayed(const Duration(milliseconds: 50));

    expect(controller.view.distanceM, greaterThan(1000));
    expect(
      audio.resumedSources.where((s) => s.contains('workout_done')),
      hasLength(1),
    );
    controller.dispose();
  });

  test('finish stops the service, saves the track and reports it', () async {
    final source = ManualPositionSource();
    final service = FakeForegroundRunClient();
    final controller = build(source, service);
    await controller.start();
    await feed(source, [0, 6, 12, 18]);
    controller
      ..pause()
      ..resume();
    await pumpEventQueue();

    final notified = <bool>[];
    controller.addListener(() => notified.add(controller.saving));
    await controller.finish();

    expect(service.calls.last, 'stop');
    expect(controller.serviceState, RunServiceState.none);
    expect(saved.single.points, hasLength(4));
    expect(controller.saved!.stored, isTrue);
    expect(controller.saving, isFalse);
    expect(notified, contains(true));
    expect(controller.active, isFalse);
    controller.dispose();
  });

  test('a run too short to save is not saved', () async {
    final source = ManualPositionSource();
    final service = FakeForegroundRunClient();
    final controller = build(source, service);
    await controller.start();
    await controller.finish();
    expect(saved, isEmpty);
    expect(controller.saved, isNull);
    expect(controller.view.issue, RunIssue.tooShort);
    expect(service.calls.last, 'stop');
    controller.dispose();
  });

  test('a failing save is reported, not thrown', () async {
    final source = ManualPositionSource();
    final controller = buildRunController(
      source: source,
      save: (_) async => throw Exception('disk full'),
    );
    await controller.start();
    await feed(source, [0, 6]);
    await controller.finish();
    expect(controller.saved!.stored, isFalse);
    expect(controller.saved!.reason, contains('disk full'));
    controller.dispose();
  });

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

  test('the real client is unsupported off Android', () {
    expect(FlutterForegroundRunClient().isSupported, isFalse);
    expect(kRunOngoingChannelId, endsWith('_v1'));
  });
}
