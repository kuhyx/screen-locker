@TestOn('vm')
library;

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/run_record.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/backup_service.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/services/tcx_codec.dart';

import '_runnerup_fake_dufs.dart';

StorageService get _svc => StorageService.instance;

/// The three fixtures, decoded: two app-made, one RunnerUp export.
List<(String, String, RunTrack)> _tracks() => [
  for (final e in fixtureTcx().entries)
    (
      e.key,
      utf8.decode(e.value),
      decodeTcx(utf8.decode(e.value), fileName: e.key),
    ),
];

Future<void> _insertAll() async {
  for (final (name, xml, track) in _tracks()) {
    final imported = track.source == RunSource.runnerupImport;
    await _svc.insertRun(
      track,
      tcxFilename: name,
      tcxSha256: tcxSha256(xml),
      uploadState: imported ? RunUploadState.never : RunUploadState.pending,
    );
  }
}

Future<void> _freshInstall() async {
  StorageService.resetForTesting();
  await StorageService.init();
}

Future<Map<String, dynamic>> _backupOnceItHolds(int runs) async {
  for (var i = 0; i < 150; i++) {
    final b = await BackupService.instance.readBackup();
    if (b != null && ((b['runs'] as List?)?.length ?? 0) >= runs) return b;
    await Future<void>.delayed(const Duration(milliseconds: 20));
  }
  fail('backup.json never held $runs run(s)');
}

void main() {
  late Directory tmp;

  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    tmp = Directory.systemTemp.createTempSync('runs_transfer');
    BackupService.baseDir = tmp.path;
    await _freshInstall();
  });

  tearDown(() {
    BackupService.baseDir = kBackupDir;
    tmp.deleteSync(recursive: true);
  });

  group('backup.json', () {
    test(
      'wipe the DB, restore: recorded runs and their points return',
      () async {
        await _insertAll();
        final backup = await _backupOnceItHolds(2);
        final saved = {
          for (final r in await _svc.listRuns())
            if (r.track.source == RunSource.app)
              r.track.id: await _svc.getRun(r.track.id),
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

        await _freshInstall(); // the reinstall
        expect(await _svc.listRuns(), isEmpty);
        await _svc.restoreFromBackupIfNeeded();

        final restored = await _svc.listRuns();
        expect(restored.map((r) => r.track.id).toSet(), saved.keys.toSet());
        for (final run in saved.values) {
          final back = (await _svc.getRun(run!.track.id))!;
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
      await _insertAll();
      await _backupOnceItHolds(2);
      await _freshInstall();
      await _svc.restoreFromBackupIfNeeded();
      final once = await _svc.listRuns();

      await _svc.restoreFromBackupIfNeeded();

      expect(await _svc.listRuns(), hasLength(once.length));
    });

    test('a run-less fresh DB cannot overwrite a runs-only backup', () async {
      await _insertAll();
      final before = await _backupOnceItHolds(2);
      await _freshInstall();

      await _svc.setLastWorkoutType('A'); // triggers _backupNow
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
      final (name, xml, track) = _tracks().firstWhere(
        (t) => t.$3.source == RunSource.app,
      );

      await _svc.insertRun(
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

  group('user export / merge-import', () {
    test(
      'round trip keeps every run and point; a re-import adds nothing',
      () async {
        await _insertAll();
        final originals = {
          for (final r in await _svc.listRuns())
            r.track.id: (await _svc.getRun(r.track.id))!,
        };
        final data =
            jsonDecode(jsonEncode(await _svc.exportData()))
                as Map<String, dynamic>;
        expect(data['version'], kExportVersion);
        expect(data['runs'], hasLength(3));

        await _freshInstall();
        final report = await _svc.importDataReport(data);

        expect(report.rows, greaterThanOrEqualTo(3));
        for (final run in originals.values) {
          final back = (await _svc.getRun(run.track.id))!;
          expect(back.track.points, run.track.points);
          expect(back.track.source, run.track.source);
          expect(back.uploadState, run.uploadState);
        }
        final again = await _svc.importDataReport(data);
        expect(again.rows, 0);
        expect(await _svc.listRuns(), hasLength(3));
      },
    );

    test('an old export without runs still imports', () async {
      final report = await _svc.importDataReport({
        'format': kExportFormat,
        'version': 2,
        'settings': <Object?>[],
      });
      expect(report.rows, 0);
      expect(await _svc.listRuns(), isEmpty);
    });

    test(
      'a runs entry that is not a list is skipped, the rest merges',
      () async {
        final report = await _svc.importDataReport({
          'settings': <Object?>[],
          'runs': 5,
        });
        expect(report.rows, 0);
      },
    );

    test('an export holding only runs is accepted; junk is not', () async {
      await _insertAll();
      final runs = (await _svc.exportData())['runs']! as List<dynamic>;
      await _freshInstall();
      expect((await _svc.importDataReport({'runs': runs})).rows, 3);
      await expectLater(
        _svc.importDataReport({'runs': 'nope'}),
        throwsFormatException,
      );
    });

    test(
      'bad entries are skipped, good ones kept, imports stay never',
      () async {
        await _insertAll();
        final good = ((await _svc.exportData())['runs']! as List<dynamic>)
            .cast<Map<String, Object?>>();
        await _freshInstall();
        final forged = {
          ...good.first,
          'source': 'runnerup_import',
          'upload_state': 'pending',
        };
        final clash = {...good[1], 'id': 'other-id'}; // same hash, new id
        final badPoints = {...good[2], 'points': 'not json'};
        final badSport = {...good[2], 'id': 'z', 'sport': 'Cycling'};
        final noId = {...good[2], 'id': ''};

        final report = await _svc.importDataReport({
          'runs': [forged, good[1], clash, badPoints, badSport, noId, 'str', 7],
        });

        expect(report.rows, 2);
        final stored = await _svc.listRuns();
        expect(stored, hasLength(2));
        final coerced = stored.firstWhere((r) => r.track.id == forged['id']);
        expect(coerced.track.source, RunSource.runnerupImport);
        expect(coerced.uploadState, RunUploadState.never);
      },
    );
  });
}
