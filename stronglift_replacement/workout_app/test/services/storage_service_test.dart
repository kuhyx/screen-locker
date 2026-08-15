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

  group('getNextWorkoutType', () {
    test('returns A when no workout has been done', () async {
      expect(await _svc.getNextWorkoutType(), 'A');
    });

    test('returns B after setting last type to A', () async {
      await _svc.setLastWorkoutType('A');
      expect(await _svc.getNextWorkoutType(), 'B');
    });

    test('returns A after setting last type to B', () async {
      await _svc.setLastWorkoutType('B');
      expect(await _svc.getNextWorkoutType(), 'A');
    });
  });

  // ── Active session ─────────────────────────────────────────────────────────

  group('active session', () {
    test('loadActiveSession returns null when empty', () async {
      expect(await _svc.loadActiveSession(), isNull);
    });

    test('saveActiveSession persists and loadActiveSession retrieves', () async {
      final data = {'workoutType': 'A', 'startTimeMs': 1000};
      await _svc.saveActiveSession(data);
      final loaded = await _svc.loadActiveSession();
      expect(loaded, isNotNull);
      expect(loaded!['workoutType'], 'A');
    });

    test('survives a full app-data wipe via the external mirror', () async {
      // Regression: `pm clear` (or an uninstall) wipes app-private SQLite,
      // which is where active_session lives — the user lost the exact set and
      // reps they were standing on mid-workout. The mirror must bring it back.
      final tmp = Directory.systemTemp.createTempSync('mw_active_wipe');
      BackupService.baseDirForTesting = tmp.path;
      addTearDown(() {
        BackupService.baseDirForTesting = kBackupDir;
        tmp.deleteSync(recursive: true);
      });

      await _svc.saveActiveSession({
        'workoutType': 'B',
        'tapped': [
          [true, true, false],
        ],
        'doneReps': [
          [5, 4, 0],
        ],
      });
      // Give the unawaited mirror write a turn to land.
      await Future<void>.delayed(Duration.zero);

      // Simulate the wipe: app-private DB gone, external mirror untouched.
      StorageService.resetForTesting();
      await StorageService.init();

      final recovered = await _svc.loadActiveSession();
      expect(recovered, isNotNull, reason: 'the in-progress set must survive');
      expect(recovered!['workoutType'], 'B');
      expect((recovered['doneReps'] as List).first, [5, 4, 0]);
      // And it re-seeded the table, so the next read needs no mirror.
      expect(await _svc.loadActiveSession(), isNotNull);
    });

    test('clearActiveSession also clears the mirror', () async {
      // Otherwise a finished workout would be resurrected on next launch.
      final tmp = Directory.systemTemp.createTempSync('mw_active_clear');
      BackupService.baseDirForTesting = tmp.path;
      addTearDown(() {
        BackupService.baseDirForTesting = kBackupDir;
        tmp.deleteSync(recursive: true);
      });

      await _svc.saveActiveSession({'workoutType': 'A'});
      await Future<void>.delayed(Duration.zero);
      await _svc.clearActiveSession();

      StorageService.resetForTesting();
      await StorageService.init();
      expect(await _svc.loadActiveSession(), isNull);
    });

    test('saveActiveSession replaces previous entry', () async {
      await _svc.saveActiveSession({'v': 1});
      await _svc.saveActiveSession({'v': 2});
      final loaded = await _svc.loadActiveSession();
      expect(loaded!['v'], 2);
    });

    test('clearActiveSession removes the entry', () async {
      await _svc.saveActiveSession({'x': 1});
      await _svc.clearActiveSession();
      expect(await _svc.loadActiveSession(), isNull);
    });
  });

  // ── Exercise state ─────────────────────────────────────────────────────────

  group('getExerciseState', () {
    test('returns state for seeded exercises', () async {
      final state = await _svc.getExerciseState(workoutA.first.name);
      expect(state, isNotNull);
      expect(state!.weight, workoutA.first.weight);
    });

    test('returns null for unknown exercise', () async {
      expect(await _svc.getExerciseState('Unknown Exercise'), isNull);
    });
  });

  group('getAllExerciseStates', () {
    test('returns states for all exercises in both plans', () async {
      final states = await _svc.getAllExerciseStates();
      final allNames = {...workoutA, ...workoutB}.map((e) => e.name).toSet();
      expect(states.map((s) => s.name).toSet(), equals(allNames));
    });
  });

  group('setExerciseThresholds', () {
    test('updates thresholds and verifies', () async {
      final name = workoutA.first.name;
      await _svc.setExerciseThresholds(
        name,
        successThreshold: 5,
        failThreshold: 3,
      );
      final state = await _svc.getExerciseState(name);
      expect(state!.successThreshold, 5);
      expect(state.failThreshold, 3);
    });
  });

  group('setExerciseReps', () {
    test('updates reps and resets streaks', () async {
      // Progression can only ever RAISE reps, so this is the only way to
      // correct a rep target a defaults re-seed set wrong.
      const name = 'Situp';
      await _svc.setExerciseReps(name, 31);
      final state = await _svc.getExerciseState(name);
      expect(state!.reps, 31);
      expect(state.successStreak, 0);
      expect(state.failStreak, 0);
    });

    test('can lower a rep target', () async {
      const name = 'Situp';
      await _svc.setExerciseReps(name, 25);
      expect((await _svc.getExerciseState(name))!.reps, 25);
    });
  });

  group('setExerciseWeight', () {
    test('updates weight and resets streaks', () async {
      final name = workoutA.first.name;
      await _svc.setExerciseWeight(name, 30.0);
      final state = await _svc.getExerciseState(name);
      expect(state!.weight, 30.0);
      expect(state.successStreak, 0);
      expect(state.failStreak, 0);
    });
  });

  group('getCurrentExercises', () {
    test('returns exercises with state-applied weights for A', () async {
      final exercises = await _svc.getCurrentExercises('A');
      expect(exercises.length, workoutA.length);
    });

    test('returns exercises for B', () async {
      final exercises = await _svc.getCurrentExercises('B');
      expect(exercises.length, workoutB.length);
    });
  });

  // ── Progression ────────────────────────────────────────────────────────────

  group('applyProgression', () {
    test('increments successStreak on success below threshold', () async {
      final name = workoutA.first.name;
      await _svc.setExerciseThresholds(
        name,
        successThreshold: 3,
        failThreshold: 2,
      );
      final before = await _svc.getExerciseState(name);
      await _svc.applyProgression(
        succeededExercises: {name: true},
        lastWorkoutDate: DateTime.now().subtract(const Duration(days: 1)),
      );
      final after = await _svc.getExerciseState(name);
      expect(after!.successStreak, (before!.successStreak + 1));
    });

    test('progresses weight when successStreak hits threshold', () async {
      final name = workoutA.first.name;
      await _svc.setExerciseThresholds(
        name,
        successThreshold: 1,
        failThreshold: 2,
      );
      final before = await _svc.getExerciseState(name);
      await _svc.applyProgression(
        succeededExercises: {name: true},
        lastWorkoutDate: DateTime.now().subtract(const Duration(days: 1)),
      );
      final after = await _svc.getExerciseState(name);
      // Weight should increase (if below maxWeight) or reps increase
      if (before!.weight < before.maxWeight) {
        expect(after!.weight, greaterThan(before.weight));
      } else {
        expect(after!.reps, greaterThanOrEqualTo(before.reps + 1));
      }
    });

    test('increments failStreak on failure below threshold', () async {
      final name = workoutA.first.name;
      await _svc.setExerciseThresholds(
        name,
        successThreshold: 3,
        failThreshold: 3,
      );
      final before = await _svc.getExerciseState(name);
      await _svc.applyProgression(
        succeededExercises: {name: false},
        lastWorkoutDate: DateTime.now().subtract(const Duration(days: 1)),
      );
      final after = await _svc.getExerciseState(name);
      expect(after!.failStreak, (before!.failStreak + 1));
    });

    test('decreases weight when failStreak hits threshold', () async {
      final name = workoutA.first.name;
      await _svc.setExerciseThresholds(
        name,
        successThreshold: 3,
        failThreshold: 1,
      );
      final before = await _svc.getExerciseState(name);
      await _svc.applyProgression(
        succeededExercises: {name: false},
        lastWorkoutDate: DateTime.now().subtract(const Duration(days: 1)),
      );
      final after = await _svc.getExerciseState(name);
      expect(after!.weight, lessThanOrEqualTo(before!.weight));
    });

    test('reduces weight after long break (> 7 days)', () async {
      final name = workoutA.first.name;
      await _svc.setExerciseWeight(name, 20.0);
      final before = await _svc.getExerciseState(name);
      await _svc.applyProgression(
        succeededExercises: {name: true},
        lastWorkoutDate: DateTime.now().subtract(const Duration(days: 10)),
      );
      final after = await _svc.getExerciseState(name);
      expect(after!.weight, lessThan(before!.weight));
    });

    test('skips unknown exercise gracefully', () async {
      await _svc.applyProgression(
        succeededExercises: {'Ghost Exercise': true},
        lastWorkoutDate: DateTime.now().subtract(const Duration(days: 1)),
      );
      // No exception thrown — that's the test.
    });
  });

  // ── History ────────────────────────────────────────────────────────────────

  group('workout history', () {
    test('getLastWorkoutDate returns null when empty', () async {
      expect(await _svc.getLastWorkoutDate(), isNull);
    });

    test('saveSession and getLastWorkoutDate', () async {
      await _svc.saveSession(
        date: '2024-06-01',
        workoutType: 'A',
        durationSeconds: 2700,
        succeeded: true,
        json: '{}',
      );
      final date = await _svc.getLastWorkoutDate();
      expect(date, isNotNull);
      expect(date!.year, 2024);
    });

    test('getWorkoutHistory returns rows newest first', () async {
      await _svc.saveSession(
        date: '2024-06-01',
        workoutType: 'A',
        durationSeconds: 1000,
        succeeded: true,
        json: '{}',
      );
      await _svc.saveSession(
        date: '2024-06-02',
        workoutType: 'B',
        durationSeconds: 1200,
        succeeded: false,
        json: '{}',
      );
      final rows = await _svc.getWorkoutHistory(limit: 10);
      expect(rows.first['date'], '2024-06-02');
    });

    test('getWorkoutHistory respects limit', () async {
      for (var i = 0; i < 5; i++) {
        await _svc.saveSession(
          date: '2024-0$i-01',
          workoutType: 'A',
          durationSeconds: 1000,
          succeeded: true,
          json: '{}',
        );
      }
      final rows = await _svc.getWorkoutHistory(limit: 3);
      expect(rows.length, lessThanOrEqualTo(3));
    });

    test('getAllWorkoutDates returns distinct dates', () async {
      await _svc.saveSession(
        date: '2024-06-01',
        workoutType: 'A',
        durationSeconds: 1000,
        succeeded: true,
        json: '{}',
      );
      await _svc.saveSession(
        date: '2024-06-01',
        workoutType: 'B',
        durationSeconds: 1200,
        succeeded: false,
        json: '{}',
      );
      final dates = await _svc.getAllWorkoutDates();
      expect(dates.where((d) => d == '2024-06-01').length, 1);
    });
  });

  // ── Reset to defaults ──────────────────────────────────────────────────────

  group('resetExerciseToDefaults', () {
    test('restores default weight and thresholds', () async {
      final name = workoutA.first.name;
      await _svc.setExerciseWeight(name, 99.0);
      await _svc.resetExerciseToDefaults(name);
      final state = await _svc.getExerciseState(name);
      expect(state!.weight, workoutA.first.weight);
      expect(state.successThreshold, 3);
      expect(state.failThreshold, 2);
    });

    test('throws for unknown exercise name', () async {
      await expectLater(
        _svc.resetExerciseToDefaults('Ghost Exercise'),
        throwsException,
      );
    });
  });

  // ── init is idempotent ─────────────────────────────────────────────────────

  test('init returns same instance when called twice', () async {
    final a = await StorageService.init();
    final b = await StorageService.init();
    expect(identical(a, b), isTrue);
  });

  // ── Schema migration (v1 → v3) ──────────────────────────────────────────────

  test('migrates a v1 database up to v3 on open', () async {
    // A v1 DB predates the threshold columns and the settings/active_session
    // tables — build one on disk, then open it through StorageService (v3) so
    // _migrateSchema runs both the <2 and <3 upgrade blocks.
    final dir = await Directory.systemTemp.createTemp('mw_migrate');
    final dbFile = p.join(dir.path, 'old.db');
    final oldDb = await databaseFactory.openDatabase(
      dbFile,
      options: OpenDatabaseOptions(
        version: 1,
        onCreate: (db, _) async {
          await db.execute(
            'CREATE TABLE exercise_state ('
            'name TEXT PRIMARY KEY, weight REAL NOT NULL, reps INTEGER NOT NULL, '
            'success_streak INTEGER NOT NULL DEFAULT 0, '
            'fail_streak INTEGER NOT NULL DEFAULT 0, max_weight REAL NOT NULL)',
          );
        },
      ),
    );
    await oldDb.close();

    StorageService.resetForTesting(dbPath: dbFile);
    await StorageService.init();

    // <3 block created the settings table (getNextWorkoutType reads it) …
    expect(await _svc.getNextWorkoutType(), 'A');
    // … and the <2 block added the threshold columns (defaulted to 3/2).
    final st = await _svc.getExerciseState(workoutA.first.name);
    expect(st, isNotNull);
    expect(st!.successThreshold, 3);
    expect(st.failThreshold, 2);

    await dir.delete(recursive: true);
  });

  // ── Progression at the weight cap ───────────────────────────────────────────

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

  group('_backupNow clobber guard', () {
    late Directory tmp;

    setUp(() {
      tmp = Directory.systemTemp.createTempSync('mw_clobber');
      BackupService.baseDirForTesting = tmp.path;
    });

    tearDown(() {
      BackupService.baseDirForTesting = kBackupDir;
      tmp.deleteSync(recursive: true);
    });

    test('refuses to overwrite a real backup from a history-less DB', () async {
      // A good backup: real progression and a real session.
      await BackupService.instance.export({
        'exercise_state': [
          {
            'name': 'Situp',
            'weight': 10.0,
            'reps': 31,
            'success_streak': 2,
            'fail_streak': 0,
            'max_weight': 10.0,
            'success_threshold': 5,
            'fail_threshold': 2,
          },
        ],
        'workout_history': [
          {
            'date': '2026-07-17',
            'workout_type': 'B',
            'duration_seconds': 6465,
            'succeeded': 1,
            'json': '{}',
          },
        ],
        'settings': [
          {'key': 'last_workout_type', 'value': 'B'},
        ],
      });

      // The DB here is freshly seeded: defaults, and no history at all.
      // Any write triggers _backupNow(), which used to export over the good
      // backup. setExerciseWeight is one such write.
      await _svc.setExerciseWeight('Situp', 10.0);
      // Let the unawaited _backupNow() settle.
      await Future<void>.delayed(const Duration(milliseconds: 50));

      final backup = await BackupService.instance.readBackup();
      final history = backup!['workout_history'] as List;
      final exercises = backup['exercise_state'] as List;

      // The good backup must still be intact.
      expect(history.length, 1, reason: 'real session was clobbered');
      expect((history.first as Map)['date'], '2026-07-17');
      final situp = exercises.firstWhere(
        (e) => (e as Map)['name'] == 'Situp',
      ) as Map;
      expect(situp['reps'], 31, reason: 'progression reps were clobbered');
    });

    test('still writes the backup once the DB has real history', () async {
      await _svc.saveSession(
        date: '2026-08-10',
        workoutType: 'B',
        durationSeconds: 10313,
        succeeded: true,
        json: '{}',
      );
      await Future<void>.delayed(const Duration(milliseconds: 50));

      final backup = await BackupService.instance.readBackup();
      expect(backup, isNotNull, reason: 'a real DB must still back itself up');
      expect((backup!['workout_history'] as List).length, 1);
    });
  });

  group('restoreFromBackupIfNeeded', () {
    late Directory tmp;

    setUp(() {
      tmp = Directory.systemTemp.createTempSync('mw_restore');
      BackupService.baseDirForTesting = tmp.path;
    });

    tearDown(() {
      BackupService.baseDirForTesting = kBackupDir;
      tmp.deleteSync(recursive: true);
    });

    test('returns early and does not restore when the DB has data', () async {
      await _svc.saveSession(
        date: '2026-07-10',
        workoutType: 'A',
        durationSeconds: 60,
        succeeded: true,
        json: '{}',
      );
      // A backup that would add a second history row if (wrongly) applied.
      await BackupService.instance.export({
        'workout_history': [
          {
            'date': '2000-01-01',
            'workout_type': 'B',
            'duration_seconds': 1,
            'succeeded': 0,
            'json': '{}',
          },
        ],
      });

      await _svc.restoreFromBackupIfNeeded();

      // Early-return path: existing history is untouched, backup ignored.
      final hist = await _svc.getWorkoutHistory();
      expect(hist.length, 1);
      expect(hist.first['date'], '2026-07-10');
    });

    test('restores exercise_state, history and settings when empty', () async {
      await BackupService.instance.export({
        'exercise_state': [
          {
            'name': 'Dumbbell Lunge',
            'weight': 42.5,
            'reps': 9,
            'success_streak': 0,
            'fail_streak': 0,
            'max_weight': 100.0,
            'success_threshold': 3,
            'fail_threshold': 2,
          },
        ],
        'workout_history': [
          {
            'date': '2026-07-01',
            'workout_type': 'A',
            'duration_seconds': 120,
            'succeeded': 1,
            'json': '{}',
          },
        ],
        'settings': [
          {'key': 'last_workout_type', 'value': 'A'},
        ],
      });

      await _svc.restoreFromBackupIfNeeded();

      // Settings restored: last was A → next is B.
      expect(await _svc.getNextWorkoutType(), 'B');
      // History restored.
      final hist = await _svc.getWorkoutHistory();
      expect(hist.length, 1);
      expect(hist.first['date'], '2026-07-01');
      // Exercise state overwritten from the backup.
      final st = await _svc.getExerciseState('Dumbbell Lunge');
      expect(st!.weight, 42.5);
    });

    test('does nothing when the DB is empty and no backup exists', () async {
      // No export() call → readBackup returns null → early return after the
      // has-data check.
      await _svc.restoreFromBackupIfNeeded();
      expect(await _svc.getWorkoutHistory(), isEmpty);
    });
  });

  // ── Last-sync timestamp (drives the home screen's status card) ─────────────

  group('last synced at', () {
    test('is null before a sync has ever succeeded', () async {
      expect(await _svc.getLastSyncedAt(), isNull);
    });

    test('round-trips the time a sync succeeded', () async {
      final at = DateTime(2026, 8, 15, 18, 30);
      await _svc.markSyncedNow(at);
      expect(await _svc.getLastSyncedAt(), at);
    });

    test('defaults to now when no time is given', () async {
      final before = DateTime.now().subtract(const Duration(seconds: 1));
      await _svc.markSyncedNow();
      final stored = await _svc.getLastSyncedAt();
      expect(stored, isNotNull);
      expect(stored!.isAfter(before), isTrue);
    });

    test('a corrupt stored value reads as never-synced, loudly', () async {
      // Seed a garbage timestamp directly: getLastSyncedAt must not throw,
      // and must say why rather than silently showing the nag card forever.
      final dir = await Directory.systemTemp.createTemp('mw_badstamp');
      final dbFile = p.join(dir.path, 'bad.db');
      StorageService.resetForTesting(dbPath: dbFile);
      await StorageService.init();
      await _svc.markSyncedNow(DateTime(2026, 8, 15));

      final db = await databaseFactory.openDatabase(dbFile);
      await db.update(
        'settings',
        {'value': 'not-a-timestamp'},
        where: 'key = ?',
        whereArgs: ['last_synced_at'],
      );
      await db.close();

      StorageService.resetForTesting(dbPath: dbFile);
      await StorageService.init();
      expect(await _svc.getLastSyncedAt(), isNull);
    });
  });
}
