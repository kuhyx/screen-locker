/// Settings screen: per-exercise streak thresholds and manual weight overrides.
/// Changes are saved immediately; a "Reset to defaults" button reverts all.
library;

import 'dart:async';
import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:url_launcher/url_launcher.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/models/workout_plan.dart';
import 'package:workout_app/services/backup_service.dart';
import 'package:workout_app/services/firebase_backend.dart';
import 'package:workout_app/services/github_device_auth.dart';
import 'package:workout_app/services/google_sign_in_backend.dart';
import 'package:workout_app/services/progression_sync_service.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/services/sync_settings.dart';
import 'package:workout_app/ui/theme.dart';

/// How to style a [_SyncStatusBadge].
enum _SyncStatusKind { success, pending, error }

/// Screen for editing per-exercise thresholds and manual weight overrides.
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

  /// Injectable HTTP client; tests pass a `MockClient` so the device-flow
  /// requests never hit the real network.
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

  /// Pulls progression after a successful connect. See [storageChecker].
  final Future<ProgressionSyncResult> Function()? progressionPuller;

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  bool _loading = true;

  final Map<String, int> _successThresholds = {};
  final Map<String, int> _failThresholds = {};
  final Map<String, double> _weights = {};
  final Map<String, int> _reps = {};

  // Debounce weight saves to avoid resetting streaks on every tap.
  final Map<String, Timer> _weightTimers = {};

  // Same debounce for reps, for the same reason.
  final Map<String, Timer> _repsTimers = {};

  final _tokenController = TextEditingController();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _firebaseConnected = false;
  bool _storageGranted = false;
  bool _firebaseBusy = false;

  // Persistent (not a transient SnackBar) so the result of Connect GitHub /
  // Save is still visible if the user looks back at the screen later --
  // mirrors diet-guard/todo's `_status` field in their settings screens.
  String? _syncStatus;
  _SyncStatusKind _syncStatusKind = _SyncStatusKind.pending;

  void _setSyncStatus(String message, _SyncStatusKind kind) {
    setState(() {
      _syncStatus = message;
      _syncStatusKind = kind;
    });
  }

  @override
  void initState() {
    super.initState();
    unawaited(_load());
    unawaited(_loadFirebaseAccount());
    unawaited(_loadStorageGranted());
  }

  Future<void> _loadStorageGranted() async {
    final granted =
        await (widget.storageChecker ??
            BackupService.instance.hasStoragePermission)();
    if (!mounted) return;
    setState(() => _storageGranted = granted);
  }

  /// Opens the system page for MANAGE_EXTERNAL_STORAGE.
  ///
  /// The ONLY caller of [BackupService.requestStoragePermission]: startup used
  /// to call it and dumped the user in system Settings on every launch, for a
  /// permission that is now genuinely optional.
  Future<void> _grantStorage() async {
    final granted =
        await (widget.storageRequester ??
            BackupService.instance.requestStoragePermission)();
    if (!mounted) return;
    setState(() => _storageGranted = granted);
  }

  /// Reflects a previously-stored account, so a returning user sees the real
  /// state instead of an empty form that looks unconfigured.
  Future<void> _loadFirebaseAccount() async {
    final account = await (widget.accountLoader ?? loadAccount)();
    // The stored session, not the account marker, decides "connected": a
    // Google sign-in leaves a refresh token that authenticates every request
    // even when no marker was written beside it.
    final connected = await (widget.sessionProbe ?? isFirebaseConfigured)();
    if (!mounted) return;
    if (account != null) _emailController.text = account.email;
    setState(() => _firebaseConnected = connected);
  }

  /// Signs in by picking a Google account -- the one-tap path.
  ///
  /// A dismissed picker is not an error; a wrong-account sign-in reports why,
  /// because that is the failure that otherwise looks like a working sync
  /// which silently never syncs.
  Future<void> _connectGoogle() async {
    setState(() => _firebaseBusy = true);
    try {
      final client =
          await (widget.googleFirebaseFactory ?? openFirebaseWithGoogle)();
      if (!mounted) return;
      if (client == null) {
        setState(() => _firebaseBusy = false);
        _setSyncStatus(
          'Google sign-in was cancelled.',
          _SyncStatusKind.pending,
        );
        return;
      }
      // openFirebaseWithGoogle stored the account under the email Firebase
      // reported; reflect it rather than reading the (empty) form field.
      final account = await (widget.accountLoader ?? storedAccount)();
      // Report the persisted state, not the fact that the call returned a
      // client: a non-null client only means sign-in succeeded in that
      // moment, which is how four apps claimed "Connected" and then synced
      // over GitHub after the next restart.
      final connected = await (widget.sessionProbe ?? isFirebaseConfigured)();
      if (!mounted) return;
      if (account != null) _emailController.text = account.email;
      setState(() {
        _firebaseBusy = false;
        _firebaseConnected = connected;
      });
      _setSyncStatus(
        connected
            ? 'Connected to Firebase.'
            : 'Signed in, but this device did not save the session - it will '
                  'sync over GitHub after a restart. Try connecting again.',
        connected ? _SyncStatusKind.success : _SyncStatusKind.error,
      );
    } on FirebaseAuthError catch (error) {
      if (!mounted) return;
      setState(() {
        _firebaseBusy = false;
        _firebaseConnected = false;
      });
      _setSyncStatus(error.message, _SyncStatusKind.error);
    } on Object catch (error) {
      // Broader than Exception on purpose: a missing platform binding raises
      // an Error, and anything escaping here leaves the button disabled and
      // the screen stuck forever -- which is what happened on the phone
      // before storedAccount() replaced loadAccount().
      if (!mounted) return;
      setState(() {
        _firebaseBusy = false;
        _firebaseConnected = false;
      });
      _setSyncStatus('Google sign-in failed: $error', _SyncStatusKind.error);
    }
  }

  /// Stores the typed account and signs in immediately, so a typo surfaces
  /// here rather than as a silent background failure on the next push.
  ///
  /// Without this the app could never reach Firebase at all: `openFirebase()`
  /// would read an account nothing had ever written.
  Future<void> _connectFirebase() async {
    final email = _emailController.text.trim();
    final password = _passwordController.text;
    if (email.isEmpty || password.isEmpty) {
      _setSyncStatus(
        'Enter the sync account email and password.',
        _SyncStatusKind.error,
      );
      return;
    }
    setState(() => _firebaseBusy = true);
    await (widget.accountSaver ?? saveAccount)(
      FirebaseAccount(email: email, password: password),
    );
    final client = await (widget.firebaseFactory ?? openFirebase)();
    if (!mounted) return;
    if (client == null) {
      await (widget.accountClearer ?? clearAccount)();
      if (!mounted) return;
      setState(() {
        _firebaseBusy = false;
        _firebaseConnected = false;
      });
      _setSyncStatus(
        'Firebase rejected that account.',
        _SyncStatusKind.error,
      );
      return;
    }
    _passwordController.clear();

    // Pull immediately. Startup already ran its pull and skipped, because at
    // that point there was no account — so without this the device stays on
    // factory defaults holding real remote progression, and its first finished
    // workout would push those defaults over the top. Connecting late is the
    // normal path after a reinstall (the uninstall wipes the keystore), so
    // this is the common case, not an edge one.
    final restored =
        await (widget.progressionPuller ??
            ProgressionSyncService().pullProgression)();
    if (!mounted) return;

    setState(() {
      _firebaseBusy = false;
      _firebaseConnected = true;
    });
    _setSyncStatus(
      restored.changed
          ? 'Connected. Restored ${restored.count} exercise(s) from Firebase.'
          : 'Connected to Firebase.',
      _SyncStatusKind.success,
    );
    if (restored.changed) await _load();
  }

  Future<void> _disconnectFirebase() async {
    await (widget.accountClearer ?? clearAccount)();
    if (!mounted) return;
    _emailController.clear();
    _passwordController.clear();
    setState(() => _firebaseConnected = false);
    _setSyncStatus('Firebase disconnected.', _SyncStatusKind.pending);
  }

  @override
  void dispose() {
    for (final t in _weightTimers.values) {
      t.cancel();
    }
    for (final t in _repsTimers.values) {
      t.cancel();
    }
    _tokenController.dispose();
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final states = await StorageService.instance.getAllExerciseStates();
    final syncSettings = await SyncSettings.load();
    if (mounted) {
      setState(() {
        for (final s in states) {
          _successThresholds[s.name] = s.successThreshold;
          _failThresholds[s.name] = s.failThreshold;
          _weights[s.name] = s.weight;
          _reps[s.name] = s.reps;
        }
        _tokenController.text = syncSettings.token;
        _loading = false;
      });
      // Never claim "Connected" just because a token STRING exists — check it
      // against the API. A revoked/expired token otherwise shows a reassuring
      // green badge while every sync 401s and the history silently stays empty.
      if (syncSettings.isConfigured) {
        _setSyncStatus('Verifying…', _SyncStatusKind.pending);
        await _verifyConnection(syncSettings.token);
      }
    }
  }

  Future<void> _saveToken() async {
    final saved = await SyncSettings(
      token: _tokenController.text.trim(),
    ).save();
    if (!mounted) return;
    _setSyncStatus(
      saved ? 'Sync token saved.' : 'Could not save token on this device.',
      saved ? _SyncStatusKind.success : _SyncStatusKind.error,
    );
  }

  /// Runs the OAuth device flow and, on success, saves the resulting token
  /// and verifies it actually works against the sync repo -- a saved token
  /// that can't reach `$syncRepoOwner/$syncRepoName` (wrong scope, revoked,
  /// etc.) must be surfaced immediately, not discovered on the next workout.
  Future<void> _connectGitHub() async {
    final auth = GitHubDeviceAuth(
      clientId: SyncSettings.defaultClientId,
      httpClient: widget.httpClient,
    );
    try {
      final device = await auth.requestDeviceCode();
      if (!mounted) return;
      final token = await showDialog<String>(
        context: context,
        barrierDismissible: false,
        builder: (_) => _DeviceCodeDialog(device: device, auth: auth),
      );
      if (token != null && token.isNotEmpty) {
        setState(() => _tokenController.text = token);
        _setSyncStatus('Connected — verifying…', _SyncStatusKind.pending);
        final saved = await SyncSettings(token: token).save();
        if (!saved) {
          if (!mounted) return;
          _setSyncStatus(
            'Connected, but could not save the token on this device.',
            _SyncStatusKind.error,
          );
          return;
        }
        await _verifyConnection(token);
      }
    } on Exception catch (e) {
      if (!mounted) return;
      _setSyncStatus('Could not start device flow: $e', _SyncStatusKind.error);
    } finally {
      auth.close();
    }
  }

  /// Confirms [token] can actually read `$syncRepoOwner/$syncRepoName`.
  /// Returns null when [token] works, else the error GitHub gave.
  Future<GitHubSyncError?> _tryVerify(String token) async {
    final client = GitHubClient(
      owner: syncRepoOwner,
      repo: syncRepoName,
      token: token,
      httpClient: widget.httpClient,
    );
    try {
      await client.getFileText('devices/phone/log.json');
      return null;
    } on GitHubSyncError catch (e) {
      return e;
    } finally {
      client.close();
    }
  }

  Future<void> _verifyConnection(String token) async {
    final error = await _tryVerify(token);
    if (error == null) {
      if (!mounted) return;
      _setSyncStatus(
        'Connected and verified via GitHub.',
        _SyncStatusKind.success,
      );
      return;
    }

    // The keystore's token may be a stale one shadowing a good backup, and
    // load() only consults the backup when the keystore is EMPTY. Try the
    // backup once before making the user re-authorize for nothing.
    final recovered = await SyncSettings.recoverFromBackup(token);
    if (recovered != null && await _tryVerify(recovered) == null) {
      if (!mounted) return;
      _tokenController.text = recovered;
      _setSyncStatus(
        'Connected and verified via GitHub (recovered the saved token from '
        'backup — the stored one had been rejected).',
        _SyncStatusKind.success,
      );
      return;
    }

    if (!mounted) return;
    // Say plainly that sync is broken. "Connected, but…" reads as success
    // and is how a dead token hid behind a green badge.
    _setSyncStatus(
      error.toString().contains('401')
          ? 'NOT connected: GitHub rejected this token (401) and no working '
                'backup was found. Tap Connect GitHub to re-authorize — '
                'until then nothing syncs.'
          : 'NOT syncing: could not reach GitHub ($error)',
      _SyncStatusKind.error,
    );
  }

  void _onWeightChanged(String name, double value) {
    setState(() => _weights[name] = value);
    _weightTimers[name]?.cancel();
    _weightTimers[name] = Timer(const Duration(milliseconds: 600), () {
      unawaited(StorageService.instance.setExerciseWeight(name, value));
    });
  }

  void _onRepsChanged(String name, int value) {
    setState(() => _reps[name] = value);
    _repsTimers[name]?.cancel();
    _repsTimers[name] = Timer(const Duration(milliseconds: 600), () {
      unawaited(StorageService.instance.setExerciseReps(name, value));
    });
  }

  Future<void> _onThresholdChanged(String name, int success, int fail) async {
    setState(() {
      _successThresholds[name] = success;
      _failThresholds[name] = fail;
    });
    await StorageService.instance.setExerciseThresholds(
      name,
      successThreshold: success,
      failThreshold: fail,
    );
  }

  Future<void> _resetToDefaults() async {
    final colorScheme = Theme.of(context).colorScheme;
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: colorScheme.surfaceContainerHigh,
        title: Text(
          'Reset to defaults?',
          style: TextStyle(color: colorScheme.onSurface),
        ),
        content: Text(
          'All weights and thresholds will be reset. '
          'Streak counters will be cleared.',
          style: TextStyle(color: colorScheme.onSurfaceVariant),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: Text(
              'Cancel',
              style: TextStyle(color: colorScheme.onSurfaceVariant),
            ),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: Text('Reset', style: TextStyle(color: colorScheme.error)),
          ),
        ],
      ),
    );
    if (ok == true) {
      for (final name in _orderedNames) {
        await StorageService.instance.resetExerciseToDefaults(name);
      }
      await _load();
    }
  }

  List<String> get _orderedNames {
    final seen = <String>{};
    return [
      ...workoutA,
      ...workoutB,
    ].map((e) => e.name).where(seen.add).toList();
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        backgroundColor: colorScheme.surfaceContainerHigh,
        title: Text(
          'Settings',
          style: TextStyle(color: colorScheme.onSurface),
        ),
        iconTheme: IconThemeData(color: colorScheme.onSurface),
        actions: [
          TextButton(
            onPressed: _loading ? null : _resetToDefaults,
            child: Text(
              'Reset defaults',
              style: TextStyle(color: colorScheme.error),
            ),
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                const _SectionHeader('WEIGHTS'),
                const SizedBox(height: 4),
                Text(
                  'Override current working weight. '
                  'Resets streak counters. Rounded to 2.5 kg.',
                  style: TextStyle(
                    color: colorScheme.onSurfaceVariant,
                    fontSize: AppTextSize.caption,
                  ),
                ),
                const SizedBox(height: 12),
                ..._orderedNames.map((name) {
                  final w = _weights[name];
                  if (w == null) return const SizedBox.shrink();
                  return _WeightRow(
                    name: name,
                    weight: w,
                    onChanged: (v) => _onWeightChanged(name, v),
                  );
                }),
                const SizedBox(height: 20),
                const _SectionHeader('TARGET REPS'),
                const SizedBox(height: 4),
                Text(
                  'Override target reps per set. Resets streak counters. '
                  'Progression only ever raises reps, so this is the only way '
                  'to lower one.',
                  style: TextStyle(
                    color: colorScheme.onSurfaceVariant,
                    fontSize: AppTextSize.caption,
                  ),
                ),
                const SizedBox(height: 12),
                ..._orderedNames.map((name) {
                  final r = _reps[name];
                  if (r == null) return const SizedBox.shrink();
                  return _RepsRow(
                    name: name,
                    reps: r,
                    onChanged: (v) => _onRepsChanged(name, v),
                  );
                }),
                const SizedBox(height: 20),
                const _SectionHeader('PROGRESSION THRESHOLDS'),
                const SizedBox(height: 4),
                Text(
                  'Consecutive successes (↑) or failures (↓) '
                  'before weight changes.',
                  style: TextStyle(
                    color: colorScheme.onSurfaceVariant,
                    fontSize: AppTextSize.caption,
                  ),
                ),
                const SizedBox(height: 12),
                ..._orderedNames.map((name) {
                  final sThresh = _successThresholds[name] ?? 3;
                  final fThresh = _failThresholds[name] ?? 2;
                  return _ExerciseThresholdCard(
                    name: name,
                    successThreshold: sThresh,
                    failThreshold: fThresh,
                    onSuccessChanged: (v) =>
                        _onThresholdChanged(name, v, _failThresholds[name]!),
                    onFailChanged: (v) =>
                        _onThresholdChanged(name, _successThresholds[name]!, v),
                  );
                }),
                const SizedBox(height: 20),
                const _SectionHeader('SYNC'),
                const SizedBox(height: 4),
                Text(
                  _firebaseConnected
                      ? 'Connected. Workouts go to Firebase first, and still '
                            'mirror to GitHub until every device has moved.'
                      : 'Not connected -- syncing over GitHub only. Enter the '
                            'shared sync account to move this device over. '
                            'The password is kept in the device keystore, '
                            'never in the app or the repo.',
                  style: TextStyle(
                    color: colorScheme.onSurfaceVariant,
                    fontSize: AppTextSize.caption,
                  ),
                ),
                const SizedBox(height: 12),
                if (_syncStatus != null) ...[
                  _SyncStatusBadge(text: _syncStatus!, kind: _syncStatusKind),
                  const SizedBox(height: 12),
                ],
                // Once connected the account is read-only text: an editable
                // email box beside an empty password box reads as "you still
                // have to enter this", making a connected device look
                // unconfigured.
                if (_firebaseConnected)
                  Row(
                    children: [
                      const Icon(Icons.cloud_done, size: 20),
                      const SizedBox(width: 8),
                      Expanded(child: Text(_emailController.text)),
                      TextButton(
                        onPressed: _firebaseBusy ? null : _disconnectFirebase,
                        child: const Text('Disconnect'),
                      ),
                    ],
                  )
                else ...[
                  TextField(
                    controller: _emailController,
                    keyboardType: TextInputType.emailAddress,
                    autocorrect: false,
                    decoration: const InputDecoration(
                      labelText: 'Sync account email',
                    ),
                  ),
                  const SizedBox(height: 8),
                  TextField(
                    controller: _passwordController,
                    obscureText: true,
                    autocorrect: false,
                    decoration: const InputDecoration(
                      labelText: 'Sync account password',
                    ),
                  ),
                  const SizedBox(height: 12),
                  ElevatedButton.icon(
                    onPressed: _firebaseBusy ? null : _connectFirebase,
                    icon: const Icon(Icons.cloud_done),
                    label: const Text('Connect Firebase'),
                  ),
                  // One tap, no typing -- the path that matters after a
                  // reinstall. Hidden where the platform has no programmatic
                  // Google flow (see google_platform.dart), because a button
                  // that always failed would be worse than none.
                  if (widget.googleAvailable ?? googleSignInSupported) ...[
                    const SizedBox(height: 12),
                    ElevatedButton.icon(
                      onPressed: _firebaseBusy ? null : _connectGoogle,
                      icon: const Icon(Icons.account_circle),
                      label: const Text('Sign in with Google'),
                    ),
                  ],
                ],
                const SizedBox(height: 8),
                // GitHub is the cutover mirror, not a choice competing with
                // Firebase, so its connect button moves in here too.
                ExpansionTile(
                  title: Text(
                    'Advanced (GitHub mirror)',
                    style: TextStyle(
                      color: colorScheme.onSurfaceVariant,
                      fontSize: AppTextSize.label,
                    ),
                  ),
                  collapsedIconColor: colorScheme.onSurfaceVariant,
                  iconColor: colorScheme.onSurfaceVariant,
                  tilePadding: EdgeInsets.zero,
                  children: [
                    Align(
                      alignment: Alignment.centerLeft,
                      child: Text(
                        'Authorize in your browser -- no token to paste. '
                        'Syncs to $syncRepoOwner/$syncRepoName.',
                        style: TextStyle(
                          color: colorScheme.onSurfaceVariant,
                          fontSize: AppTextSize.caption,
                        ),
                      ),
                    ),
                    const SizedBox(height: 12),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: ElevatedButton.icon(
                        onPressed: _connectGitHub,
                        icon: const Icon(Icons.login),
                        label: const Text('Connect GitHub'),
                      ),
                    ),
                    const SizedBox(height: 12),
                    // The PAT fallback lives inside the mirror section too:
                    // two sibling "Advanced" disclosures made it look like
                    // there were two independent things to configure.
                    _SyncTokenField(
                      controller: _tokenController,
                      onSave: _saveToken,
                    ),
                  ],
                ),
                const SizedBox(height: 20),
                const _SectionHeader('OFFLINE BACKUP'),
                const SizedBox(height: 4),
                Text(
                  _storageGranted
                      ? 'Granted. Progression is also written to '
                            '$kBackupPath, so it survives a reinstall even '
                            'with no network.'
                      : 'Optional. Progression is restored from Firebase on '
                            'a fresh install, so this is a second, offline '
                            'copy — not a requirement. Granting it also keeps '
                            'a readable snapshot at $kBackupPath.',
                  style: TextStyle(
                    color: colorScheme.onSurfaceVariant,
                    fontSize: AppTextSize.caption,
                  ),
                ),
                const SizedBox(height: 12),
                if (_storageGranted)
                  const Row(
                    children: [
                      Icon(Icons.check_circle, size: 20),
                      SizedBox(width: 8),
                      Expanded(child: Text('Storage permission granted')),
                    ],
                  )
                else
                  Align(
                    alignment: Alignment.centerLeft,
                    child: ElevatedButton.icon(
                      onPressed: _grantStorage,
                      icon: const Icon(Icons.sd_storage),
                      label: const Text('Grant storage permission'),
                    ),
                  ),
              ],
            ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: TextStyle(
        color: Theme.of(context).colorScheme.onSurfaceVariant,
        fontSize: AppTextSize.caption,
        letterSpacing: 1.4,
      ),
    );
  }
}

