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
