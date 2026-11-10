/// Settings screen: manual weight and rep overrides, each exercise's
/// settings sheet, plus links to the sync surfaces.
///
/// "Sync settings" is the shared `sync_settings_ui` package (Firebase sync;
/// no Backup section -- see [SettingsScreen]). "Advanced sync (GitHub)" stays
/// app-local ([GitHubMirrorScreen]): the shared package has no GitHub surface.
library;

import 'dart:async';
import 'dart:developer';
import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:sync_settings_ui/sync_settings_ui.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/models/workout_plan.dart';
import 'package:workout_app/sandbox/sandbox.dart';
import 'package:workout_app/sandbox/sandbox_log.dart';
import 'package:workout_app/screens/github_mirror_screen.dart';
import 'package:workout_app/services/backup_service.dart';
import 'package:workout_app/services/firebase_backend.dart';
import 'package:workout_app/services/google_sign_in_backend.dart';
import 'package:workout_app/services/pc_pairing.dart';
import 'package:workout_app/services/progression_sync_service.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/data_transfer_buttons.dart';
import 'package:workout_app/widgets/exercise_settings_sheet.dart';
import 'package:workout_app/widgets/runnerup_import_badge.dart';

part 'settings_screen_actions.dart';
part 'settings_screen_deload.dart';
part 'settings_screen_exercise_list.dart';
part 'settings_screen_exercise_sections.dart';
part 'settings_screen_pc_link.dart';
part 'settings_screen_rows.dart';
part 'settings_screen_sandbox.dart';
part 'settings_screen_sections.dart';
part 'settings_screen_sound.dart';
part 'settings_screen_widget.dart';

class _SettingsScreenState extends State<SettingsScreen> {
  bool _loading = true;

  final Map<String, ExerciseState> _states = {};
  final Map<String, double> _weights = {};
  final Map<String, int> _reps = {};

  // Debounced saves, so a tap does not reset streaks on every step.
  final Map<String, Timer> _weightTimers = {};
  final Map<String, Timer> _repsTimers = {};

  bool _storageGranted = false;
  bool _soundEnabled = true;

  // Set after a Sync settings visit restores progression; the banner stays.
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

  /// Opens the system page for MANAGE_EXTERNAL_STORAGE. The ONLY caller of
  /// [BackupService.requestStoragePermission]: startup used to, and dumped
  /// the user in system Settings on every launch.
  Future<void> _grantStorage() async {
    final granted =
        await (widget.storageRequester ??
            BackupService.instance.requestStoragePermission)();
    if (!mounted) return;
    setState(() => _storageGranted = granted);
  }

  @override
  void dispose() {
    for (final t in [..._weightTimers.values, ..._repsTimers.values]) {
      t.cancel();
    }
    super.dispose();
  }

  Future<void> _load() async {
    final storage = StorageService.instance;
    final states = await storage.getAllExerciseStates();
    final sound = await storage.getSoundEnabled();
    if (!mounted) return;
    setState(() {
      _soundEnabled = sound;
      for (final s in states) {
        _states[s.name] = s;
        _weights[s.name] = s.weight;
        _reps[s.name] = s.reps;
      }
      _loading = false;
    });
  }

  /// Pushes the shared Sync settings screen, then pulls progression once it
  /// pops -- covering both "connected just now" and "disconnected/no-op".
  ///
  /// Not hooked into the connect flow: `SyncSettingsScreen` has no
  /// post-connect callback, and [ProgressionSyncService.pullProgression]
  /// already self-gates (no account => immediate return; never overwrites
  /// local state once [StorageService.hasSyncedProgression] is true), so an
  /// unconditional call on pop is safe. The push-side guard (never overwrite
  /// remote progression from an install that has not pulled yet) is the real
  /// safety net against the reinstall-then-finish-a-workout race; this call
  /// only restores progression now instead of at the next launch, which also
  /// pulls unconditionally.
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

  void _setSound(bool enabled) {
    setState(() => _soundEnabled = enabled);
    unawaited(StorageService.instance.setSoundEnabled(enabled: enabled));
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

  /// Opens [state]'s settings sheet. Every edit is saved as it happens, the
  /// same as from the workout tile; once the sheet closes the result goes to
  /// Firebase, so a reinstall before the next workout keeps it.
  Future<void> _openExercise(ExerciseState state) async {
    var edited = false;
    await showExerciseSettingsSheet(
      context,
      state: state,
      onChanged: (updated) {
        edited = true;
        setState(() => _states[updated.name] = updated);
        unawaited(StorageService.instance.setExerciseSettings(updated));
      },
      onDeload: () async {
        final deloaded = await _deload(state.name);
        if (deloaded != null) edited = true;
        return deloaded;
      },
    );
    if (!edited) return;
    final pushed =
        await (widget.progressionPusher ??
            ProgressionSyncService().pushProgression)();
    if (!mounted || pushed.changed) return;
    _flagUnsynced(pushed.reason);
  }

  /// Shows a deloaded target everywhere this screen holds a copy of it.
  ///
  /// Here rather than in `settings_screen_deload.dart` because `setState` is
  /// `@protected` and unreachable from an extension.
  void _showDeloaded(ExerciseState next) => setState(() {
    _states[next.name] = next;
    _weights[next.name] = next.weight;
    _reps[next.name] = next.reps;
  });

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
                _ExercisesSection(
                  orderedNames: _orderedNames,
                  states: _states,
                  onOpen: (s) => unawaited(_openExercise(s)),
                ),
                const SizedBox(height: 20),
                _SoundSection(enabled: _soundEnabled, onChanged: _setSound),
                const SizedBox(height: 20),
                _SyncSection(
                  progressionStatus: _progressionStatus,
                  onOpenSyncSettings: () => unawaited(_openSyncSettings()),
                  onOpenGitHubMirror: () => unawaited(_openGitHubMirror()),
                ),
                const SizedBox(height: 20),
                _PcLinkSection(pairingLoader: widget.pcPairingLoader),
                const SizedBox(height: 20),
                _OfflineBackupSection(
                  storageGranted: _storageGranted,
                  onGrantStorage: _grantStorage,
                ),
                if (Sandbox.enabled) ...[
                  const SizedBox(height: 20),
                  const _SandboxSection(),
                ],
              ],
            ),
    );
  }
}
