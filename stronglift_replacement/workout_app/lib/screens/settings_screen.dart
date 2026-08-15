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

part 'settings_screen_actions.dart';
part 'settings_screen_exercise_sections.dart';
part 'settings_screen_rows.dart';
part 'settings_screen_sections.dart';
part 'settings_screen_thresholds.dart';
part 'settings_screen_widget.dart';

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
    await _pushSyncSettingsScreen();
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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: _SettingsAppBar(
        loading: _loading,
        onReset: () => unawaited(_resetToDefaults()),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                _WeightsSection(
                  orderedNames: _orderedNames,
                  weights: _weights,
                  onWeightChanged: _onWeightChanged,
                ),
                const SizedBox(height: 20),
                _RepsSection(
                  orderedNames: _orderedNames,
                  reps: _reps,
                  onRepsChanged: _onRepsChanged,
                ),
                const SizedBox(height: 20),
                _ThresholdsSection(
                  orderedNames: _orderedNames,
                  successThresholds: _successThresholds,
                  failThresholds: _failThresholds,
                  onThresholdChanged: (name, success, fail) =>
                      unawaited(_onThresholdChanged(name, success, fail)),
                ),
                const SizedBox(height: 20),
                _SyncSection(
                  progressionStatus: _progressionStatus,
                  onOpenSyncSettings: () => unawaited(_openSyncSettings()),
                  onOpenGitHubMirror: () => unawaited(_openGitHubMirror()),
                ),
                const SizedBox(height: 20),
                _OfflineBackupSection(
                  storageGranted: _storageGranted,
                  onGrantStorage: _grantStorage,
                ),
              ],
            ),
    );
  }
}
