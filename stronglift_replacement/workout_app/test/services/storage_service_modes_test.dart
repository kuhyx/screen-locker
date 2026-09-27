// Progression modes, the per-exercise warmup toggle, and the v3 -> v4
// schema upgrade that added both.
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/workout_plan.dart';
import 'package:workout_app/services/storage_service.dart';

StorageService get _svc => StorageService.instance;

final _yesterday = DateTime.now().subtract(const Duration(days: 1));

/// Builds a database exactly as a v3 install left it: the v3 schema, a
/// finished workout from today, and a workout in progress.
Future<void> _writeV3Database(String path) async {
  final db = await databaseFactory.openDatabase(
    path,
    options: OpenDatabaseOptions(
      version: 3,
      onCreate: (db, _) async {
        await db.execute(
          'CREATE TABLE exercise_state (name TEXT PRIMARY KEY, '
          'weight REAL NOT NULL, reps INTEGER NOT NULL, '
          'success_streak INTEGER NOT NULL DEFAULT 0, '
          'fail_streak INTEGER NOT NULL DEFAULT 0, max_weight REAL NOT NULL, '
          'success_threshold INTEGER NOT NULL DEFAULT 3, '
          'fail_threshold INTEGER NOT NULL DEFAULT 2)',
        );
        await db.execute(
          'CREATE TABLE workout_history (id INTEGER PRIMARY KEY '
          'AUTOINCREMENT, date TEXT NOT NULL, workout_type TEXT NOT NULL, '
          'duration_seconds INTEGER NOT NULL, succeeded INTEGER NOT NULL, '
          'json TEXT NOT NULL)',
        );
        await db.execute(
          'CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)',
        );
        await db.execute(
          'CREATE TABLE active_session (id INTEGER PRIMARY KEY '
          'CHECK (id = 1), json TEXT NOT NULL)',
        );
      },
    ),
  );
  for (final ex in [...workoutA, ...workoutB]) {
    await db.insert('exercise_state', {
      'name': ex.name,
      'weight': 17.5,
      'reps': 9,
      'success_streak': 2,
      'fail_streak': 1,
      'max_weight': ex.maxWeight,
      'success_threshold': 5,
      'fail_threshold': 4,
    }, conflictAlgorithm: ConflictAlgorithm.replace);
  }
  await db.insert('workout_history', {
    'date': '2026-09-27',
    'workout_type': 'A',
    'duration_seconds': 4000,
    'succeeded': 1,
    'json': '{"workoutType":"A"}',
  });
  await db.insert('settings', {'key': 'last_workout_type', 'value': 'A'});
  await db.insert('active_session', {'id': 1, 'json': jsonEncode(_session)});
  await db.close();
}

