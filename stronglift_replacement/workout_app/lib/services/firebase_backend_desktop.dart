part of 'firebase_backend.dart';

// The Linux-desktop credential edge. Kept beside the Android keystore path
// rather than in it, because the two answer the same questions from entirely
// different places: Android from the OS keystore, desktop from the 0600 files
// the Python half of this fleet already maintains.
//
// Every function here touches the filesystem or the environment, which the
// `flutter test` host has no meaningful version of -- the same reason the rest
// of firebase_backend.dart is excluded.
// coverage:ignore-start

/// Path of the shared desktop credential cache, matching the Python
/// `crdt_sync.credential_store_for("screen_locker")`.
///
/// Deliberately the SAME file the PC's own sync already uses: the fleet holds
/// one long-lived refresh token per app, and a second copy would drift out of
/// date the first time either half refreshed it.
File _desktopCredentialFile() => File(
  p.join(
    Platform.environment['HOME'] ?? '',
    '.config',
    'screen_locker',
    'firebase_auth.json',
  ),
);

/// Reads the shared desktop credential from `~/.config/crdt-sync/`.
///
/// Linux desktop only. The PC half of this fleet (screen_locker, and the
/// `crdt_sync` Python library) already keeps the sync account there as
/// `firebase.json` + `password`, both mode 600, so the desktop build reads
/// that rather than standing up a second credential the user would have to
/// enter and keep in step. It also sidesteps `google_sign_in`, which has no
/// Linux implementation at all.
///
/// Returns null when the files are absent or malformed; the caller then
/// reports the device as not connected, exactly as an empty keystore would.
Future<FirebaseAccount?> _accountFromDesktopConfig() async {
  try {
    final home = Platform.environment['HOME'];
    if (home == null || home.isEmpty) {
      log(
        'WorkoutApp: HOME is unset — cannot locate ~/.config/crdt-sync, so '
        'this desktop is NOT connected to sync.',
        level: 1000,
      );
      return null;
    }
    final dir = Directory(p.join(home, '.config', 'crdt-sync'));
    final configFile = File(p.join(dir.path, 'firebase.json'));
    final passwordFile = File(p.join(dir.path, 'password'));
    if (!configFile.existsSync() || !passwordFile.existsSync()) {
      log(
        'WorkoutApp: no desktop sync credential at ${dir.path} '
        '(need firebase.json + password) — this desktop is NOT connected to '
        'sync, so progression and workouts will not reach any other device.',
        level: 1000,
      );
      return null;
    }
    final config =
        jsonDecode(await configFile.readAsString()) as Map<String, dynamic>;
    final email = config['email'] as String?;
    if (email == null || email.isEmpty) {
      log(
        'WorkoutApp: ${configFile.path} has no "email" key — cannot sign in.',
        level: 1000,
      );
      return null;
    }
    final password = (await passwordFile.readAsString()).trim();
    return FirebaseAccount(email: email, password: password);
  } on Object catch (error) {
    log(
      'WorkoutApp: failed to read the desktop sync credential from '
      '~/.config/crdt-sync ($error) — treating this desktop as NOT connected.',
      level: 1000,
      error: error,
    );
    return null;
  }
}

// coverage:ignore-end
