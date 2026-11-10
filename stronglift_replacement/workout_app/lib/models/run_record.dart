/// A stored run: the track plus its upload bookkeeping.
library;

import 'package:flutter/foundation.dart';
import 'package:workout_app/models/run_track.dart';

/// Whether a run's TCX has reached the PC's dufs inbox.
enum RunUploadState {
  /// Recorded here; not uploaded yet (or the last attempt failed).
  pending('pending'),

  /// The PC's dufs accepted the file.
  uploaded('uploaded'),

  /// Must never be uploaded. Every imported RunnerUp run is this: re-sending
  /// history would credit old runs as new ones.
  never('never');

  const RunUploadState(this.storageKey);

  /// The value in the `runs.upload_state` column.
  final String storageKey;

  /// The state stored as [key]; throws on an unknown key.
  static RunUploadState fromStorageKey(String key) =>
      values.firstWhere((s) => s.storageKey == key);
}

/// One row of the `runs` table with its points (empty when listed).
@immutable
class RunRecord {
  /// Creates a record.
  const RunRecord({
    required this.track,
    required this.uploadState,
    required this.tcxFilename,
    required this.tcxSha256,
  });

  /// The run; `track.points` is empty in a list result.
  final RunTrack track;

  /// Upload bookkeeping.
  final RunUploadState uploadState;

  /// The export file name (see `tcxFilename`).
  final String tcxFilename;

  /// Hex SHA-256 of the encoded TCX: the dedupe key.
  final String tcxSha256;
}
