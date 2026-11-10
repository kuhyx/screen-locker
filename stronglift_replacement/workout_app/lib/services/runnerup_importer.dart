/// One-time import of the RunnerUp history into the app's `runs` table.
///
/// Imported runs are display-only: [RunSource.runnerupImport] with
/// [RunUploadState.never]. Nothing here ever PUTs a `.tcx` anywhere; the only
/// write to the PC is the dotfile marker (see [kImportMarkerPath]) that tells
/// the PC the import finished.
library;

import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:workout_app/models/run_record.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/sandbox/sandbox.dart';
import 'package:workout_app/sandbox/sandbox_log.dart';
import 'package:workout_app/services/backup_service.dart';
import 'package:workout_app/services/dufs_credentials.dart';
import 'package:workout_app/services/runnerup_dav.dart';
import 'package:workout_app/services/runnerup_import_state.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/services/tcx_codec.dart';

export 'package:workout_app/services/runnerup_import_state.dart';

/// Imports the RunnerUp history once, on app start.
class RunnerUpImporter {
  /// Creates an importer; every collaborator can be replaced in tests.
  RunnerUpImporter({
    http.Client? client,
    Future<DufsCredentials?> Function()? loadLogin,
    Future<bool> Function()? canReadStorage,
    this.localDir = kRunnerUpLocalDir,
    bool? isAndroid,
    DateTime Function()? now,
  }) : _client = client ?? http.Client(),
       _loadLogin = loadLogin ?? DufsCredentials.load,
       _canReadStorage =
           canReadStorage ?? BackupService.instance.hasStoragePermission,
       _isAndroid = isAndroid ?? Platform.isAndroid,
       _now = now ?? DateTime.now;

  final http.Client _client;
  final Future<DufsCredentials?> Function() _loadLogin;
  final Future<bool> Function() _canReadStorage;
  final bool _isAndroid;
  final DateTime Function() _now;

  /// Where RunnerUp's own exports are looked for (when storage is readable).
  final String localDir;

  /// Runs the import unless it already completed, this is the sandbox, or
  /// this is not the phone (a desktop run would write the marker before the
  /// phone ever imported).
  Future<RunnerUpImportReport> runIfNeeded() async {
    if (Sandbox.enabled) {
      SandboxLog.event('runnerup import skipped: sandbox never imports');
      return kNothingImported;
    }
    if (!_isAndroid) {
      debugPrint('WorkoutApp: RunnerUp import skipped: not the phone.');
      return kNothingImported;
    }
    final prefs = await SharedPreferences.getInstance();
    if (prefs.getBool(kImportDoneKey) ?? false) {
      final marker = prefs.getString(kImportMarkerKey);
      if (marker == null) {
        runnerUpImportStatus.value = RunnerUpImportStatus.done;
        return kNothingImported;
      }
      return (
        imported: 0,
        duplicates: 0,
        skipped: 0,
        failures: await _deliver(prefs, marker),
      );
    }
    runnerUpImportStatus.value = RunnerUpImportStatus.running;
    final report = await _importAll(prefs);
    runnerUpImportStatus.value = report.failures.isEmpty
        ? RunnerUpImportStatus.done
        : RunnerUpImportStatus.failed;
    return report;
  }

  /// [runIfNeeded] that cannot leave the badge spinning: anything thrown
  /// outside the per-file handling (a platform error, a prefs write) becomes
  /// a logged failure and the `failed` state, retried next start.
  Future<RunnerUpImportReport> runGuarded() async {
    try {
      return await runIfNeeded();
    } on Object catch (error) {
      debugPrint('WorkoutApp: RunnerUp import WARNING: aborted: $error');
      runnerUpImportStatus.value = RunnerUpImportStatus.failed;
      return (
        imported: 0,
        duplicates: 0,
        skipped: 0,
        failures: ['aborted: $error'],
      );
    }
  }

  Future<RunnerUpImportReport> _importAll(SharedPreferences prefs) async {
    final tally = ImportTally();
    final login = await _loadLogin();
    final names = <String>[];
    if (login == null) {
      tally.fail('no dufs login in secure storage, so nothing was fetched');
    } else {
      names.addAll(await _importRemote(login, tally));
    }
    await _importLocal(tally);
    if (tally.failures.isEmpty && login != null) {
      final marker = jsonEncode({
        'completed_at': _now().toUtc().toIso8601String(),
        'count': names.length,
        'tcx_names': names,
      });
      await prefs.setString(kImportMarkerKey, marker);
      await prefs.setBool(kImportDoneKey, true);
      tally.failures.addAll(await _deliver(prefs, marker));
    }
    return tally.report;
  }

