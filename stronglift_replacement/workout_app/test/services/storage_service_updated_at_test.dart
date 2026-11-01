import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/workout_plan.dart';
import 'package:workout_app/services/storage_service.dart';

StorageService get _svc => StorageService.instance;

Future<List<Map<String, dynamic>>> _rows(String table) async =>
    ((await _svc.exportData())[table] as List).cast<Map<String, dynamic>>();

Future<int> _stamp(String table, String idColumn, String id) async {
  final row = (await _rows(table)).firstWhere((r) => r[idColumn] == id);
  return row['updated_at']! as int;
}

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  test('v7 -> v8 backfills updated_at with 0 on existing rows', () async {
    final dir = await Directory.systemTemp.createTemp('mw_v8');
    addTearDown(() => dir.delete(recursive: true));
    final path = p.join(dir.path, 'v7.db');
    final old = await databaseFactory.openDatabase(
      path,
      options: OpenDatabaseOptions(
        version: 7,
        onCreate: (db, _) async {
          await db.execute(
            'CREATE TABLE exercise_state (name TEXT PRIMARY KEY, '
            'weight REAL NOT NULL, reps INTEGER NOT NULL, '
            'success_streak INTEGER NOT NULL DEFAULT 0, '
            'fail_streak INTEGER NOT NULL DEFAULT 0, '
            'max_weight REAL NOT NULL, '
            'success_threshold INTEGER NOT NULL DEFAULT 3, '
            'fail_threshold INTEGER NOT NULL DEFAULT 2, '
            "progression_mode TEXT NOT NULL DEFAULT 'weight', "
            'reps_high INTEGER NOT NULL DEFAULT 12, '
            'reps_low INTEGER NOT NULL DEFAULT 8, has_warmup INTEGER, '
            'paused_until TEXT, '
            'rest_success_secs INTEGER NOT NULL DEFAULT 120, '
            'rest_fail_secs INTEGER NOT NULL DEFAULT 180, '
            'rest_warmup_secs INTEGER NOT NULL DEFAULT 60)',
          );
          await db.execute(
            'CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)',
          );
          await db.execute(
            'CREATE TABLE active_session (id INTEGER PRIMARY KEY, '
            'json TEXT NOT NULL)',
          );
          await db.execute(
            'CREATE TABLE workout_history (id INTEGER PRIMARY KEY '
            'AUTOINCREMENT, date TEXT NOT NULL, workout_type TEXT NOT NULL, '
            'duration_seconds INTEGER NOT NULL, succeeded INTEGER NOT NULL, '
            'json TEXT NOT NULL)',
          );
          await db.execute(
            'CREATE TABLE progression_events (id INTEGER PRIMARY KEY '
            'AUTOINCREMENT, at TEXT NOT NULL, exercise TEXT NOT NULL, '
            'kind TEXT NOT NULL, source TEXT NOT NULL, '
            'from_weight REAL NOT NULL, from_reps INTEGER NOT NULL, '
            'to_weight REAL NOT NULL, to_reps INTEGER NOT NULL)',
          );
          await db.insert('exercise_state', {
            'name': workoutA.first.name,
            'weight': 61.5,
            'reps': 5,
            'max_weight': 100.0,
          });
          await db.insert('settings', {
            'key': 'last_workout_type',
            'value': 'B',
          });
        },
      ),
    );
    await old.close();

    StorageService.resetForTesting(dbPath: path);
    await StorageService.init();

    final name = workoutA.first.name;
    expect(await _stamp('exercise_state', 'name', name), 0);
    expect(await _stamp('settings', 'key', 'last_workout_type'), 0);
    // Data survived, seeded rows are 0 too (a default is not an edit).
    expect((await _svc.getExerciseState(name))!.weight, 61.5);
    for (final row in await _rows('exercise_state')) {
      expect(row['updated_at'], 0);
    }
  });

  group('every write path stamps updated_at with now', () {
    late String name;
    late int before;

    setUp(() async {
      StorageService.resetForTesting();
      await StorageService.init();
      name = workoutA.first.name;
      before = DateTime.now().toUtc().millisecondsSinceEpoch;
    });

    Future<void> expectStamped(Future<void> Function() write) async {
      expect(await _stamp('exercise_state', 'name', name), 0);
      await write();
      expect(
        await _stamp('exercise_state', 'name', name),
        greaterThanOrEqualTo(before),
      );
    }

    test(
      'setExerciseWeight',
      () => expectStamped(() => _svc.setExerciseWeight(name, 50)),
    );
    test(
      'setExerciseReps',
      () => expectStamped(() => _svc.setExerciseReps(name, 6)),
    );
    test(
      'setExerciseThresholds',
      () => expectStamped(
        () => _svc.setExerciseThresholds(
          name,
          successThreshold: 4,
          failThreshold: 3,
        ),
      ),
    );
    test(
      'setExerciseSettings',
      () => expectStamped(() async {
        final s = (await _svc.getExerciseState(name))!;
        await _svc.setExerciseSettings(s.copyWith(hasWarmup: false));
      }),
    );
    test(
      'replaceExerciseState',
      () => expectStamped(() async {
        final s = (await _svc.getExerciseState(name))!;
        await _svc.replaceExerciseState(s.copyWith(weight: 33));
      }),
    );
    test(
      'resetExerciseToDefaults',
      () => expectStamped(() => _svc.resetExerciseToDefaults(name)),
    );
    test(
      'manualDeload',
      () => expectStamped(() async {
        await _svc.manualDeload(name, source: DeloadSource.settings);
      }),
    );
    test(
      'applyProgression',
      () => expectStamped(
        () => _svc.applyProgression(
          succeededExercises: {name: true},
          lastWorkoutDate: DateTime.now(),
        ),
      ),
    );
    test('settings writes', () async {
      await _svc.setLastWorkoutType('A');
      expect(
        await _stamp('settings', 'key', 'last_workout_type'),
        greaterThanOrEqualTo(before),
      );
    });
  });
}
