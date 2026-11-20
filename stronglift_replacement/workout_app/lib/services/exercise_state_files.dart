/// The files around the one-time gap deload backfill: its pre-cut export
/// and the restore file `scripts/restore_exercise_state.py` pushes back.
///
/// Both live in the app's external files dir
/// (`/sdcard/Android/data/<package>/files`), the one place `adb` can reach on
/// a release build without storage permission. The export is also written
/// to the internal support dir, a second copy that survives a cleared
/// external dir.
///
/// The restore goes through the phone's own stamped import, not Firebase:
/// after its first reconcile the phone never pulls progression again (local
/// wins), so a PC-side Firebase write would never land and be overwritten
/// by the next push.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:developer';
import 'dart:io';

import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:workout_app/services/progression_sync_service.dart';
import 'package:workout_app/services/storage_service.dart';

/// File name of the pre-cut `exercise_state` export.
const String kDeloadExportFileName = 'exercise_state_pre_gap_deload.json';

/// File name the restore script pushes.
const String kRestoreFileName = 'restore_exercise_state.json';

/// What [ExerciseStateFiles.importRestoreFile] did.
class RestoreOutcome {
  /// Creates an outcome.
  const RestoreOutcome({required this.rows, required this.reason});

  /// Rows the import wrote; 0 when no file was there or it was unusable.
  final int rows;

  /// Why, as a sentence.
  final String reason;
}

// coverage:ignore-start
// Android-only plugin calls; the suite injects directories instead.
Future<List<Directory>> _defaultExportDirs() async => [
  await getApplicationSupportDirectory(),
  if (Platform.isAndroid) ?await getExternalStorageDirectory(),
];

Future<Directory?> _defaultRestoreDir() async =>
    Platform.isAndroid ? await getExternalStorageDirectory() : null;
// coverage:ignore-end

/// Writes the backfill export and imports a pushed restore file.
class ExerciseStateFiles {
  /// Creates the helper; the arguments are test seams.
  ExerciseStateFiles({
    Future<List<Directory>> Function()? exportDirs,
    Future<Directory?> Function()? restoreDir,
  }) : _exportDirs = exportDirs ?? _defaultExportDirs,
       _restoreDir = restoreDir ?? _defaultRestoreDir;

  final Future<List<Directory>> Function() _exportDirs;
  final Future<Directory?> Function() _restoreDir;

  /// Writes [json] to every export dir. Throws when none could be written,
  /// which stops the backfill before it cuts anything.
  Future<void> writeDeloadExport(String json) async {
    var written = 0;
    final failures = <String>[];
    for (final dir in await _exportDirs()) {
      try {
        await dir.create(recursive: true);
        await File(p.join(dir.path, kDeloadExportFileName)).writeAsString(json);
        written++;
        log('ExerciseStateFiles: pre-deload export saved in ${dir.path}');
      } on FileSystemException catch (error) {
        failures.add('${dir.path}: $error');
        log(
          'ExerciseStateFiles: pre-deload export NOT saved in ${dir.path} '
          '($error).',
          level: 900,
        );
      }
    }
    if (written == 0) {
      throw FileSystemException(
        'no copy of the pre-deload export could be written: '
        '${failures.isEmpty ? 'no export directory' : failures.join('; ')}',
      );
    }
  }

  /// Imports [kRestoreFileName] if the restore script pushed one, then
  /// renames it so the next launch does not import it again.
  Future<RestoreOutcome> importRestoreFile() async {
    final dir = await _restoreDir();
    if (dir == null) {
      return const RestoreOutcome(
        rows: 0,
        reason: 'no external files dir on this platform',
      );
    }
    final file = File(p.join(dir.path, kRestoreFileName));
    if (!file.existsSync()) {
      return const RestoreOutcome(rows: 0, reason: 'no restore file pushed');
    }
    final ImportReport report;
    try {
      final data = jsonDecode(await file.readAsString());
      report = await StorageService.instance.importDataReport(
        data as Map<String, dynamic>,
      );
    } on Object catch (error) {
      final reason =
          'restore file ${file.path} is not a workout_app export ($error); '
          'left in place, nothing restored';
      log('ExerciseStateFiles: $reason', level: 1000);
      return RestoreOutcome(rows: 0, reason: reason);
    }
    final done = '${file.path}.done-${DateTime.now().millisecondsSinceEpoch}';
    await file.rename(done);
    final reason =
        'restore file imported ${report.rows} row(s); kept as $done';
    log('ExerciseStateFiles: $reason', level: 900);
    return RestoreOutcome(rows: report.rows, reason: reason);
  }
}

// coverage:ignore-start
// Launch-path glue: both halves are tested on their own
// (exercise_state_files_test, storage_service_gap_deload_test).
/// Imports a pushed restore file, then runs the one-time gap deload
/// backfill (stamped, so later launches skip it), and pushes what changed.
Future<void> repairProgression() async {
  final files = ExerciseStateFiles();
  final restore = await files.importRestoreFile();
  log('WorkoutApp: ${restore.reason}');
  final backfill = await StorageService.instance.runGapDeloadBackfill(
    writeExport: files.writeDeloadExport,
  );
  log('WorkoutApp: ${backfill.reason}');
  if (restore.rows > 0 || backfill.deloads.isNotEmpty) {
    unawaited(
      ProgressionSyncService().pushProgression().then((r) {
        if (!r.changed) {
          log('Repaired progression not synced: ${r.reason}', level: 1000);
        }
      }),
    );
  }
}
// coverage:ignore-end
