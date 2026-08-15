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
}
