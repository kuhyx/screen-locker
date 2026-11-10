/// Stores a finished recording and queues it for upload.
library;

import 'dart:async';
import 'dart:developer';

import 'package:flutter/foundation.dart';
import 'package:workout_app/models/run_record.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/sandbox/sandbox_log.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/services/tcx_codec.dart';

/// What [saveRecordedRun] did.
@immutable
class RunSaveResult {
  /// Creates a result.
  const RunSaveResult({required this.stored, required this.reason});

  /// Whether a new row was written.
  final bool stored;

  /// A sentence saying what happened.
  final String reason;
}

/// Writes [track] to the `runs` table as an app-recorded, pending-upload run
/// and calls [enqueue] (without awaiting it) so the upload starts now.
Future<RunSaveResult> saveRecordedRun(
  RunTrack track, {
  required StorageService storage,
  required Future<Object?> Function() enqueue,
}) async {
  final tcx = encodeTcx(track);
  final name = tcxFilename(track);
  final stored = await storage.insertRun(
    track,
    tcxFilename: name,
    tcxSha256: tcxSha256(tcx),
    uploadState: RunUploadState.pending,
  );
  if (!stored) {
    final reason =
        'run ${track.id} is already stored (same id or same TCX), so '
        'nothing new was saved or queued.';
    log('RunSaver: $reason', level: 1000);
    return RunSaveResult(stored: false, reason: reason);
  }
  SandboxLog.event('run saved', {'id': track.id, 'file': name});
  unawaited(enqueue());
  return RunSaveResult(stored: true, reason: 'saved $name');
}
