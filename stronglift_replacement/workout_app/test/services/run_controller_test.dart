import 'package:audioplayers/audioplayers.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/sandbox/sandbox.dart';
import 'package:workout_app/services/feedback_cues.dart';
import 'package:workout_app/services/foreground_run_client.dart';
import 'package:workout_app/services/foreground_run_client_flutter.dart';
import 'package:workout_app/services/position_source.dart';
import 'package:workout_app/services/run_controller.dart';
import 'package:workout_app/services/run_recorder.dart';
import 'package:workout_app/services/run_saver.dart';
import 'package:workout_app/services/storage_service.dart';

import '../fake_audio_platform.dart';
import '../fake_run_service.dart';
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

  tearDown(() => Sandbox.enabled = false);

  RunController build(
    ManualPositionSource source,
    FakeForegroundRunClient service, {
    Future<RunSaveResult> Function(RunTrack)? save,
  }) => RunController(
    sourceFor: (_) => source,
    service: service,
    cues: FeedbackCues(AudioPlayer()),
    save:
        save ??
        (track) async {
          saved.add(track);
          return const RunSaveResult(stored: true, reason: 'saved');
        },
  );

  Future<void> feed(ManualPositionSource source, List<int> northM) async {
    for (final (i, m) in northM.indexed) {
      source.controller.add(fixAt(i * 2, m.toDouble()));
    }
    await pumpEventQueue();
  }

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
    expect(service.drawn.single, '0.00|0:00  --:--');
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
    await controller.start();
    expect(service.calls, isEmpty);
    expect(controller.serviceState, RunServiceState.none);
    expect(controller.recorder.issue, RunIssue.deniedForever);
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
    expect(service.drawn, hasLength(1));
    expect(controller.recorder.livePoints.value, hasLength(3));
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
    expect(controller.recorder.phase, RunPhase.recording);
    expect(controller.recorder.livePoints.value, hasLength(2));
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

  test('the sandbox asks for the data-sync service type alone', () async {
    Sandbox.enabled = true;
    final service = FakeForegroundRunClient();
    final controller = build(ManualPositionSource(), service);
    await controller.start();
    expect(service.starts, [false]);
    controller.dispose();
  });

  test('a kilometre buzzes and chimes once', () async {
    final source = ManualPositionSource();
    final controller = build(source, FakeForegroundRunClient());
    await controller.start();

    await feed(source, [for (var i = 0; i <= 170; i++) i * 6]);
    await Future<void>.delayed(const Duration(milliseconds: 50));

    expect(controller.recorder.distanceM, greaterThan(1000));
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
    expect(controller.recorder.issue, RunIssue.tooShort);
    expect(service.calls.last, 'stop');
    controller.dispose();
  });

  test('a failing save is reported, not thrown', () async {
    final source = ManualPositionSource();
    final controller = build(
      source,
      FakeForegroundRunClient(),
      save: (_) async => throw Exception('disk full'),
    );
    await controller.start();
    await feed(source, [0, 6]);
    await controller.finish();
    expect(controller.saved!.stored, isFalse);
    expect(controller.saved!.reason, contains('disk full'));
    controller.dispose();
  });

  test('leaving mid-run stops the service', () async {
    final source = ManualPositionSource();
    final service = FakeForegroundRunClient();
    final controller = build(source, service);
    await controller.start();
    controller.dispose();
    expect(service.calls.last, 'stop');
  });

  test('the real client is unsupported off Android', () {
    expect(FlutterForegroundRunClient().isSupported, isFalse);
    expect(kRunOngoingChannelId, endsWith('_v1'));
  });
}