class _RepsRow extends StatelessWidget {
  const _RepsRow({
    required this.name,
    required this.reps,
    required this.onChanged,
  });

  final String name;
  final int reps;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        children: [
          Expanded(
            child: Text(
              name,
              style: TextStyle(
                color: colorScheme.onSurfaceVariant,
                fontSize: AppTextSize.label,
              ),
            ),
          ),
          _StepperButton(
            icon: Icons.remove,
            onTap: () => onChanged((reps - 1).clamp(1, 999)),
          ),
          SizedBox(
            width: 72,
            child: Text(
              '$reps reps',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: colorScheme.onSurface,
                fontSize: AppTextSize.label,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
          _StepperButton(
            icon: Icons.add,
            onTap: () => onChanged((reps + 1).clamp(1, 999)),
          ),
        ],
      ),
    );
  }
}

class _WeightRow extends StatelessWidget {
  const _WeightRow({
    required this.name,
    required this.weight,
    required this.onChanged,
  });

  final String name;
  final double weight;
  final ValueChanged<double> onChanged;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        children: [
          Expanded(
            child: Text(
              name,
              style: TextStyle(
                color: colorScheme.onSurfaceVariant,
                fontSize: AppTextSize.label,
              ),
            ),
          ),
          _StepperButton(
            icon: Icons.remove,
            onTap: () => onChanged(
              (weight - kWeightIncrement).clamp(0.0, 999.0),
            ),
          ),
          // Fixed-width container supports up to "999.9kg" (7 chars).
          SizedBox(
            width: 72,
            child: Text(
              '${weight}kg',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: colorScheme.onSurface,
                fontSize: AppTextSize.label,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
          _StepperButton(
            icon: Icons.add,
            onTap: () => onChanged(weight + kWeightIncrement),
          ),
        ],
      ),
    );
  }
}

