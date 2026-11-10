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

StorageService get svc => StorageService.instance;

/// The three fixtures, decoded: two app-made, one RunnerUp export.
List<(String, String, RunTrack)> tracks() => [
  for (final e in fixtureTcx().entries)
    (
      e.key,
      utf8.decode(e.value),
      decodeTcx(utf8.decode(e.value), fileName: e.key),
    ),
];

Future<void> insertAll() async {
  for (final (name, xml, track) in tracks()) {
    final imported = track.source == RunSource.runnerupImport;
    await svc.insertRun(
      track,
      tcxFilename: name,
      tcxSha256: tcxSha256(xml),
      uploadState: imported ? RunUploadState.never : RunUploadState.pending,
    );
  }
}

Future<void> freshInstall() async {
  StorageService.resetForTesting();
  await StorageService.init();
}

Future<Map<String, dynamic>> backupOnceItHolds(int runs) async {
  for (var i = 0; i < 150; i++) {
    final b = await BackupService.instance.readBackup();
    if (b != null && ((b['runs'] as List?)?.length ?? 0) >= runs) return b;
    await Future<void>.delayed(const Duration(milliseconds: 20));
  }
  fail('backup.json never held $runs run(s)');
}

/// A fresh in-memory database and a throwaway backup directory per test.
void useRunsTransferSandbox() {
  late Directory tmp;

  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    tmp = Directory.systemTemp.createTempSync('runs_transfer');
    BackupService.baseDir = tmp.path;
    await freshInstall();
  });

  tearDown(() {
    BackupService.baseDir = kBackupDir;
    tmp.deleteSync(recursive: true);
  });
}