  /// Fetches and stores every remote export; returns the names now accounted
  /// for (stored, or already stored). A file that is not a usable run is
  /// skipped for good and left out; a network failure is a failure.
  Future<List<String>> _importRemote(
    DufsCredentials login,
    ImportTally tally,
  ) async {
    final List<String> remote;
    try {
      remote = await listProcessedTcx(_client, login);
    } on Exception catch (error) {
      debugPrint('WorkoutApp: RunnerUp import WARNING: listing failed: $error');
      tally.failures.add('listing the PC history failed: $error');
      return const [];
    }
    final accounted = <String>[];
    final seen = <String>{};
    for (final name in remote) {
      try {
        final bytes = await fetchProcessedTcx(_client, login, name);
        final source = await _ingest(name, bytes, tally);
        // The marker lists each distinct RunnerUp run once (the phone's
        // `Pixel_6a_` twin of a file is the same run) and never an
        // app-authored file.
        if (source == RunSource.runnerupImport &&
            seen.add(name.replaceFirst('Pixel_6a_', ''))) {
          accounted.add(name);
        }
      } on Exception catch (error) {
        debugPrint('WorkoutApp: RunnerUp import WARNING: $name: $error');
        tally.failures.add('$name: $error');
      }
      await Future<void>.delayed(Duration.zero);
    }
    return accounted;
  }

  /// Best effort: only if storage is already readable, and never a failure.
  Future<void> _importLocal(ImportTally tally) async {
    if (!await _canReadStorage()) {
      debugPrint(
        'WorkoutApp: RunnerUp import: storage not readable, skipping '
        '$localDir (the PC copy is the source).',
      );
      return;
    }
    try {
      final dir = Directory(localDir);
      if (!dir.existsSync()) return;
      for (final file in dir.listSync().whereType<File>().where(
        (f) => f.path.toLowerCase().endsWith('.tcx'),
      )) {
        final name = file.path.substring(file.path.lastIndexOf('/') + 1);
        await _ingest(name, await file.readAsBytes(), tally);
      }
    } on Exception catch (error) {
      debugPrint(
        'WorkoutApp: RunnerUp import WARNING: reading $localDir failed '
        '($error); the PC copy still completes the import.',
      );
    }
  }

  /// Stores one export; returns what its file says made it (before it is
  /// forced to history), or null when it is not a usable run.
  Future<RunSource?> _ingest(
    String name,
    Uint8List bytes,
    ImportTally tally,
  ) async {
    final String xml;
    final RunTrack decoded;
    try {
      xml = utf8.decode(bytes);
      decoded = decodeTcx(xml, fileName: name);
    } on FormatException catch (error) {
      tally.skipped++;
      debugPrint(
        'WorkoutApp: RunnerUp import WARNING: $name is not a usable run '
        '($error); skipped for good.',
      );
      return null;
    }
    // Forced, whatever the file says: an app-made TCX that came back through
    // processed/ must not be re-uploaded, so it is history, never pending.
    final track = RunTrack(
      id: decoded.id,
      sport: decoded.sport,
      startedAt: decoded.startedAt,
      points: decoded.points,
      totalSeconds: decoded.totalSeconds,
      distanceM: decoded.distanceM,
      source: RunSource.runnerupImport,
    );
    final added = await StorageService.instance.insertRun(
      track,
      tcxFilename: name,
      tcxSha256: tcxSha256(xml),
      uploadState: RunUploadState.never,
    );
    added ? tally.imported++ : tally.duplicates++;
    return decoded.source;
  }

  /// PUTs the marker; returns the failures (empty once the PC has it).
  Future<List<String>> _deliver(SharedPreferences prefs, String marker) async {
    final login = await _loadLogin();
    String? failure;
    if (login == null) {
      failure = 'no dufs login in secure storage, so the PC was not told';
    } else {
      try {
        await putImportMarker(_client, login, marker);
      } on Exception catch (error) {
        failure = 'telling the PC failed: $error';
      }
    }
    if (failure != null) {
      debugPrint('WorkoutApp: RunnerUp import WARNING: $failure');
      runnerUpImportStatus.value = RunnerUpImportStatus.failed;
      return [failure];
    }
    await prefs.remove(kImportMarkerKey);
    runnerUpImportStatus.value = RunnerUpImportStatus.done;
    return const [];
  }
}