class _StepperButton extends StatelessWidget {
  const _StepperButton({required this.icon, required this.onTap});

  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 36,
        height: 36,
        decoration: BoxDecoration(
          color: colorScheme.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(6),
        ),
        alignment: Alignment.center,
        child: Icon(icon, color: colorScheme.onSurface, size: 18),
      ),
    );
  }
}

/// A visible, colored status pill for the GitHub sync connection state --
/// placed directly under the section description (not buried below the
/// collapsed Advanced field) so "am I connected?" has an immediate answer.
class _SyncStatusBadge extends StatelessWidget {
  const _SyncStatusBadge({required this.text, required this.kind});

  final String text;
  final _SyncStatusKind kind;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final status = Theme.of(context).extension<AppStatusColors>()!;
    final color = switch (kind) {
      _SyncStatusKind.success => status.success,
      _SyncStatusKind.error => colorScheme.error,
      _SyncStatusKind.pending => colorScheme.onSurfaceVariant,
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.4)),
      ),
      child: Row(
        children: [
          if (kind == _SyncStatusKind.pending)
            const SizedBox(
              width: 14,
              height: 14,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          else
            Icon(
              kind == _SyncStatusKind.success
                  ? Icons.check_circle
                  : Icons.error,
              color: color,
              size: 16,
            ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              text,
              style: TextStyle(
                color: color,
                fontSize: AppTextSize.label,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _SyncTokenField extends StatelessWidget {
  const _SyncTokenField({required this.controller, required this.onSave});

  final TextEditingController controller;
  final VoidCallback onSave;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: TextField(
            controller: controller,
            obscureText: true,
            style: TextStyle(color: colorScheme.onSurface),
            // filled/fillColor/border inherit from the shared
            // inputDecorationTheme (theme.dart) — only the field-specific
            // hint/padding need setting here.
            decoration: InputDecoration(
              hintText: 'GitHub PAT',
              hintStyle: TextStyle(color: colorScheme.onSurfaceVariant),
              contentPadding: const EdgeInsets.symmetric(
                horizontal: 12,
                vertical: 10,
              ),
            ),
          ),
        ),
        const SizedBox(width: 8),
        ElevatedButton(onPressed: onSave, child: const Text('Save')),
      ],
    );
  }
}

class _ExerciseThresholdCard extends StatelessWidget {
  const _ExerciseThresholdCard({
    required this.name,
    required this.successThreshold,
    required this.failThreshold,
    required this.onSuccessChanged,
    required this.onFailChanged,
  });

  final String name;
  final int successThreshold;
  final int failThreshold;
  final ValueChanged<int> onSuccessChanged;
  final ValueChanged<int> onFailChanged;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final status = Theme.of(context).extension<AppStatusColors>()!;
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainerHigh,
        borderRadius: BorderRadius.circular(AppRadius.sm),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            name,
            style: TextStyle(
              color: colorScheme.onSurface,
              fontWeight: FontWeight.bold,
              fontSize: AppTextSize.label,
            ),
          ),
          const SizedBox(height: 10),
          _ThresholdRow(
            label: '↑ Increase after N successes',
            value: successThreshold,
            color: status.success,
            onChanged: onSuccessChanged,
          ),
          const SizedBox(height: 6),
          _ThresholdRow(
            label: '↓ Decrease after N failures',
            value: failThreshold,
            color: colorScheme.error,
            onChanged: onFailChanged,
          ),
        ],
      ),
    );
  }
}

