/// Writes workout result JSON to external storage (ADB) and the HTTP server.
library;

import 'dart:io';
import 'package:path_provider/path_provider.dart';
import 'package:workout_app/models/workout_session.dart';
import 'package:workout_app/services/http_server_service.dart';

/// Path on the phone's external storage where the PC reads workout data.
const String kSyncFilePath = '/sdcard/workout_result.json';

/// Handles writing completed workout sessions to disk and the HTTP server.
class SyncService {
  /// Writes [session] as JSON to external storage and updates the HTTP server.
  ///
  /// Falls back to app-external directory if /sdcard/ is not writable.
  Future<SyncResult> writeWorkoutResult(WorkoutSession session) async {
    final json = session.toJsonString();

    // Always update the in-app HTTP server so the PC can read via WiFi.
    HttpServerService.instance.latestWorkout = json;

    // Try the primary path first (/sdcard/ — ADB-accessible without root).
    try {
      final file = File(kSyncFilePath);
      await file.writeAsString(json);
      return const SyncResult(success: true, path: kSyncFilePath);
    } on Exception {
      // Fallback: app-specific external directory (still ADB accessible).
    }

    // External storage is Android-only; getExternalStorageDirectory() throws an
    // UnsupportedError (not an Exception) on other platforms, so guard the call.
    // coverage:ignore-start
    // Android-only: getExternalStorageDirectory is unavailable on the Linux
    // test host, so this block can't be exercised in CI.
    if (Platform.isAndroid) {
      try {
        final dir = await getExternalStorageDirectory();
        if (dir != null) {
          final file = File('${dir.path}/workout_result.json');
          await file.writeAsString(json);
          return SyncResult(success: true, path: file.path);
        }
      } on Exception {
        // Fallback failed.
      }
    }
    // coverage:ignore-end

    return const SyncResult(
      success: false,
      path: null,
      error: 'No writable external path',
    );
  }
}

/// Result of a [SyncService.writeWorkoutResult] call.
class SyncResult {
  /// Creates a sync result.
  const SyncResult({required this.success, required this.path, this.error});

  /// Whether the write succeeded.
  final bool success;

  /// Absolute path where the file was written, or null on failure.
  final String? path;

  /// Human-readable error message on failure.
  final String? error;
}
