/// Wiring for the Firebase backend, during and after the GitHub cutover.
///
/// Split by what is safe to publish, because this repo is public:
///
/// * [kProject] holds the Web API key and database URL. Both are public
///   identifiers that already ship inside the APK; the security rules, not
///   their secrecy, are what protect the data.
/// * The account email and password are entered once per device and kept in
///   the OS keystore, next to the GitHub token this app already stores there.
///
/// Nothing here reads `~/.config/crdt-sync/` — that is the desktop/Python
/// half. On Android there is no such file.
library;

import 'dart:convert';
import 'dart:developer';
import 'dart:io';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:path/path.dart' as p;
import 'package:workout_app/services/google_sign_in_backend.dart';

part 'firebase_backend_desktop.dart';
part 'firebase_backend_google.dart';

/// The shared `kuhy-syncs` project.
///
/// `databaseUrl` is the **regional** host. The plain `*.firebaseio.com` form
/// answers 404 with a `correctUrl` body rather than an obvious error, which
/// reads like an auth failure and wastes a debugging session.
const kProject = FirebaseProject(
  apiKey: 'AIzaSyCF_sA3xCMehAYXK8eND-rAygb9NXXW_8E',
  databaseUrl:
      'https://kuhy-syncs-default-rtdb.europe-west1.firebasedatabase.app',
);

/// Same options the GitHub token uses: off Android's deprecated
/// `encryptedSharedPreferences` path, and libsecret on Linux.
const _secure = FlutterSecureStorage();

// Everything below reaches the OS keystore through a platform channel, which
// `flutter test` has no binding for -- the same reason `main.dart` and
// `openRepository()` are excluded. The logic these wrap (parsing, the
// public/private split, sign-in) lives in `crdt_sync` and is covered there at
// 100%; what is left here is the two-line adapter.
// coverage:ignore-start

/// The keystore-backed home for the Firebase refresh token.
///
/// On Linux the "keystore" is the shared 0600 file above rather than
/// libsecret, so the desktop build signs in with the same durable refresh
/// token the Python side already holds — the account password on this fleet
/// is stale, and only the refresh token still authenticates.
SecureCredentialStore credentialStore() {
  if (Platform.isLinux) {
    return SecureCredentialStore(
      read: (key) async {
        final file = _desktopCredentialFile();
        if (!file.existsSync()) return null;
        return file.readAsString();
      },
      write: (key, value) async {
        final file = _desktopCredentialFile();
        await file.parent.create(recursive: true);
        await file.writeAsString(value);
        // The refresh token is the secret worth protecting; keep it 0600 the
        // way the Python half writes it.
        await Process.run('chmod', ['600', file.path]);
      },
      delete: (key) async {
        final file = _desktopCredentialFile();
        if (file.existsSync()) await file.delete();
      },
    );
  }
  return SecureCredentialStore(
    read: (key) => _secure.read(key: key),
    write: (key, value) => _secure.write(key: key, value: value),
    delete: (key) => _secure.delete(key: key),
  );
}

/// Reads the per-device account, or null when sync has not been set up.
Future<FirebaseAccount?> loadAccount() async {
  // Linux desktop reads the shared PC credential instead of the keystore,
  // so a fresh desktop install is connected the moment it starts.
  if (Platform.isLinux) return _accountFromDesktopConfig();
  try {
    return FirebaseAccount.tryParse(
      await _secure.read(key: kFirebaseAccountKey),
    );
  } on Object catch (error) {
    // No secret service available: behave as "not configured" rather than
    // crashing the caller. Deliberately catches Object, not Exception: with no
    // platform-channel binding (the `flutter test` host) this throws a
    // FlutterError -- an Error, not an Exception -- which slipped straight
    // through the old guard and failed any test whose code path reached the
    // keystore.
    //
    // "Not configured" is the honest answer in both cases, and it is never
    // silent: callers log their own "no Firebase account" reason, and this
    // says which failure produced it.
    // `log`, not `debugPrint`: debugPrint is stripped in release builds, and a
    // keystore that has stopped answering means every sync path on this device
    // silently reports "not configured" — the exact invisible failure the
    // repo's CLAUDE.md forbids.
    log(
      'WorkoutApp: cannot read the Firebase account from the keystore '
      '($error) — treating this device as NOT connected to sync, so '
      'progression and workouts will not reach any other device.',
      level: 1000,
      error: error,
    );
    return null;
  }
}