class _ThresholdRow extends StatelessWidget {
  const _ThresholdRow({
    required this.label,
    required this.value,
    required this.color,
    required this.onChanged,
  });

  final String label;
  final int value;
  final Color color;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Row(
      children: [
        Expanded(
          child: Text(
            label,
            style: TextStyle(
              color: colorScheme.onSurfaceVariant,
              fontSize: AppTextSize.caption,
            ),
          ),
        ),
        const SizedBox(width: 8),
        for (int i = 1; i <= 5; i++)
          Padding(
            padding: const EdgeInsets.only(left: 4),
            child: GestureDetector(
              onTap: () => onChanged(i),
              child: Container(
                width: 32,
                height: 32,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: i == value
                      ? color
                      : colorScheme.surfaceContainerHighest,
                ),
                alignment: Alignment.center,
                child: Text(
                  '$i',
                  style: TextStyle(
                    // on-fill on the selected (filled) circle.
                    color: i == value
                        ? colorScheme.onPrimary
                        : colorScheme.onSurface,
                    fontWeight: FontWeight.bold,
                    fontSize: AppTextSize.label,
                  ),
                ),
              ),
            ),
          ),
      ],
    );
  }
}

/// Dialog shown during the device flow: displays the user code, opens the
/// verification page, and polls until authorized -- popping the token (or
/// null if cancelled / failed).
class _DeviceCodeDialog extends StatefulWidget {
  const _DeviceCodeDialog({required this.device, required this.auth});

