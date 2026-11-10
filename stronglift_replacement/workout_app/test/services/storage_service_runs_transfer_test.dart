@TestOn('vm')
library;

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/run_record.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/backup_service.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/services/tcx_codec.dart';

import 'storage_service_runs_fixtures.dart';

void main() {
  useRunsTransferSandbox();

  group('backup.json', () {
    test(
      'wipe the DB, restore: recorded runs and their points return',
      () async {
        await insertAll();
        final backup = await backupOnceItHolds(2);
        final saved = {
          for (final r in await svc.listRuns())
            if (r.track.source == RunSource.app)
              r.track.id: await svc.getRun(r.track.id),
        };
        expect(saved, hasLength(2));
        // RunnerUp history is reproducible from the PC: not duplicated here.
        expect(
          (backup['runs'] as List).map((r) => (r as Map)['source']).toSet(),
          {'app'},
        );
        final text = const JsonEncoder.withIndent('  ').convert(backup);
        expect(
          text.split('\n').length,
          lessThan(200),
          reason: 'points must stay one string per run, not one line per fix',
        );

        await freshInstall(); // the reinstall
        expect(await svc.listRuns(), isEmpty);
        await svc.restoreFromBackupIfNeeded();

        final restored = await svc.listRuns();
        expect(restored.map((r) => r.track.id).toSet(), saved.keys.toSet());
        for (final run in saved.values) {
          final back = (await svc.getRun(run!.track.id))!;
          expect(back.track.points, run.track.points);
          expect(back.track.points, isNotEmpty);
          expect(back.uploadState, run.uploadState);
          expect(back.tcxSha256, run.tcxSha256);
          expect(back.track.totalSeconds, run.track.totalSeconds);
          expect(back.track.distanceM, run.track.distanceM);
        }
      },
    );

    test('restoring twice stores nothing twice', () async {
      await insertAll();
      await backupOnceItHolds(2);
      await freshInstall();
      await svc.restoreFromBackupIfNeeded();
      final once = await svc.listRuns();

      await svc.restoreFromBackupIfNeeded();

      expect(await svc.listRuns(), hasLength(once.length));
    });

    test('a run-less fresh DB cannot overwrite a runs-only backup', () async {
      await insertAll();
      final before = await backupOnceItHolds(2);
      await freshInstall();

      await svc.setLastWorkoutType('A'); // triggers _backupNow
      await Future<void>.delayed(const Duration(milliseconds: 100));

      final after = await BackupService.instance.readBackup();
      expect(
        after!['runs'] as List,
        hasLength((before['runs'] as List).length),
      );
    });
  });

  test(
    'a run on a history-less DB cannot clobber a backup with history',
    () async {
      await BackupService.instance.export({
        'exercise_state': <Object?>[],
        'workout_history': [
          {
            'date': '2026-07-17',
            'workout_type': 'B',
            'duration_seconds': 6465,
            'succeeded': 1,
            'json': '{}',
          },
        ],
        'settings': <Object?>[],
      });
      final (name, xml, track) = tracks().firstWhere(
        (t) => t.$3.source == RunSource.app,
      );

      await svc.insertRun(
        track,
        tcxFilename: name,
        tcxSha256: tcxSha256(xml),
        uploadState: RunUploadState.pending,
      );
      await Future<void>.delayed(const Duration(milliseconds: 150));

      final after = await BackupService.instance.readBackup();
      expect(after!['workout_history'], hasLength(1));
    },
  );
}
