import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/workout_plan.dart';
import 'package:workout_app/services/backup_service.dart';
import 'package:workout_app/services/storage_service.dart';

StorageService get _svc => StorageService.instance;

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    StorageService.resetForTesting();
    await StorageService.init();
  });

  // ── Workout type ───────────────────────────────────────────────────────────

  test('applyProgression bumps reps (not weight) once at max weight', () async {
    final name = workoutA.first.name;
    final maxW = (await _svc.getExerciseState(name))!.maxWeight;
    // Pin the working weight at the cap; streaks reset to 0.
    await _svc.setExerciseWeight(name, maxW);
    final startReps = (await _svc.getExerciseState(name))!.reps;

    // Default success threshold is 3 — three straight successes trigger a
    // progression, which at the cap increments reps instead of weight.
    final today = DateTime.now();
    for (var i = 0; i < 3; i++) {
      await _svc.applyProgression(
        succeededExercises: {name: true},
        lastWorkoutDate: today,
      );
    }

    final st = (await _svc.getExerciseState(name))!;
    expect(st.weight, maxW); // weight stayed capped
    expect(st.reps, startReps + 1); // reps incremented instead
  });

  // ── Restore from backup ─────────────────────────────────────────────────────

  // Regression guard for the 2026-08-05 data loss: a reinstall re-seeded the
  // DB to factory defaults, and the first write afterwards exported those
  // defaults over /sdcard/WorkoutTracker/backup.json -- destroying the only
  // off-device copy of months of progression. The seed is survivable; the
  // clobber is what made it permanent.
  group('restoreSyncedSessions', () {
    Map<String, dynamic> session(String date, String start) => {
      'workout_type': 'B',
      'date': date,
      'start_time': start,
      'duration_seconds': 3600,
      'succeeded': true,
      'exercises': [
        {'name': 'Situp', 'targetReps': 31, 'targetWeight': 10.0, 'sets': []},
      ],
    };

    test('restores sessions the local DB is missing', () async {
      final restored = await _svc.restoreSyncedSessions([
        session('2026-07-17', '2026-07-17T09:48:34.338'),
        session('2026-07-27', '2026-07-27T09:14:22.547'),
      ]);
      expect(restored, 2);
      final hist = await _svc.getWorkoutHistory();
      expect(hist.length, 2);
      expect(hist.first['date'], '2026-07-27');
    });

    test('is idempotent — re-syncing never duplicates a session', () async {
      final payloads = [session('2026-07-17', '2026-07-17T09:48:34.338')];
      expect(await _svc.restoreSyncedSessions(payloads), 1);
      expect(await _svc.restoreSyncedSessions(payloads), 0);
      expect((await _svc.getWorkoutHistory()).length, 1);
    });

    test('does not duplicate a session the device already recorded', () async {
      final payload = session('2026-08-10', '2026-08-10T10:19:44.075703');
      await _svc.saveSession(
        date: '2026-08-10',
        workoutType: 'B',
        durationSeconds: 10313,
        succeeded: true,
        json: jsonEncode(payload),
      );
      expect(await _svc.restoreSyncedSessions([payload]), 0);
      expect((await _svc.getWorkoutHistory()).length, 1);
    });

    test('ignores PC-side records that are not sessions', () async {
      // runnerup/manual entries have no `exercises` and belong in the synced
      // list, not local history.
      final restored = await _svc.restoreSyncedSessions([
        {'kind': 'runnerup_verified', 'date': '2026-07-12', 'type': 'x'},
        {'kind': 'manual_workout', 'date': '2026-07-13', 'type': 'y'},
      ]);
      expect(restored, 0);
      expect(await _svc.getWorkoutHistory(), isEmpty);
    });

    test('empty payload list is a no-op', () async {
      expect(await _svc.restoreSyncedSessions([]), 0);
    });

    test('skips a payload with no date or start_time', () async {
      final restored = await _svc.restoreSyncedSessions([
        {'exercises': <dynamic>[], 'duration_seconds': 60},
      ]);
      expect(restored, 0);
    });

    test('a corrupt local row does not block restoring the rest', () async {
      await _svc.saveSession(
        date: '2026-07-01',
        workoutType: 'A',
        durationSeconds: 60,
        succeeded: true,
        json: 'not valid json',
      );
      final restored = await _svc.restoreSyncedSessions([
        session('2026-07-17', '2026-07-17T09:48:34.338'),
      ]);
      expect(restored, 1);
    });
  });
}
