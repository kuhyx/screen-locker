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
}
