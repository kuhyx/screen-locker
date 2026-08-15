// The active-session mirror and the sync-token file.
//
// An `extension` in a `part`: Dart cannot continue a class body across
// files, but library privacy still applies inside a part, so these reach
// _activeSessionPath / _syncTokenPath and callers are unchanged.
part of 'backup_service.dart';

/// The active-session mirror and sync-token file on external storage.
extension BackupServiceSession on BackupService {
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
      final dir = Directory(BackupService._baseDir);
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
      final dir = Directory(BackupService._baseDir);
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
