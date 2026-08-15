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
}