const _session = {
  'workoutType': 'B',
  'startTimeMs': 1790516739892,
  'tapped': [
    [true, true, true, true, true],
    [true, true, true, true, true],
    [true, true, true, true, false],
    [false, false, false],
  ],
  'doneReps': [
    [9, 9, 9, 9, 9],
    [12, 12, 12, 12, 12],
    [12, 12, 12, 12, 12],
    [31, 31, 31],
  ],
  'warmupTapped': [true, true, true, false],
};

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    StorageService.resetForTesting();
    await StorageService.init();
  });

  group('v3 -> v4 upgrade', () {
    late Directory dir;
    setUp(() async {
      dir = await Directory.systemTemp.createTemp('mw_v4');
      final file = p.join(dir.path, 'v3.db');
      await _writeV3Database(file);
      StorageService.resetForTesting(dbPath: file);
      await StorageService.init();
    });
    tearDown(() => dir.delete(recursive: true));

    test('keeps a workout in progress byte for byte', () async {
      expect(await _svc.loadActiveSession(), _session);
    });

    test("keeps today's finished workout and the history marker", () async {
      expect(await _svc.getLastWorkoutDate(), DateTime(2026, 9, 27));
      expect(await _svc.getNextWorkoutType(), 'B');
      expect(await _svc.looksFreshlyInstalled(), isFalse);
    });

    test('keeps progression and gives every row weight mode', () async {
      for (final ex in [...workoutA, ...workoutB]) {
        final s = (await _svc.getExerciseState(ex.name))!;
        expect((s.weight, s.reps, s.successStreak, s.failStreak), (
          17.5,
          9,
          2,
          1,
        ));
        expect((s.successThreshold, s.failThreshold), (5, 4));
        expect(s.mode, ProgressionMode.weight);
        expect((s.repsHigh, s.repsLow), (kDefaultRepsHigh, kDefaultRepsLow));
        // NULL column -> the plan's default: Situp stays warmup-free.
        expect(s.hasWarmup, ex.hasWarmup, reason: ex.name);
      }
    });
  });

  test('v4 -> v5 (the phone today) keeps settings and adds no pause', () async {
    final dir = await Directory.systemTemp.createTemp('mw_v5');
    addTearDown(() => dir.delete(recursive: true));
    final file = p.join(dir.path, 'v4.db');
    await _writeV3Database(file);
    // Upgrade to exactly v4 the way the v4 build did, and set a mode there.
    final v4 = await databaseFactory.openDatabase(
      file,
      options: OpenDatabaseOptions(
        version: 4,
        onUpgrade: (db, _, _) async {
          await db.execute(
            "ALTER TABLE exercise_state ADD COLUMN progression_mode TEXT "
            "NOT NULL DEFAULT 'weight'",
          );
          await db.execute(
            'ALTER TABLE exercise_state ADD COLUMN reps_high INTEGER '
            'NOT NULL DEFAULT 12',
          );
          await db.execute(
            'ALTER TABLE exercise_state ADD COLUMN reps_low INTEGER '
            'NOT NULL DEFAULT 6',
          );
          await db.execute(
            'ALTER TABLE exercise_state ADD COLUMN has_warmup INTEGER',
          );
        },
      ),
    );
    await v4.update('exercise_state', {
      'progression_mode': 'double',
      'has_warmup': 0,
    }, where: "name = 'Situp'");
    await v4.close();

    StorageService.resetForTesting(dbPath: file);
    await StorageService.init();
    final situp = (await _svc.getExerciseState('Situp'))!;
    expect(situp.mode, ProgressionMode.doubleProgression);
    expect(situp.hasWarmup, isFalse);
    expect(situp.pausedUntil, isNull);
    expect(await _svc.getLastWorkoutDate(), DateTime(2026, 9, 27));
  });

  group('setExerciseSettings', () {
    test('persists mode, rep range, warmup and thresholds', () async {
      final name = workoutA.first.name;
      final s = (await _svc.getExerciseState(name))!;
      await _svc.setExerciseSettings(
        s.copyWith(
          mode: ProgressionMode.doubleProgression,
          repsHigh: 15,
          repsLow: 8,
          hasWarmup: false,
          successThreshold: 1,
          failThreshold: 4,
        ),
      );
      final after = (await _svc.getExerciseState(name))!;
      expect(after.mode, ProgressionMode.doubleProgression);
      expect((after.repsHigh, after.repsLow), (15, 8));
      expect(after.hasWarmup, isFalse);
      expect((after.successThreshold, after.failThreshold), (1, 4));
      // The target itself is untouched until the next finished workout.
      expect((after.weight, after.reps), (s.weight, s.reps));
    });

    test('persists a pause and its resume', () async {
      final s = (await _svc.getExerciseState('Situp'))!;
      await _svc.setExerciseSettings(
        s.copyWith(pausedUntil: DateTime(2026, 10, 11)),
      );
      expect(
        (await _svc.getExerciseState('Situp'))!.pausedUntil,
        DateTime(2026, 10, 11),
      );
      await _svc.setExerciseSettings(s.copyWith(resume: true));
      expect((await _svc.getExerciseState('Situp'))!.pausedUntil, isNull);
    });

    test('reaches the workout through getCurrentExercises', () async {
      final name = workoutA.first.name;
      final s = (await _svc.getExerciseState(name))!;
      await _svc.setExerciseSettings(s.copyWith(hasWarmup: false));
      final exercises = await _svc.getCurrentExercises('A');
      expect(exercises.first.hasWarmup, isFalse);
      expect(exercises[1].hasWarmup, isTrue);
    });
  });

  group('applyProgression per mode', () {
    Future<ExerciseState> run(
      ProgressionMode mode, {
      required bool success,
      required int reps,
      DateTime? last,
    }) async {
      final name = workoutA.first.name;
      final s = (await _svc.getExerciseState(name))!;
      await _svc.setExerciseSettings(
        s.copyWith(mode: mode, successThreshold: 1, failThreshold: 1),
      );
      await _svc.setExerciseReps(name, reps);
      await _svc.setExerciseWeight(name, 10);
      await _svc.applyProgression(
        succeededExercises: {name: success},
        lastWorkoutDate: last ?? _yesterday,
      );
      return (await _svc.getExerciseState(name))!;
    }

    test('reps: success adds a rep', () async {
      final s = await run(ProgressionMode.reps, success: true, reps: 10);
      expect((s.weight, s.reps, s.successStreak), (10, 11, 0));
    });

    test('reps: failure removes a rep', () async {
      final s = await run(ProgressionMode.reps, success: false, reps: 10);
      expect((s.weight, s.reps, s.failStreak), (10, 9, 0));
    });

    test('double: success at n moves up in weight and back to m', () async {
      final s = await run(
        ProgressionMode.doubleProgression,
        success: true,
        reps: 12,
      );
      expect((s.weight, s.reps), (12.5, 6));
    });

    test('double: failure at m moves down in weight and up to n', () async {
      final s = await run(
        ProgressionMode.doubleProgression,
        success: false,
        reps: 6,
      );
      expect((s.weight, s.reps), (7.5, 12));
    });

    test('a week off is one regression step in the active mode', () async {
      final s = await run(
        ProgressionMode.reps,
        success: true,
        reps: 10,
        last: DateTime.now().subtract(const Duration(days: 9)),
      );
      expect((s.weight, s.reps, s.successStreak, s.failStreak), (10, 9, 0, 0));
    });
  });
}
