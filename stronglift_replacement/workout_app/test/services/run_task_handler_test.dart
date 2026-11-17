import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/run_phase.dart';
import 'package:workout_app/services/run_task_handler.dart';
import 'package:workout_app/services/run_wire.dart';

import '../fake_audio_platform.dart';
import '../fake_run_engine.dart';
import '../run_host_rig.dart';

void main() {
  setUp(installFakeAudioPlatform);

  RunTaskHandler handlerFor(HostRig rig) =>
      RunTaskHandler(host: rig.host, port: rig.port);

  group('onStart', () {
    test('a system start with a checkpoint resumes the run', () async {
      final rig = HostRig();
      rig.store.held = FakeCheckpoint(1);
      await handlerFor(rig).onStart(startedBySystem: true);

      expect(rig.engine.restored, hasLength(1));
      expect(rig.engine.phase, RunPhase.recording);
      expect(rig.port.stops, 0);
    });

    test('an app start with a checkpoint resumes it too (force-stop)', () async {
      final rig = HostRig();
      rig.store.held = FakeCheckpoint(1);
      await handlerFor(rig).onStart(startedBySystem: false);
      expect(rig.engine.phase, RunPhase.recording);
    });

    test('a system start with no checkpoint stops itself', () async {
      final rig = HostRig();
      await handlerFor(rig).onStart(startedBySystem: true);

      expect(rig.port.stops, 1);
      expect(rig.engines, isEmpty);
    });

    test('an app start with no checkpoint waits for the start command', () async {
      final rig = HostRig();
      await handlerFor(rig).onStart(startedBySystem: false);

      expect(rig.port.stops, 0);
      expect(rig.engines, isEmpty);
    });
  });

  group('messages', () {
    test('run commands reach the host', () async {
      final rig = HostRig();
      final handler = handlerFor(rig)
        ..onReceiveData({'cmd': RunCmd.start});
      await pumpEventQueue();

      expect(rig.engine.phase, RunPhase.recording);
      handler.onReceiveData({'cmd': RunCmd.pause});
      await pumpEventQueue();
      expect(rig.engine.phase, RunPhase.paused);
    });

    test('a break-service message is ignored', () async {
      final rig = HostRig();
      handlerFor(rig)
        ..onReceiveData({'workoutType': 'A', 'restEndsAtMs': 5})
        ..onReceiveData('nudge');
      await pumpEventQueue();

      expect(rig.engines, isEmpty);
      expect(rig.port.sent, isEmpty);
    });
  });

  test('a notification tap goes to the host', () async {
    final rig = HostRig();
    handlerFor(rig).onNotificationPressed();
    expect(rig.port.launches, 1);
  });

  test('destroy lets go and never ends the run', () async {
    final rig = HostRig();
    final handler = handlerFor(rig)..onReceiveData({'cmd': RunCmd.start});
    await pumpEventQueue();
    handler.onDestroy();

    expect(rig.engine.disposed, isTrue);
    expect(rig.saved, isEmpty);
    expect(rig.store.clears, 0);
  });
}
