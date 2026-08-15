// The public SettingsScreen widget and its injectable seams.
//
// A `part` so the widget stays in the same library as its private state class
// while the constructor and its eleven test seams — each needing its own doc
// comment under `public_member_api_docs` — live somewhere the state logic can
// be read without scrolling past them.
part of 'settings_screen.dart';

/// Screen for editing per-exercise thresholds and manual weight overrides.
///
/// No [BackupSlot] is wired into the shared Sync settings screen: unlike the
/// notes app and home_inventory, workout_app has no user-facing export/import
/// action to hand it. `BackupService.export`/`readBackup` are called only from
/// [StorageService]'s automatic paths (on every weight/threshold write, and
/// once at startup via `restoreFromBackupIfNeeded`) -- there is nothing for a
/// manual "Export"/"Import" button to trigger that isn't already automatic,
/// and a blind manual import would risk clobbering current progression with
/// whatever is on external storage. The storage-permission affordance itself
/// is a device permission, not a sync action, so it stays here rather than
/// moving to either sync screen.
class SettingsScreen extends StatefulWidget {
  /// Creates a [SettingsScreen].
  const SettingsScreen({
    super.key,
    this.httpClient,
    this.firebaseFactory,
    this.googleFirebaseFactory,
    this.googleAvailable,
    this.accountLoader,
    this.accountSaver,
    this.accountClearer,
    this.sessionProbe,
    this.storageChecker,
    this.storageRequester,
    this.progressionPuller,
  });

  /// Injectable HTTP client, passed through to [GitHubMirrorScreen] so its
  /// device-flow requests never hit the real network in tests.
  final http.Client? httpClient;

  /// Builds the Firebase client. Injected so tests need no platform channel.
  final Future<FirebaseRestClient?> Function()? firebaseFactory;

  /// Builds the Firebase backend via Google sign-in. Separate from
  /// [firebaseFactory] because it reaches the Google plugin's platform
  /// channel, which `flutter test` has no binding for.
  final Future<FirebaseRestClient?> Function()? googleFirebaseFactory;

  /// Whether to offer the Google button. Defaults to what the platform
  /// supports; injected by tests, whose host reports unsupported.
  final bool? googleAvailable;

  /// Keystore accessors for the Firebase account. Injected as a group so the
  /// connect/disconnect flows are testable without a platform channel --
  /// `flutter test` has no binding for one.
  final Future<FirebaseAccount?> Function()? accountLoader;

  /// Persists the account. See [accountLoader].
  final Future<void> Function(FirebaseAccount)? accountSaver;

  /// Forgets the account and any cached session. See [accountLoader].
  final Future<void> Function()? accountClearer;

  /// Whether a Firebase session is stored. See [accountLoader].
  ///
  /// Separate from [accountLoader] because the two answer different
  /// questions: the account marker is bookkeeping, the session is the
  /// credential. A device can hold the second without the first, and
  /// reporting only the first is what made a syncing phone read as
  /// "not connected".
  final Future<bool> Function()? sessionProbe;

  /// Reads whether storage permission is held. Injected for the same reason as
  /// [accountLoader]: `permission_handler` is a platform channel, and calling
  /// it unguarded in `initState` made every settings-screen test throw.
  final Future<bool> Function()? storageChecker;

  /// Opens the system grant page. See [storageChecker].
  final Future<bool> Function()? storageRequester;

  /// Pulls progression after returning from Sync settings. See
  /// [_openSyncSettings] for why this fires on pop rather than being hooked
  /// into the shared screen's connect flow.
  final Future<ProgressionSyncResult> Function()? progressionPuller;

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}
