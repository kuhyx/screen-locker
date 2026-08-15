/// Settings screen: per-exercise streak thresholds and manual weight
/// overrides, plus links to the sync surfaces.
///
/// "Sync settings" is the shared `sync_settings_ui` package (Firebase sync;
/// no Backup section -- see the class doc on [SettingsScreen] for why).
/// "Advanced sync (GitHub)" stays app-local ([GitHubMirrorScreen]) because
/// the shared package has no GitHub surface at all.
library;

import 'dart:async';
import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:sync_settings_ui/sync_settings_ui.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/models/workout_plan.dart';
import 'package:workout_app/screens/github_mirror_screen.dart';
import 'package:workout_app/services/backup_service.dart';
import 'package:workout_app/services/firebase_backend.dart';
import 'package:workout_app/services/google_sign_in_backend.dart';
import 'package:workout_app/services/progression_sync_service.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/ui/theme.dart';

part 'settings_screen_rows.dart';
part 'settings_screen_thresholds.dart';

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

  bool _storageGranted = false;

  // Set after a Sync settings visit restores progression, so the banner
  // persists until the user looks back at the screen -- mirrors the pattern
  // every app-local sync status field in this migration already used.
  String? _progressionStatus;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
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

  @override
  void dispose() {
    for (final t in _weightTimers.values) {
      t.cancel();
    }
    for (final t in _repsTimers.values) {
      t.cancel();
    }
    super.dispose();
  }

  Future<void> _load() async {
    final states = await StorageService.instance.getAllExerciseStates();
    if (!mounted) return;
    setState(() {
      for (final s in states) {
        _successThresholds[s.name] = s.successThreshold;
        _failThresholds[s.name] = s.failThreshold;
        _weights[s.name] = s.weight;
        _reps[s.name] = s.reps;
      }
      _loading = false;
    });
  }

  /// Pushes the shared Sync settings screen, then pulls progression once it
  /// pops -- covering both "connected just now" and "disconnected/no-op".
  ///
  /// Not hooked into the connect flow itself: `SyncSettingsScreen` has no
  /// post-connect callback, and [ProgressionSyncService.pullProgression]
  /// already self-gates (returns immediately with no account, and refuses to
  /// overwrite local state once [StorageService.hasSyncedProgression] is
  /// true), so calling it unconditionally on pop is safe and simpler than
  /// threading a callback through the shared screen's Firebase closures.
  /// [ProgressionSyncService.pushProgression]'s own guard (never overwrite
  /// remote progression from an install that hasn't pulled yet) is the actual
  /// safety net against the reinstall-then-finish-a-workout race this
  /// mirrors; this call is a convenience that restores progression
  /// immediately instead of waiting for the next app launch, which also
  /// pulls unconditionally at startup.
  Future<void> _openSyncSettings() async {
    await Navigator.of(context).push<void>(
      MaterialPageRoute(
        builder: (_) => SyncSettingsScreen(
          accountLoader: widget.accountLoader ?? loadAccount,
          accountSaver: widget.accountSaver ?? saveAccount,
          accountClearer: widget.accountClearer ?? clearAccount,
          sessionProbe: widget.sessionProbe ?? isFirebaseConfigured,
          firebaseFactory: widget.firebaseFactory ?? openFirebase,
          googleFirebaseFactory:
              widget.googleFirebaseFactory ?? openFirebaseWithGoogle,
          googleAvailable: widget.googleAvailable ?? googleSignInSupported,
        ),
      ),
    );
    if (!mounted) return;
    final restored =
        await (widget.progressionPuller ??
            ProgressionSyncService().pullProgression)();
    if (!mounted) return;
    if (restored.changed) {
      setState(
        () => _progressionStatus =
            'Restored ${restored.count} exercise(s) from Firebase.',
      );
      await _load();
    }
  }

  Future<void> _openGitHubMirror() async {
    await Navigator.of(context).push<void>(
      MaterialPageRoute(
        builder: (_) => GitHubMirrorScreen(httpClient: widget.httpClient),
      ),
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
                if (_progressionStatus != null) ...[
                  Text(
                    _progressionStatus!,
                    style: TextStyle(
                      color: colorScheme.onSurfaceVariant,
                      fontSize: AppTextSize.caption,
                    ),
                  ),
                  const SizedBox(height: 8),
                ],
                Card(
                  margin: EdgeInsets.zero,
                  color: colorScheme.surfaceContainerHigh,
                  child: Column(
                    children: [
                      ListTile(
                        title: Text(
                          'Sync settings',
                          style: TextStyle(color: colorScheme.onSurface),
                        ),
                        subtitle: Text(
                          'Firebase sync',
                          style: TextStyle(
                            color: colorScheme.onSurfaceVariant,
                          ),
                        ),
                        trailing: Icon(
                          Icons.chevron_right,
                          color: colorScheme.onSurfaceVariant,
                        ),
                        onTap: () => unawaited(_openSyncSettings()),
                      ),
                      Divider(
                        height: 1,
                        color: colorScheme.onSurfaceVariant.withValues(
                          alpha: 0.2,
                        ),
                      ),
                      ListTile(
                        title: Text(
                          'Advanced sync (GitHub)',
                          style: TextStyle(color: colorScheme.onSurface),
                        ),
                        subtitle: Text(
                          'Cutover mirror — not recommended',
                          style: TextStyle(
                            color: colorScheme.onSurfaceVariant,
                          ),
                        ),
                        trailing: Icon(
                          Icons.chevron_right,
                          color: colorScheme.onSurfaceVariant,
                        ),
                        onTap: () => unawaited(_openGitHubMirror()),
                      ),
                    ],
                  ),
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