/// Reads the account from the keystore only, with no wrapper fallback.
///
/// [loadAccount] falls back to the desktop wrapper's `/sync-account` route
/// when the keystore is empty, which on Android resolves to `file:///` and
/// throws `No host specified in URI`. Callers reading back an account they
/// just wrote -- where a fallback would be wrong anyway -- use this instead.
/// Verified on the phone: without it, sign-in succeeded and then the settings
/// screen hung on "Signing in..." forever.
Future<FirebaseAccount?> storedAccount() async =>
    FirebaseAccount.tryParse(await _secure.read(key: kFirebaseAccountKey));

/// Stores the per-device account. Keystore only — never prefs, never source.
Future<void> saveAccount(FirebaseAccount account) =>
    _secure.write(key: kFirebaseAccountKey, value: account.toJsonString());

/// Forgets the account and any cached session.
Future<void> clearAccount() async {
  await _secure.delete(key: kFirebaseAccountKey);
  await credentialStore().clear();
}

/// Returns a signed-in Firebase client, or null when not configured.
///
/// Signs in with the stored password only when there is no cached refresh
/// token, so the usual path costs no authentication round trip.
Future<FirebaseRestClient?> openFirebase() async {
  final account = await loadAccount();
  if (account == null) {
    // A stored refresh token IS a signed-in device, even with no account
    // marker beside it. Treating the marker as the source of truth is what
    // made a phone with a live session sync over GitHub and 401 forever --
    // the credential was in the keystore the whole time, unused.
    return _clientFromStoredSession();
  }
  return firebaseClientFor(
    config: kProject.configFor(account.email),
    store: credentialStore(),
    // A Google-provisioned account stores an empty password.
    // Passing '' would make firebaseClientFor treat it as a usable
    // credential and sign in with it, which fails; null correctly
    // means "no password on this device".
    //
    // On Linux the shared refresh token in ~/.config/screen_locker is the
    // real credential and short-circuits sign-in before any password is
    // consulted. The password in ~/.config/crdt-sync no longer authenticates
    // on this fleet, so offering it would only turn a working token into an
    // INVALID_LOGIN_CREDENTIALS failure.
    password: (Platform.isLinux || account.password.isEmpty)
        ? null
        : account.password,
    // Deliberately NOT offering Google here. This path runs from background
    // timers and, in some apps, before runApp -- offering it would let a
    // non-interactive tick raise the OS account picker with no user action
    // behind it. Interactive sign-in uses openFirebaseWithGoogle instead.
    expectedUid: kSyncUid,
  );
}

/// a working device "not connected", which is exactly how a phone that was in
/// fact syncing looked broken.
Future<bool> isFirebaseConfigured() async {
  try {
    final auth = FirebaseTokenProvider(
      apiKey: kProject.apiKey,
      store: credentialStore(),
    );
    if (await auth.hasSession()) return true;
    // storedAccount, not loadAccount: on Android the latter falls back to the
    // desktop wrapper's /sync-account route, which resolves to file:/// and
    // throws "No host specified in URI" -- observed on the phone, where it
    // turned a successful sign-in into "Google sign-in failed".
    if (await storedAccount() == null) return false;
    // A marker with no session behind it cannot sign a single request. Drop
    // just the marker so the settings screen offers a sign-in instead of a
    // dead banner -- not clearAccount(), which also sets the opt-out flag and
    // would stop the desktop wrapper re-provisioning after the next sign-in.
    await _secure.delete(key: kFirebaseAccountKey);
    return false;
  } on Object catch (error, stackTrace) {
    log(
      'session probe failed; reporting this device as not configured',
      level: 1000,
      error: error,
      stackTrace: stackTrace,
    );
    return false;
  }
}

/// Returns a client built from the keystore's refresh token alone, or null.
///
/// The recovery path for a device that has a live session but no account
/// marker -- the state a Google sign-in used to leave behind. Costs one
/// keystore read and no network round trip when there is no session, so it is
/// safe on the background-tick path [openFirebase] also serves.
Future<FirebaseRestClient?> _clientFromStoredSession() async {
  try {
    final auth = FirebaseTokenProvider(
      apiKey: kProject.apiKey,
      store: credentialStore(),
    );
    if (!await auth.hasSession()) return null;
    return FirebaseRestClient(databaseUrl: kProject.databaseUrl, auth: auth);
  } on Object catch (error, stackTrace) {
    log(
      'stored-session recovery failed; falling back to the GitHub mirror',
      level: 1000,
      error: error,
      stackTrace: stackTrace,
    );
    return null;
  }
}

// coverage:ignore-end
