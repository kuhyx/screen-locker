import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/services/backup_service.dart';
import 'package:workout_app/services/storage_service.dart';

import '_deload_test_fixtures.dart';

StorageService get _svc => StorageService.instance;

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  late Directory dir;

  setUp(() async {
    dir = await Directory.systemTemp.createTemp('deload_persist');
    BackupService.baseDir = p.join(dir.path, 'backup');
  });

  tearDown(() async {
    BackupService.baseDir = kBackupDir;
    StorageService.resetForTesting();
    await dir.delete(recursive: true);
  });

  /// Opens the DB at [path] through StorageService, then a second raw handle.
  Future<Database> openBoth(String path) async {
    StorageService.resetForTesting(dbPath: path);
    await StorageService.init();
    final raw = await databaseFactory.openDatabase(path);
    return raw;
  }

  Map<String, Object?> eventRow({String at = '2026-10-01T08:00:00.000'}) => {
    'at': at,
    'exercise': 'Deload Lift',
    'kind': kManualDeloadKind,
    'source': 'settings',
    'from_weight': 100.0,
    'from_reps': 5,
    'to_weight': 97.5,
    'to_reps': 5,
  };

  test('v6 database migrates to v7 with an empty progression_events', () async {
    final path = p.join(dir.path, 'v6.db');
    final old = await databaseFactory.openDatabase(
      path,
      options: OpenDatabaseOptions(
        version: 6,
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
            'reps_low INTEGER NOT NULL DEFAULT 6, has_warmup INTEGER, '
            'paused_until TEXT, '
            'rest_success_secs INTEGER NOT NULL DEFAULT 180, '
            'rest_fail_secs INTEGER NOT NULL DEFAULT 300, '
            'rest_warmup_secs INTEGER NOT NULL DEFAULT 180)',
          );
          await db.execute(
            'CREATE TABLE workout_history (id INTEGER PRIMARY KEY '
            'AUTOINCREMENT, date TEXT NOT NULL, workout_type TEXT NOT NULL, '
            'duration_seconds INTEGER NOT NULL, succeeded INTEGER NOT NULL, '
            'json TEXT NOT NULL)',
          );
          await db.execute(
            'CREATE TABLE settings (key TEXT PRIMARY KEY, '
            'value TEXT NOT NULL)',
          );
          await db.execute(
            'CREATE TABLE active_session (id INTEGER PRIMARY KEY '
            'CHECK (id = 1), json TEXT NOT NULL)',
          );
          await db.insert('exercise_state', {
            'name': 'Deload Lift',
            'weight': 42.5,
            'reps': 7,
            'max_weight': 100.0,
          });
        },
      ),
    );
    await old.close();

    StorageService.resetForTesting(dbPath: path);
    await StorageService.init();

    expect(await _svc.getProgressionEvents(), isEmpty);
    // The pre-existing row survived and the new table is writable by deload.
    final kept = (await _svc.getExerciseState('Deload Lift'))!;
    expect((kept.weight, kept.reps), (42.5, 7));
    final r = await _svc.manualDeload(
      'Deload Lift',
      source: DeloadSource.settings,
    );
    expect(r.applied, isTrue);
    expect(await _svc.getProgressionEvents(), hasLength(1));
  });

  test('a row with an unparsable timestamp is skipped, not fatal', () async {
    final raw = await openBoth(p.join(dir.path, 'corrupt.db'));
    await raw.insert('progression_events', eventRow(at: 'last tuesday'));
    await raw.insert('progression_events', eventRow());
    await raw.close();

    final events = await _svc.getProgressionEvents();
    expect(events, hasLength(1));
    expect(events.single.at, DateTime(2026, 10, 1, 8));
  });

  test('refuses and logs nothing if the row vanishes mid-deload', () async {
    final raw = await openBoth(p.join(dir.path, 'vanish.db'));
    await _svc.replaceExerciseState(deloadState());
    // RAISE(IGNORE) makes the UPDATE touch 0 rows, as a concurrent delete
    // between the read and the transaction would.
    await raw.execute(
      'CREATE TRIGGER skip_update BEFORE UPDATE ON exercise_state '
      'BEGIN SELECT RAISE(IGNORE); END',
    );

    final r = await _svc.manualDeload(
      'Deload Lift',
      source: DeloadSource.workout,
    );
    expect(r.applied, isFalse);
    expect(r.reason, contains('disappeared from exercise_state'));
    expect(await raw.query('progression_events'), isEmpty);
    await raw.close();
  });

  group('backup', () {
    Future<Map<String, dynamic>> backupWithEvents(int count) async {
      // _backupNow is fire-and-forget; poll until it has landed.
      for (var i = 0; i < 100; i++) {
        final b = await BackupService.instance.readBackup();
        final events = (b?['progression_events'] as List?) ?? const [];
        if (events.length == count) return b!;
        await Future<void>.delayed(const Duration(milliseconds: 20));
      }
      fail('backup never reached $count progression_events');
    }

    test('events round-trip through backup and restore', () async {
      StorageService.resetForTesting();
      await StorageService.init();
      await _svc.replaceExerciseState(deloadState());
      await _svc.manualDeload('Deload Lift', source: DeloadSource.settings);
      final original = (await _svc.getProgressionEvents()).single;
      await backupWithEvents(1);

      // A reinstall: brand-new empty DB, then restore from the backup file.
      StorageService.resetForTesting();
      await StorageService.init();
      expect(await _svc.getProgressionEvents(), isEmpty);
      await _svc.restoreFromBackupIfNeeded();

      final restored = (await _svc.getProgressionEvents()).single;
      expect(restored.at, original.at);
      expect(
        (restored.exercise, restored.kind, restored.source),
        ('Deload Lift', 'manual_deload', 'settings'),
      );
      expect((restored.fromWeight, restored.toWeight), (100.0, 97.5));
      expect((restored.fromReps, restored.toReps), (5, 5));
      final st = (await _svc.getExerciseState('Deload Lift'))!;
      expect(st.weight, 97.5);
    });

    test('a pre-v7 backup without the key still restores', () async {
      Directory(BackupService.baseDir).createSync(recursive: true);
      File(p.join(BackupService.baseDir, 'backup.json')).writeAsStringSync(
        jsonEncode({
          'exercise_state': <Object>[],
          'workout_history': <Object>[],
          'settings': <Object>[],
        }),
      );
      StorageService.resetForTesting();
      await StorageService.init();
      await _svc.restoreFromBackupIfNeeded();
      expect(await _svc.getProgressionEvents(), isEmpty);
    });
  });
}