  final DeviceCodeResponse device;
  final GitHubDeviceAuth auth;

  @override
  State<_DeviceCodeDialog> createState() => _DeviceCodeDialogState();
}

class _DeviceCodeDialogState extends State<_DeviceCodeDialog> {
  String? _error;

  @override
  void initState() {
    super.initState();
    unawaited(_poll());
  }

  Future<void> _poll() async {
    try {
      final token = await widget.auth.pollForToken(widget.device);
      if (mounted) Navigator.of(context).pop(token);
    } on Exception catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  Future<void> _openPage() async {
    await Clipboard.setData(ClipboardData(text: widget.device.userCode));
    await launchUrl(
      Uri.parse(widget.device.verificationUri),
      mode: LaunchMode.externalApplication,
    );
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return AlertDialog(
      backgroundColor: colorScheme.surfaceContainerHigh,
      title: Text(
        'Authorize on GitHub',
        style: TextStyle(color: colorScheme.onSurface),
      ),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Enter this code on GitHub:',
            style: TextStyle(color: colorScheme.onSurfaceVariant),
          ),
          const SizedBox(height: 8),
          SelectableText(
            widget.device.userCode,
            style: TextStyle(
              color: colorScheme.onSurface,
              fontSize: AppTextSize.title,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 16),
          if (_error == null)
            Row(
              children: [
                const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    'Waiting for authorization…',
                    style: TextStyle(color: colorScheme.onSurfaceVariant),
                  ),
                ),
              ],
            )
          else
            Text(_error!, style: TextStyle(color: colorScheme.error)),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: Text(
            'Cancel',
            style: TextStyle(color: colorScheme.onSurfaceVariant),
          ),
        ),
        FilledButton.icon(
          onPressed: _openPage,
          icon: const Icon(Icons.open_in_new),
          label: const Text('Open GitHub & copy code'),
        ),
      ],
    );
  }
}
