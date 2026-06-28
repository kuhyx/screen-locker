/// Backup service: mirrors the DB as JSON to external storage so data survives
/// uninstall/reinstall on Android 11+ where internal storage is wiped.
library;

import 'dart:convert';
import 'dart:io';
import 'package:permission_handler/permission_handler.dart';

/// Path where the backup JSON lives on external storage.
const String kBackupPath = '/sdcard/WorkoutTracker/backup.json';

/// Handles exporting and importing the workout database as a JSON file on
/// external storage, which persists across app uninstalls.
class BackupService {
  BackupService._();

  /// The singleton instance.
  static final BackupService instance = BackupService._();

  // ── Permission ─────────────────────────────────────────────────────────────

  /// Returns true if the app has MANAGE_EXTERNAL_STORAGE.
  Future<bool> hasStoragePermission() async {
    return Permission.manageExternalStorage.isGranted;
  }

  /// Requests MANAGE_EXTERNAL_STORAGE; opens the system settings page.
  ///
  /// Returns true once granted.
  Future<bool> requestStoragePermission() async {
    final status =
        await Permission.manageExternalStorage.request();
    return status.isGranted;
  }

  // ── Export ─────────────────────────────────────────────────────────────────

  /// Writes [data] to [kBackupPath] as pretty-printed JSON.
  ///
  /// Silently swallows errors (e.g. permission not granted, no external
  /// storage) so the caller never crashes.
  Future<void> export(Map<String, dynamic> data) async {
    try {
      final dir = Directory('/sdcard/WorkoutTracker');
      if (!dir.existsSync()) {
        dir.createSync(recursive: true);
      }
      await File(kBackupPath).writeAsString(
        const JsonEncoder.withIndent('  ').convert(data),
      );
    } on Exception {
      // Backup is best-effort; never throw.
    }
  }

  // ── Import ─────────────────────────────────────────────────────────────────

  /// Returns the parsed backup JSON, or null if the file does not exist or
  /// is unreadable.
  Future<Map<String, dynamic>?> readBackup() async {
    try {
      final f = File(kBackupPath);
      if (!f.existsSync()) return null;
      final raw = await f.readAsString();
      return jsonDecode(raw) as Map<String, dynamic>;
    } on Exception {
      return null;
    }
  }
}
