/// Writes workout result JSON to external storage (ADB) and the in-app HTTP server.
library;

import 'dart:io';
import 'package:path_provider/path_provider.dart';
import 'package:workout_app/models/workout_session.dart';
import 'package:workout_app/services/http_server_service.dart';

/// Path on the phone's external storage where the PC reads workout data via ADB.
const String kSyncFilePath = '/sdcard/workout_result.json';

class SyncService {
  /// Writes [session] as JSON to external storage and updates the HTTP server.
  ///
  /// Falls back to app-external directory if /sdcard/ is not writable.
  Future<SyncResult> writeWorkoutResult(WorkoutSession session) async {
    final json = session.toJsonString();

    // Always update the in-app HTTP server so the PC can read via WiFi.
    HttpServerService.instance.updateLatestWorkout(json);

    // Try the primary path first (/sdcard/ — ADB-accessible without root).
    try {
      final file = File(kSyncFilePath);
      await file.writeAsString(json);
      return SyncResult(success: true, path: kSyncFilePath);
    } on Exception {
      // Fallback: app-specific external directory (still ADB accessible).
    }

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

    return SyncResult(success: false, path: null, error: 'No writable external path');
  }
}

class SyncResult {
  const SyncResult({required this.success, required this.path, this.error});

  final bool success;
  final String? path;
  final String? error;
}
