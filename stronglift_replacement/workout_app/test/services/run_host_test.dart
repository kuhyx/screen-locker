import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/run_phase.dart';
import 'package:workout_app/services/run_wire.dart';

import '../fake_audio_platform.dart';
import '../fake_run_engine.dart';
import '../run_host_rig.dart';

void main() {
  setUp(installFakeAudioPlatform);

  group('start', () {
    test('builds an engine, records, and tells the UI', () async {
      final rig = HostRig();
      await rig.cmd(RunCmd.start, {'paceTarget': 330, 'sound': false});

      expect(rig.engine.phase, RunPhase.recording);
      expect(rig.engine.paceTarget, 330);
      expect(rig.cues.soundOn, isFalse);
      expect(rig.port.last['phase'], 'recording');
      expect(rig.port.last['from'], 0);
    });

    test('a second start never restarts a live run', () async {
      final rig = HostRig();
      await rig.cmd(RunCmd.start);
      rig.engine.addFix();
      await rig.cmd(RunCmd.start);

      expect(rig.engines, hasLength(1));
      expect(rig.engine.starts, 1);
      expect(rig.engine.disposed, isFalse);
      expect(rig.port.last['total'], 1);
      expect(rig.port.last['from'], 0, reason: 'a re-sync sends it all');
    });

    test('a refused start leaves the issue for the UI', () async {
      final rig = HostRig()..startResult = false;
      await rig.cmd(RunCmd.start);

      expect(rig.port.last['phase'], 'idle');
      expect(rig.port.last['issue'], 'denied');
    });

    test('a start after a finished run builds a fresh engine', () async {
      final rig = HostRig();
      await rig.cmd(RunCmd.start);
      await rig.cmd(RunCmd.finish);
      await rig.cmd(RunCmd.start);

      expect(rig.engines, hasLength(2));
      expect(rig.engines.first.disposed, isTrue);
      expect(rig.engine.phase, RunPhase.recording);
      expect(rig.port.last['done'], isFalse);
    });
  });

  group('snapshots', () {
    test('send only the new points, hello sends all', () async {
      final rig = HostRig();
      await rig.cmd(RunCmd.start);
      rig.engine
        ..addFix()
        ..addFix();
      expect(rig.port.last['from'], 1);
      expect(rig.port.last['pts'], hasLength(1));

      await rig.cmd(RunCmd.hello);
      expect(rig.port.last['from'], 0);
      expect(rig.port.last['pts'], hasLength(2));
      expect(isRunMessage(rig.port.last), isTrue);
    });

    test('hello with no run answers idle', () async {
      final rig = HostRig();
      await rig.cmd(RunCmd.hello);
      expect(rig.port.last['phase'], 'idle');
    });
  });

  group('checkpoint and notification', () {
    test('every change of an active run is saved and redrawn', () async {
      final rig = HostRig();
      await rig.cmd(RunCmd.start);
      rig.engine
        ..addFix()
        ..addFix();
      await pumpEventQueue();

      expect(rig.store.saves, greaterThanOrEqualTo(3));
      expect(rig.port.notes, isNotEmpty);
      final redraws = rig.port.notes.length;
      rig.engine.notifyListeners();
      expect(rig.port.notes, hasLength(redraws), reason: 'same words');
    });

    test('pause and resume are saved too', () async {
      final rig = HostRig();
      await rig.cmd(RunCmd.start);
      await pumpEventQueue();
      final before = rig.store.saves;
      await rig.cmd(RunCmd.pause);
      await rig.cmd(RunCmd.resume);
      await pumpEventQueue();

      expect(rig.engine.calls, containsAllInOrder(['pause', 'resume']));
      expect(rig.store.saves, before + 2);
    });

    test('a failed checkpoint write is logged, not fatal', () async {
      final rig = HostRig();
      rig.store.failSave = true;
      await rig.cmd(RunCmd.start);
      rig.engine.addFix();
      await pumpEventQueue();

      expect(rig.engine.phase, RunPhase.recording);
    });

    test('a pace target change goes to the engine', () async {
      final rig = HostRig();
      await rig.cmd(RunCmd.start);
      await rig.cmd(RunCmd.paceTarget, {'paceTarget': 300});
      expect(rig.engine.paceTarget, 300);
    });
  });

  group('finish', () {
    test('saves, clears the checkpoint, cues and stops the service', () async {
      final rig = HostRig();
      await rig.cmd(RunCmd.start);
      rig.engine.addFix();
      await rig.cmd(RunCmd.finish);

      expect(rig.saved, hasLength(1));
      expect(rig.store.held, isNull);
      expect(rig.cues.finishes, 1);
      expect(rig.port.stops, 1);
      expect(rig.port.last['done'], isTrue);
      expect(rig.port.last['saved'], {'stored': true, 'reason': 'saved'});
      expect(rig.port.sent.any((m) => m['saving'] == true), isTrue);
    });

    test('a refused save (duplicate) still ends the run cleanly', () async {
      final rig = HostRig(saveStores: false);
      await rig.cmd(RunCmd.start);
      await rig.cmd(RunCmd.finish);

      expect(rig.store.held, isNull);
      expect(rig.port.last['saved'], {'stored': false, 'reason': 'saved'});
      expect(rig.port.stops, 1);
    });

    test('a save that throws keeps the checkpoint', () async {
      final rig = HostRig(saveThrows: true);
      await rig.cmd(RunCmd.start);
      await pumpEventQueue();
      await rig.cmd(RunCmd.finish);

      expect(rig.store.held, isNotNull);
      expect(rig.port.last['saved'], {
        'stored': false,
        'reason': 'save failed: Exception: db locked',
      });
      expect(rig.port.last['done'], isTrue);
    });

    test('too few fixes: nothing saved, checkpoint cleared', () async {
      final rig = HostRig();
      await rig.cmd(RunCmd.start);
      rig.engine.track = null;
      await rig.cmd(RunCmd.finish);

      expect(rig.saved, isEmpty);
      expect(rig.store.held, isNull);
      expect(rig.port.last['saved'], isNull);
      expect(rig.port.last['done'], isTrue);
    });

    test('finishing with no active run does nothing', () async {
      final rig = HostRig();
      await rig.cmd(RunCmd.finish);
      expect(rig.saved, isEmpty);
      expect(rig.port.stops, 0);
    });

    test('finishing twice at once saves once', () async {
      final rig = HostRig();
      await rig.cmd(RunCmd.start);
      await Future.wait([rig.cmd(RunCmd.finish), rig.cmd(RunCmd.finish)]);
      expect(rig.saved, hasLength(1));
    });
  });

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
