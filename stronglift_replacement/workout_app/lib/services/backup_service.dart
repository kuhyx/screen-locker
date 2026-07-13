/// Backup service: mirrors the DB (and, deliberately, the GitHub sync token)
/// as files on external storage so they survive uninstall/reinstall on
/// Android 11+, where internal storage -- including the Keystore-backed
/// secure storage the token normally lives in -- is wiped.
///
/// Mirroring the token here is a deliberate, explicit trade-off: it moves
/// the token from Keystore-only secrecy to plaintext-on-external-storage,
/// which is readable by any app holding storage permission or by plugging
/// the phone into a PC. That's a real credential-exposure increase over
/// diet-guard/todo (which keep their tokens Keystore-only and do not survive
/// reinstall) -- accepted here because losing sync on every reinstall during
/// active development was worse in practice than the exposure risk.
library;

import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart' show visibleForTesting;
import 'package:permission_handler/permission_handler.dart';

/// Default directory backups live in on external storage.
const String kBackupDir = '/sdcard/WorkoutTracker';

/// Path where the backup JSON lives on external storage.
const String kBackupPath = '$kBackupDir/backup.json';

/// Path where the GitHub sync token is mirrored on external storage.
const String kSyncTokenBackupPath = '$kBackupDir/sync_token';

/// Handles exporting and importing the workout database (and the GitHub
/// sync token) as files on external storage, which persist across app
/// uninstalls.
class BackupService {
  BackupService._();

  /// The singleton instance.
  static final BackupService instance = BackupService._();

  // Overridable for unit tests (set by resetForTesting) so round-trips can
  // be verified against a real temp directory instead of `/sdcard`, which
  // doesn't exist on the test host.
  static String _baseDir = kBackupDir;

  /// The directory backup files are currently written to/read from.
  /// Test-only.
  @visibleForTesting
  static String get baseDirForTesting => _baseDir;

  /// Points the backup files at this directory instead of [kBackupDir].
  /// Test-only.
  @visibleForTesting
  static set baseDirForTesting(String dir) => _baseDir = dir;

  String get _backupPath => '$_baseDir/backup.json';
  String get _syncTokenPath => '$_baseDir/sync_token';

  // ── Permission ─────────────────────────────────────────────────────────────

  // coverage:ignore-start
  // Thin wrappers over the permission_handler platform channel — Android
  // runtime permissions that can't be meaningfully exercised on the test host.

  /// Returns true if the app has MANAGE_EXTERNAL_STORAGE.
  Future<bool> hasStoragePermission() async {
    return Permission.manageExternalStorage.isGranted;
  }

  /// Requests MANAGE_EXTERNAL_STORAGE; opens the system settings page.
  ///
  /// Returns true once granted.
  Future<bool> requestStoragePermission() async {
    final status = await Permission.manageExternalStorage.request();
    return status.isGranted;
  }
  // coverage:ignore-end

  // ── Export ─────────────────────────────────────────────────────────────────

  /// Writes [data] to the backup path as pretty-printed JSON.
  ///
  /// Silently swallows errors (e.g. permission not granted, no external
  /// storage) so the caller never crashes.
  Future<void> export(Map<String, dynamic> data) async {
    try {
      final dir = Directory(_baseDir);
      if (!dir.existsSync()) {
        dir.createSync(recursive: true);
      }
      await File(
        _backupPath,
      ).writeAsString(const JsonEncoder.withIndent('  ').convert(data));
    } on Exception {
      // Backup is best-effort; never throw.
    }
  }

  // ── Import ─────────────────────────────────────────────────────────────────

  /// Returns the parsed backup JSON, or null if the file does not exist or
  /// is unreadable.
  Future<Map<String, dynamic>?> readBackup() async {
    try {
      final f = File(_backupPath);
      if (!f.existsSync()) return null;
      final raw = await f.readAsString();
      return jsonDecode(raw) as Map<String, dynamic>;
    } on Exception {
      return null;
    }
  }

  // ── Sync token backup ────────────────────────────────────────────────────

  /// Mirrors [token] to external storage (deleting the file when empty).
  /// Best-effort like [export]; see the library doc for the security
  /// trade-off this represents.
  Future<void> exportSyncToken(String token) async {
    try {
      final f = File(_syncTokenPath);
      if (token.isEmpty) {
        if (f.existsSync()) await f.delete();
        return;
      }
      final dir = Directory(_baseDir);
      if (!dir.existsSync()) {
        dir.createSync(recursive: true);
      }
      await f.writeAsString(token);
    } on Exception {
      // Backup is best-effort; never throw.
    }
  }

  /// Returns the mirrored sync token, or null if none exists / unreadable.
  Future<String?> readSyncToken() async {
    try {
      final f = File(_syncTokenPath);
      if (!f.existsSync()) return null;
      final token = await f.readAsString();
      return token.isEmpty ? null : token;
      // coverage:ignore-start
      // Defensive: a present, readable token file is the norm; a portable way
      // to make readAsString throw here (unreadable file) isn't available.
    } on Exception {
      return null;
    }
    // coverage:ignore-end
  }
}
