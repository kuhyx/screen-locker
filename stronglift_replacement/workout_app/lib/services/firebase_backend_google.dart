part of 'firebase_backend.dart';

// The interactive Google sign-in path. Separate from the rest of the backend
// because it is the only piece that can raise UI, and because it is dead code
// on Linux desktop -- google_sign_in ships no Linux implementation, so the
// desktop build authenticates from the shared refresh token instead.
// coverage:ignore-start

/// Signs in with Google alone, for a device that has no account stored yet.
///
/// This is the one-tap path: [openFirebase] needs an account in the keystore
/// to know which email to use, but a fresh install has none. The Google token
/// carries the identity, so nothing needs to be typed.
///
/// The account is stored under the email **Firebase reports**, never one read
/// from the UI: a fresh install has no email anywhere on the device, so taking
/// it from a text field would persist an empty account and send the next
/// launch down the password path with ''.
///
/// Returns null when the user dismisses the picker; throws [FirebaseAuthError]
/// when Google succeeds but resolves to a uid the security rules do not pin,
/// which would otherwise authenticate fine and then be denied every read and
/// write with no other symptom.
Future<FirebaseRestClient?> openFirebaseWithGoogle({
  Future<String?> Function()? tokenFetcher,
  Future<void> Function(FirebaseAccount)? accountSaver,
  http.Client? httpClient,
}) async {
  final token = await (tokenFetcher ?? googleIdToken)();
  if (token == null) return null;
  final auth = FirebaseTokenProvider(
    apiKey: kProject.apiKey,
    store: credentialStore(),
    httpClient: httpClient,
  );
  final email = await auth.signInWithGoogle(
    idToken: token,
    expectedUid: kSyncUid,
  );
  // Saved unconditionally, and deliberately not gated on `email`:
  // `signInWithIdp` omits that field whenever the Google account hides it, and
  // gating the write on it returned a working client while persisting nothing,
  // so the next launch looked unconfigured and fell back to GitHub-only.
  // The session itself is already durable here -- signInWithGoogle stored the
  // refresh token -- and that token, not the address, is the credential.
  await (accountSaver ?? saveAccount)(
    FirebaseAccount(email: email ?? '', password: ''),
  );
  return FirebaseRestClient(databaseUrl: kProject.databaseUrl, auth: auth);
}

/// Whether this device can actually authenticate against Firebase.
///
/// True when either half of the state is present: the account marker
/// [loadAccount] reads, or a stored refresh token. The token is the half that
/// matters -- it is what signs requests -- so reporting the marker alone calls
// coverage:ignore-end
