import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/run_phase.dart';
import 'package:workout_app/services/run_wire.dart';

import '../fake_audio_platform.dart';
import '../fake_run_engine.dart';
import '../run_host_rig.dart';

void main() {
  setUp(installFakeAudioPlatform);

  group('suggestions never end the run', () {
    test('cue, glyph in the notification, run keeps recording', () async {
      final rig = HostRig();
      await rig.cmd(RunCmd.start);
      rig.engine.addFix();
      rig.lastHooks.onSuggest('stationary');
      await pumpEventQueue();

      expect(rig.cues.suggestions, 1);
      expect(rig.engine.phase, RunPhase.recording);
      expect(rig.port.last['suggestion'], 'stationary');
      expect(rig.port.notes.last, startsWith('⏸ '));
      expect(rig.saved, isEmpty);
      expect(rig.port.stops, 0);
    });

    test('each reason has its own symbol', () async {
      final rig = HostRig();
      await rig.cmd(RunCmd.start);
      for (final (why, glyph) in [
        ('vehicleSpeed', '⚡'),
        ('gpsLost', '⌖'),
        ('restored', '↻'),
      ]) {
        rig.lastHooks.onSuggest(why);
        rig.engine.addFix();
        expect(rig.port.notes.last, startsWith('$glyph '), reason: why);
      }
    });

    test('a tap on the notification asks for the finish modal', () async {
      final rig = HostRig();
      await rig.cmd(RunCmd.start);
      rig.lastHooks.onSuggest('gpsLost');
      rig.host.notificationPressed();

      expect(rig.port.launches, 1);
      expect(rig.port.last['prompt'], isTrue);
      expect(rig.engine.phase, RunPhase.recording, reason: 'still needs a tap');

      await rig.cmd(RunCmd.ackPrompt);
      expect(rig.port.last['prompt'], isFalse);
      expect(rig.port.last['suggestion'], 'gpsLost');
    });

    test('a tap with no advice only opens the app', () async {
      final rig = HostRig();
      await rig.cmd(RunCmd.start);
      rig.host.notificationPressed();
      expect(rig.port.launches, 1);
      expect(rig.port.last['prompt'], isFalse);
    });

    test('advice while finishing is dropped', () async {
      final rig = HostRig();
      await rig.cmd(RunCmd.start);
      final finishing = rig.cmd(RunCmd.finish);
      rig.lastHooks.onSuggest('stationary');
      await finishing;
      expect(rig.cues.suggestions, 0);
    });
  });

  group('5 h auto end', () {
    test('saves like a finish and plays its own cue', () async {
      final rig = HostRig();
      await rig.cmd(RunCmd.start);
      rig.engine.addFix();
      rig.lastHooks.onAutoEnd();
      await pumpEventQueue();

      expect(rig.saved, hasLength(1));
      expect(rig.cues.autoEnds, 1);
      expect(rig.cues.finishes, 0);
      expect(rig.store.held, isNull);
      expect(rig.port.stops, 1);
    });
  });

  group('hooks', () {
    test('kilometres and pace cues reach the cues', () async {
      final rig = HostRig();
      await rig.cmd(RunCmd.start);
      rig.lastHooks.onKilometre(1);
      await pumpEventQueue();
      expect(rig.cues.kilometres, [1]);
    });
  });

  group('restoreFromStore', () {
    test('false with no checkpoint, and no engine is built', () async {
      final rig = HostRig();
      expect(await rig.host.restoreFromStore(), isFalse);
      expect(rig.engines, isEmpty);
    });

    test('resumes the run and tells the UI', () async {
      final rig = HostRig();
      rig.store.held = FakeCheckpoint(7);
      expect(await rig.host.restoreFromStore(), isTrue);

      expect(rig.engine.restored.single, isA<FakeCheckpoint>());
      expect(rig.port.last['phase'], 'recording');
    });

    test(
      'a checkpoint that cannot resume is kept and the issue shown',
      () async {
        final rig = HostRig()..restoreResult = false;
        rig.store.held = FakeCheckpoint(7);
        expect(await rig.host.restoreFromStore(), isTrue);

        expect(rig.store.held, isNotNull);
        expect(rig.port.last['issue'], 'streamError');
      },
    );
  });

  test('unknown commands are ignored', () async {
    final rig = HostRig();
    await rig.cmd('nonsense');
    expect(rig.engines, isEmpty);
    expect(rig.port.sent, isEmpty);
  });

  test('dispose lets go without ending anything', () async {
    final rig = HostRig();
    await rig.cmd(RunCmd.start);
    rig.host.dispose();
    expect(rig.engine.disposed, isTrue);
    expect(rig.saved, isEmpty);
    expect(rig.store.clears, 0);
    rig.host.dispose();
  });
}
