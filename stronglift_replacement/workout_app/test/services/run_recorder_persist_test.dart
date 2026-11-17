import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/gps_filter.dart';
import 'package:workout_app/services/position_source.dart';
import 'package:workout_app/services/run_checkpoint.dart';
import 'package:workout_app/services/run_recorder.dart';

import '../run_recorder_persist_rig.dart';
import '../run_test_fixtures.dart';

void main() {
  group('checkpoint()', () {
    test('is null when idle and after finish', () async {
      final h = PersistHost();
      expect(h.recorder.checkpoint(), isNull);
      await h.recorder.start();
      expect(h.recorder.checkpoint(), isNotNull);
      await h.recorder.finish();
      expect(h.recorder.checkpoint(), isNull);
      h.recorder.dispose();
    });

    test('holds the whole recording state', () async {
      final h = PersistHost(at: persistT0.add(const Duration(minutes: 3)));
      await h.recorder.start();
      h.recorder.setPaceTarget(330);
      await h.feed(straightRun(10));
      final c = h.recorder.checkpoint()!;
      expect(c.startedAt, persistT0.add(const Duration(minutes: 3)));
      expect(c.savedAt, h.now);
      expect(c.phase, RunPhase.recording);
      expect(c.points, hasLength(10));
      expect(c.distanceM, closeTo(54, 0.5));
      expect(c.movingSeconds, 18);
      expect(c.paceTargetSeconds, 330);
      expect(c.segmentBreak, isFalse);
      expect(c.id, '2026-11-09T12:00:00Z');
      h.recorder.dispose();
    });

    test('a pause is recorded with its segment break', () async {
      final c = await checkpointAfter(5, pause: true);
      expect(c.phase, RunPhase.paused);
      expect(c.segmentBreak, isTrue);
    });
  });

  group('onCheckpoint', () {
    test('fires on start, every accepted fix, pause and resume', () async {
      final h = PersistHost();
      await h.recorder.start();
      expect(h.checkpoints, hasLength(1));
      await h.feed(straightRun(3));
      expect(h.checkpoints, hasLength(4));
      await h.feed([fixAt(6, 18, accuracy: 99)]); // dropped: no checkpoint
      expect(h.checkpoints, hasLength(4));
      h.recorder.pause();
      h.recorder.resume();
      expect(h.checkpoints.map((c) => c.phase), [
        RunPhase.recording,
        RunPhase.recording,
        RunPhase.recording,
        RunPhase.recording,
        RunPhase.paused,
        RunPhase.recording,
      ]);
      h.recorder.dispose();
    });
  });

  group('restore()', () {
    test('re-enters recording with the state and tells the host', () async {
      final saved = await checkpointAfter(10);
      final h = PersistHost(at: persistT0.add(const Duration(minutes: 10)));
      expect(await h.recorder.restore(saved), isTrue);
      expect(h.recorder.phase, RunPhase.recording);
      expect(h.recorder.seconds, 18);
      expect(h.recorder.distanceM, closeTo(54, 0.5));
      expect(h.recorder.livePoints.value, hasLength(10));
      expect(h.source.subscriptions, 1);
      expect(h.suggestions, [RunSuggestion.restored]);
      expect(h.autoEnds, 0);
      h.recorder.dispose();
    });

    test('the dead time is bridged and credited at a running pace', () async {
      final saved = await checkpointAfter(10); // last fix: 18 s, 54 m
      final h = PersistHost(at: persistT0.add(const Duration(minutes: 10)));
      await h.recorder.restore(saved);
      await h.feed([fixAt(318, 954)]); // 300 s later, 900 m on: 3 m/s
      expect(h.recorder.distanceM, closeTo(954, 1));
      expect(h.recorder.seconds, 18 + 300);
      expect(h.recorder.livePoints.value.last.link, RunLink.bridge);
      h.recorder.dispose();
    });

    test('a vehicle-speed gap is drawn but earns nothing', () async {
      final saved = await checkpointAfter(10);
      final h = PersistHost(at: persistT0.add(const Duration(minutes: 10)));
      await h.recorder.restore(saved);
      await h.feed([fixAt(78, 54 + 600)]); // 60 s, 600 m: 36 km/h
      expect(h.recorder.distanceM, closeTo(54, 0.5));
      expect(h.recorder.seconds, 18);
      expect(h.recorder.livePoints.value, hasLength(11));
      h.recorder.dispose();
    });

    test('kilometres already announced are not announced again', () async {
      final h0 = PersistHost();
      await h0.recorder.start();
      await h0.feed(straightRun(340)); // 2 km
      final saved = viaJson(h0.recorder.checkpoint()!);
      expect(h0.km, [1, 2]);
      await h0.recorder.finish();
      h0.recorder.dispose();

      final h = PersistHost(at: persistT0.add(const Duration(hours: 1)));
      await h.recorder.restore(saved);
      await h.feed([fixAt(681, 2043)]); // still km 2
      expect(h.km, isEmpty);
      await h.feed([fixAt(1000, 2043 + 1000)]); // km 3 across a bridge
      expect(h.km, [3]);
      h.recorder.dispose();
    });

    test('a paused run comes back paused, ignoring fixes', () async {
      final saved = await checkpointAfter(5, pause: true);
      final h = PersistHost(at: persistT0.add(const Duration(minutes: 5)));
      expect(await h.recorder.restore(saved), isTrue);
      expect(h.recorder.phase, RunPhase.paused);
      await h.feed([fixAt(300, 900)]);
      expect(h.recorder.livePoints.value, hasLength(5));
      h.recorder.resume();
      await h.feed([fixAt(310, 930)]);
      expect(h.recorder.livePoints.value.last.link, RunLink.segmentStart);
      expect(h.recorder.distanceM, closeTo(24, 0.5)); // nothing for the walk
      h.recorder.dispose();
    });

    test('the pace target comes back', () async {
      final h0 = PersistHost();
      await h0.recorder.start();
      h0.recorder.setPaceTarget(300);
      await h0.feed(straightRun(3));
      final saved = viaJson(h0.recorder.checkpoint()!);
      h0.recorder.dispose();
      final h = PersistHost(at: persistT0.add(const Duration(minutes: 1)));
      await h.recorder.restore(saved);
      expect(h.recorder.coach.target, 300);
      h.recorder.dispose();
    });

    test('a run with no fix yet restores and then records', () async {
      final h0 = PersistHost();
      await h0.recorder.start();
      final saved = viaJson(h0.recorder.checkpoint()!);
      h0.recorder.dispose();
      final h = PersistHost(at: persistT0.add(const Duration(minutes: 1)));
      expect(await h.recorder.restore(saved), isTrue);
      await h.feed(straightRun(3));
      expect(h.recorder.livePoints.value, hasLength(3));
      final track = (await h.recorder.finish())!;
      expect(track.points, hasLength(3));
      h.recorder.dispose();
    });

    test('finishing a restored run saves one track with the bridge', () async {
      final saved = await checkpointAfter(10);
      final h = PersistHost(at: persistT0.add(const Duration(minutes: 10)));
      await h.recorder.restore(saved);
      await h.feed([fixAt(318, 954), fixAt(320, 960)]);
      final track = (await h.recorder.finish())!;
      expect(track.points, hasLength(12));
      expect(track.id, '2026-11-09T12:00:00Z');
      expect(track.totalSeconds, 18 + 300 + 2);
      expect(track.distanceM, closeTo(960, 1));
      h.recorder.dispose();
    });

    test(
      'is refused (false, issue set) when location access is gone',
      () async {
        final saved = await checkpointAfter(3);
        final source = ManualPositionSource(access: LocationAccess.denied);
        final h = PersistHost(source: source);
        expect(await h.recorder.restore(saved), isFalse);
        expect(h.recorder.phase, RunPhase.idle);
        expect(h.recorder.issue, RunIssue.denied);
        expect(h.suggestions, isEmpty);
        expect(source.subscriptions, 0);
        h.recorder.dispose();
      },
    );

    test('is false when opening the source throws', () async {
      final saved = await checkpointAfter(3);
      final h = PersistHost(source: ThrowingSource());
      expect(await h.recorder.restore(saved), isFalse);
      expect(h.recorder.phase, RunPhase.idle);
      expect(h.recorder.issue, RunIssue.streamError);
      h.recorder.dispose();
    });

    test('is false when a run is already going', () async {
      final saved = await checkpointAfter(3);
      final h = PersistHost();
      await h.recorder.start();
      expect(await h.recorder.restore(saved), isFalse);
      expect(h.recorder.phase, RunPhase.recording);
      h.recorder.dispose();
    });

    test(
      'runs afterAccess (the foreground service) before listening',
      () async {
        final saved = await checkpointAfter(3);
        final h = PersistHost();
        var served = false;
        await h.recorder.restore(saved, afterAccess: () async => served = true);
        expect(served, isTrue);
        h.recorder.dispose();
      },
    );

    test('past 5 h of wall clock it auto-ends at once on restore', () async {
      final saved = await checkpointAfter(10);
      final h = PersistHost(
        at: persistT0.add(const Duration(hours: 5, seconds: 1)),
      );
      await h.recorder.restore(saved);
      expect(h.autoEnds, 1);
      expect(h.suggestions, isEmpty);
      // The host now finishes; the run saves like a manual finish.
      expect(await h.recorder.finish(), isNotNull);
      h.recorder.dispose();
    });
  });
}
