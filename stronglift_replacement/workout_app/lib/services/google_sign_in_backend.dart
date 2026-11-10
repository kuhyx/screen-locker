/// One-tap Google sign-in, kept apart from the rest of the sync wiring.
///
/// Why this is its own file: `crdt_sync` is deliberately pure Dart (only
/// `crypto` and `http`), because the same library runs on Linux desktop and
/// headless under systemd, where no Google plugin exists. So the plugin
/// (`google_account_token`) is used here, in the app, and the library only
/// ever receives a token string through a closure.
///
/// What this buys: on a fresh install the sync account is reached by tapping
/// one account-picker row instead of typing a long password on a phone
/// keyboard. The password path stays as the fallback and as the machine
/// credential for desktop and the Python side.
library;

import 'dart:developer';

import 'package:google_account_token/google_account_token.dart' as plugin;

/// The account the security rules pin.
///
/// Not a secret -- it is already in the public `database.rules.json` -- but it
/// is the value that makes a wrong-account sign-in *fail loudly* instead of
/// authenticating fine and then being denied every read and write. See
/// `crdt-sync/tool/link_google.py`, which is what put the Google identity on
/// this uid in the first place.
const kSyncUid = 'OvA2REQyLIhAHOEjzwS1o877rgG3';

/// The project's **Web** OAuth client id, used as the audience for ID
/// tokens.
///
/// Public by design, exactly like [kProject]'s `apiKey`: it ships inside every
/// APK, and the security rules -- not its secrecy -- protect the data.
///
/// A plain const rather than a `--dart-define`, deliberately. As a
/// compile-time environment value it was empty in every build that matters:
/// the phone-deploy skill and CI both run `flutter build apk --release`
/// with no defines, so released APKs would have shown a Google button that
/// always reported "cancelled" -- a visible control that can never succeed,
/// which is the exact thing the [googleSignInSupported] gate exists to
/// prevent.
///
/// Fill this in from Firebase console -> Project settings -> the `syncs-rest`
/// Web app's OAuth client (type "Web application"). Android must request a
/// token minted for the *web* client; an Android client id here yields a token
/// Firebase rejects with `audience mismatch`.
/// Empty until the Web OAuth client is registered; [googleSignInSupported] is
/// false while it is, so the button stays hidden rather than failing.
const kServerClientId =
    '845446124781-prdoherj0v64vc6egvvcp3l0693khaur.apps.googleusercontent.com';

/// Whether this platform can sign in programmatically.
///
/// Only Android has an AccountManager (the plugin's own gate). Web and the
/// Linux desktop build authenticate from the shared credential instead, so
/// the button must not exist there. The plugin's check is web-safe (no
/// `dart:io`).
///
/// Also false when no client id is compiled in: a button that cannot possibly
/// succeed is worse than no button, and without this check an unconfigured
/// build reports "cancelled" and sends you debugging the OAuth console for a
/// problem that is really a missing constant.
bool get googleSignInSupported =>
    plugin.googleAccountTokenSupported && kServerClientId.isNotEmpty;

/// Returns a Google ID token for the signed-in account, or null.
///
/// Null rather than throwing when the user dismisses the picker: cancelling is
/// an ordinary outcome, and the caller falls back to the password path.
///
/// [signInFn], [serverClientId] and [warn] exist for tests that bypass the
/// plugin or observe the log.
Future<String?> googleIdToken({
  Future<String?> Function()? signInFn,
  String serverClientId = kServerClientId,
  void Function(String message)? warn,
}) async {
  if (signInFn != null) return await signInFn();
  if (serverClientId.isEmpty) {
    // Repo rule: a guard that aborts work must say so. Without this the
    // caller only sees "cancelled" and debugs the OAuth console instead.
    const message =
        'WorkoutApp: Google sign-in unavailable: the Web client id '
        '(kServerClientId) is empty; falling back to the password path';
    if (warn != null) {
      warn(message);
    } else {
      log(message, level: 900);
    }
    return null;
  }
  return await plugin.googleIdToken(serverClientId: serverClientId);
}
