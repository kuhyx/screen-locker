/// Locally-stored GitHub sync token, trimmed from diet-guard's
/// `sync_settings.dart`: this app only ever talks to one hardcoded repo, so
/// there's no owner/repo to persist -- just the pasted PAT (kept as a
/// fallback; see [defaultClientId] for the primary "Connect GitHub" path).
///
/// Unlike diet-guard/todo, the token is also mirrored to external storage
/// via [BackupService] so it survives an app uninstall -- see that class's
/// library doc for the security trade-off this represents.
library;

import 'package:flutter/foundation.dart' show debugPrint;
import 'package:flutter/services.dart' show PlatformException;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:workout_app/services/backup_service.dart';

/// The repo owner/org, matching the PC's `SYNC_REPO_OWNER` constant.
const syncRepoOwner = 'kuhyx';

/// The repo name, matching the PC's `SYNC_REPO_NAME` constant.
const syncRepoName = 'syncs';

/// The GitHub token is kept in the OS keystore (Android Keystore) via
/// [FlutterSecureStorage] -- it never touches `SharedPreferences`, so there's
/// no plaintext-migration path to carry (unlike diet-guard/todo, which
/// predate this app and had an existing plaintext copy to migrate away from).
class SyncSettings {
  /// Creates a [SyncSettings] from its token.
  const SyncSettings({required this.token});

  /// A GitHub PAT with contents read/write on `$syncRepoOwner/$syncRepoName`.
  final String token;

  /// True when a token has been pasted and sync can be attempted.
  bool get isConfigured => token.isNotEmpty;

  /// This app's own GitHub OAuth App (device-flow enabled) client id, baked
  /// in so "Connect GitHub" works with zero setup. Registered 2026-07-06 at
  /// github.com/settings/developers, device flow enabled -- distinct from
  /// the sibling diet-guard/todo apps' OAuth Apps, which belong to different
  /// products and can't be shared across them.
  static const defaultClientId = 'Ov23liJNyu82dkIUiXSZ';

  static const _secureToken = 'sync.token';

  /// Default options keep us off the deprecated `encryptedSharedPreferences`
  /// path on Android.
  static const _secure = FlutterSecureStorage();

  /// Loads the token from the keystore, falling back to the external-storage
  /// backup (and re-seeding the keystore from it) if the keystore is empty --
  /// which is exactly what happens right after a reinstall, since the
  /// keystore entry does not survive uninstall but the backup file does.
  static Future<SyncSettings> load() async {
    String? token;
    try {
      token = await _secure.read(key: _secureToken);
    } on PlatformException catch (error) {
      debugPrint(
        'WorkoutApp: could not read the sync token from the keystore '
        '($error) — falling back to the external backup below.',
      );
      token = null;
    }
    if (token == null || token.isEmpty) {
      final backedUp = await BackupService.instance.readSyncToken();
      if (backedUp != null && backedUp.isNotEmpty) {
        token = backedUp;
        try {
          await _secure.write(key: _secureToken, value: backedUp);
        } on PlatformException catch (error) {
          // Keystore unavailable; still return the recovered token below.
          debugPrint(
            'WorkoutApp: recovered the sync token from the backup but could '
            'NOT write it back to the keystore ($error) — sync works this '
            'run, but every launch will keep re-reading the backup.',
          );
        }
      }
    }
    return SyncSettings(token: token ?? '');
  }

  /// Re-seeds the keystore from the external backup after its token was
  /// REJECTED by GitHub, returning the recovered token (or null).
  ///
  /// [load] prefers the keystore and only consults the backup when the
  /// keystore is EMPTY. So a stale keystore entry — say, one left by an
  /// earlier authorization — shadows a perfectly good backup indefinitely,
  /// and the user is told to re-authorize for nothing. Callers that see a
  /// token rejected call this and retry ONCE before demanding re-auth.
  ///
  /// Returns null when there is nothing to recover: no backup, an empty one,
  /// or one holding the very token that was just rejected.
  static Future<String?> recoverFromBackup(String rejectedToken) async {
    final backedUp = await BackupService.instance.readSyncToken();
    if (backedUp == null || backedUp.isEmpty || backedUp == rejectedToken) {
      return null;
    }
    try {
      await _secure.write(key: _secureToken, value: backedUp);
    } on PlatformException catch (error) {
      // Keystore unavailable — the caller can still use the returned token.
      debugPrint(
        'WorkoutApp: could not re-seed the keystore with the recovered sync '
        'token ($error) — this retry still works, but the stale entry will '
        'keep shadowing the backup on future launches.',
      );
    }
    return backedUp;
  }

  /// Persists [token] to the keystore (deleting the entry when empty) and
  /// mirrors it to external storage so it survives an app uninstall.
  /// Returns false if the platform secret service is unavailable.
  Future<bool> save() async {
    await BackupService.instance.exportSyncToken(token);
    try {
      if (token.isEmpty) {
        await _secure.delete(key: _secureToken);
      } else {
        await _secure.write(key: _secureToken, value: token);
      }
      return true;
    } on PlatformException catch (error) {
      debugPrint(
        'WorkoutApp: could not save the sync token to the keystore ($error) '
        '— it is still mirrored to external storage, so sync survives, but '
        'the keystore copy is missing.',
      );
      return false;
    }
  }
}
