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
import 'package:flutter/foundation.dart' show debugPrint, visibleForTesting;
import 'package:flutter/services.dart' show MissingPluginException;
import 'package:permission_handler/permission_handler.dart';

/// Default directory backups live in on external storage.
const String kBackupDir = '/sdcard/WorkoutTracker';

/// Path where the backup JSON lives on external storage.
const String kBackupPath = '$kBackupDir/backup.json';

/// Path where the GitHub sync token is mirrored on external storage.
const String kSyncTokenBackupPath = '$kBackupDir/sync_token';

/// Path where the IN-PROGRESS session is mirrored on external storage.
///
/// The active session (which set you are on, and the reps done so far) lives
/// in app-private SQLite, which an uninstall or `pm clear` wipes — losing the
/// workout you are standing in the middle of. Mirroring it here means even a
/// full app-data wipe resumes on the exact set and rep.
const String kActiveSessionBackupPath = '$kBackupDir/active_session.json';

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

  String get _activeSessionPath => '$_baseDir/active_session.json';

  // ── Permission ─────────────────────────────────────────────────────────────

  // coverage:ignore-start
  // Thin wrappers over the permission_handler platform channel — Android
  // runtime permissions that can't be meaningfully exercised on the test host.

  /// Whether MANAGE_EXTERNAL_STORAGE is already held.
  ///
  /// A pure query: unlike [requestStoragePermission] this never navigates the
  /// user anywhere, so startup can check it and move on.
  ///
  /// Answers "not granted" instead of throwing when there is no platform
  /// channel to ask — the state on the `flutter test` host, where a
  /// MissingPluginException from a widget's `initState` fails the test rather
  /// than surfacing anything useful. "No permission" is also the truthful
  /// answer there: the test host has no `/sdcard` to write to.
  Future<bool> hasStoragePermission() async {
    try {
      return await Permission.manageExternalStorage.isGranted;
    } on MissingPluginException catch (error) {
      debugPrint(
        'WorkoutApp: no permission_handler platform channel ($error) — '
        'treating storage as not granted. Expected on the test host.',
      );
      return false;
    }
  }

  /// Requests MANAGE_EXTERNAL_STORAGE; opens the system settings page.
  ///
  /// Only ever called from an explicit user action in Settings. Startup must
  /// NOT call this: `Permission.manageExternalStorage.request()` throws the
  /// user into a system Settings page whenever the permission is absent, and
  /// since Firebase carries progression the `/sdcard` backup is a convenience,
  /// not a requirement. Prompting for it on every launch made an optional
  /// permission feel mandatory.
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
  /// Never throws — a failed backup must not crash a workout in progress — but
  /// it is NOT silent: a backup that quietly stops working is invisible until
  /// the reinstall that needed it, which is exactly how the 2026-08-05 wipe
  /// destroyed months of progression.
  ///
  /// Returns true if the backup was written.
  Future<bool> export(Map<String, dynamic> data) async {
    try {
      final dir = Directory(_baseDir);
      if (!dir.existsSync()) {
        dir.createSync(recursive: true);
      }
      await File(
        _backupPath,
      ).writeAsString(const JsonEncoder.withIndent('  ').convert(data));
      return true;
    } on Exception catch (e) {
      debugPrint(
        'WorkoutApp: BACKUP FAILED to $_backupPath: $e — progression state is '
        'now unprotected against an uninstall/reinstall. Check that storage '
        'permission is granted.',
      );
      return false;
    }
  }

  // ── Import ─────────────────────────────────────────────────────────────────

  /// Returns the parsed backup JSON, or null if the file does not exist or
  /// is unreadable.
  ///
  /// Distinguishes the two cases in the log: "no backup exists" is normal on a
  /// genuinely first install, whereas "a backup exists but could not be read"
  /// means a restore is about to fall through to defaults and silently lose
  /// real data. The second must never pass unnoticed.
  Future<Map<String, dynamic>?> readBackup() async {
    final f = File(_backupPath);
    try {
      if (!f.existsSync()) {
        debugPrint(
          'WorkoutApp: no backup at $_backupPath — nothing to restore. Normal '
          'on a first install; on a REINSTALL it means the backup was lost.',
        );
        return null;
      }
      final raw = await f.readAsString();
      return jsonDecode(raw) as Map<String, dynamic>;
    } on Exception catch (e) {
      debugPrint(
        'WorkoutApp: BACKUP UNREADABLE at $_backupPath: $e — a backup EXISTS '
        'but cannot be parsed, so restore will fall through to defaults and '
        'lose progression state. Do not let the app overwrite it.',
      );
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
    } on Exception catch (error) {
      // Backup is best-effort; never throw.
      debugPrint(
        'WorkoutApp: could not mirror the sync token to $_syncTokenPath '
        '($error) — the token will NOT survive the next uninstall.',
      );
    }
  }

  /// Mirrors the IN-PROGRESS session (or clears it when [data] is null).
  ///
  /// Best-effort like [export]. Called on every set/rep change, so a wipe of
  /// app-private storage — an uninstall, or `pm clear` — no longer costs the
  /// user the workout they are standing in the middle of.
  Future<void> exportActiveSession(Map<String, dynamic>? data) async {
    try {
      final f = File(_activeSessionPath);
      if (data == null) {
        if (f.existsSync()) await f.delete();
        return;
      }
      final dir = Directory(_baseDir);
      if (!dir.existsSync()) {
        dir.createSync(recursive: true);
      }
      await f.writeAsString(jsonEncode(data));
    } on Exception catch (error) {
      // Backup is best-effort; never throw mid-workout.
      debugPrint(
        'WorkoutApp: could not mirror the active session to '
        '$_activeSessionPath ($error) — an app-data wipe mid-workout would '
        'now lose the set you are standing on.',
      );
    }
  }

  /// Returns the mirrored in-progress session, or null if none / unreadable.
  Future<Map<String, dynamic>?> readActiveSession() async {
    try {
      final f = File(_activeSessionPath);
      if (!f.existsSync()) return null;
      final decoded = jsonDecode(await f.readAsString());
      return decoded is Map<String, dynamic> ? decoded : null;
    } on Exception catch (error) {
      debugPrint(
        'WorkoutApp: mirrored active session at $_activeSessionPath exists '
        'but is unreadable ($error) — an in-progress workout cannot be '
        'resumed from it.',
      );
      return null;
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
    } on Exception catch (error) {
      debugPrint(
        'WorkoutApp: mirrored sync token at $_syncTokenPath exists but is '
        'unreadable ($error) — sync cannot be recovered from the backup.',
      );
      return null;
    }
    // coverage:ignore-end
  }
}
