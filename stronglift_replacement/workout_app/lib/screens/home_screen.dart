/// Home screen: auto-resumes an active session, shows done-today status.
library;

import 'dart:async';
import 'dart:developer';
import 'package:flutter/material.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/sandbox/sandbox_log.dart';
import 'package:workout_app/screens/history_screen.dart';
import 'package:workout_app/screens/manual_workout_screen.dart';
import 'package:workout_app/screens/settings_screen.dart';
import 'package:workout_app/screens/workout_screen.dart';
import 'package:workout_app/services/done_today.dart';
import 'package:workout_app/services/lock_mode.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/services/sync_status.dart';
import 'package:workout_app/services/workout_sync_service.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/sync_status_card.dart';

part 'home_screen_cards.dart';
part 'home_screen_launch.dart';
part 'home_screen_navigation.dart';
part 'home_screen_sync.dart';

/// Home screen: auto-resumes active sessions and shows done-today status.
class HomeScreen extends StatefulWidget {
  /// Creates a [HomeScreen].
  ///
  /// [syncService], [clock] and [configuredProbe] are injection seams for
  /// tests: the real sync service reaches the keystore and the network, and
  /// "synced 3h ago" is only assertable against a fixed clock.
  const HomeScreen({
    super.key,
    this.syncService,
    this.clock,
    this.configuredProbe,
    this.openWorkoutOnLaunch = true,
  });

  /// Sync service to use; defaults to a real [WorkoutSyncService].
  final WorkoutSyncService? syncService;

  /// Source of "now"; defaults to [DateTime.now].
  final DateTime Function()? clock;

  /// Whether this device has sync credentials. Defaults to asking the
  /// service itself.
  final Future<bool> Function()? configuredProbe;

  /// Whether the first load may skip home and open the workout. The app
  /// always does; tests of the home screen itself switch it off.
  final bool openWorkoutOnLaunch;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  late List<Exercise> _exercises;
  String _nextType = 'A';
  bool _loading = true;
  bool _doneToday = false;
  Map<String, dynamic>? _savedSession;

  /// Null until the first sync tick resolves, which keeps the card off the
  /// screen rather than flashing a wrong state on launch.
  SyncStatus? _syncStatus;
  bool _syncing = false;

  /// True once the first load has decided whether to open the workout, so
  /// returning from it (or from anywhere) lands on home.
  bool _hasAutoOpened = false;

  /// A synced record (manual workout, PC run) covers today. Sticky for the
  /// process: only the launch reads the backends for it.
  bool _syncedToday = false;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    final storage = StorageService.instance;
    final nextType = await storage.getNextWorkoutType();
    final exercises = await storage.getCurrentExercises(nextType);
    final saved = await storage.loadActiveSession();
    final lastDate = await storage.getLastWorkoutDate();
    final today = DateTime.now();
    final doneLocally =
        lastDate != null &&
        lastDate.year == today.year &&
        lastDate.month == today.month &&
        lastDate.day == today.day;
    final firstLoad = !_hasAutoOpened;
    _hasAutoOpened = true;
    final launch = await _decideLaunch(
      firstLoad: firstLoad,
      hasSaved: saved != null,
      doneLocally: doneLocally,
      today: today,
    );
    _syncedToday = _syncedToday || launch.syncedToday;

    if (mounted) {
      setState(() {
        _nextType = nextType;
        _exercises = exercises;
        _savedSession = saved;
        _doneToday = doneLocally || _syncedToday;
        // An auto-open keeps the spinner up and pushes with no transition,
        // so the home card is never drawn under the workout first. The
        // `_load` that runs when the workout pops clears it.
        _loading = launch.open;
      });

      // Sync in the background on every open. Deliberately not awaited: a
      // slow or dead network must not hold up the workout screen, it just
      // changes what the card says when it lands.
      unawaited(_refreshSyncStatus());

      if (launch.open) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (!mounted) return;
          unawaited(
            _openWorkout(
              resume: saved != null,
              auto: true,
              syncNotSetUp: launch.syncNotSetUp,
            ),
          );
        });
      } else {
        SandboxLog.event('home shown', {'doneToday': _doneToday});
      }
    }
  }

  /// Runs [fn] inside `setState` on behalf of this library's extensions,
  /// which cannot call the `@protected` original.
  void _applyState(VoidCallback fn) => setState(fn);

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        backgroundColor: colorScheme.surfaceContainerHigh,
        title: Text(
          'Workout Tracker',
          style: TextStyle(color: colorScheme.onSurface),
        ),
        actions: [
          IconButton(
            icon: Icon(Icons.edit_note, color: colorScheme.onSurface),
            tooltip: 'Log manual workout',
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute<void>(
                builder: (_) => const ManualWorkoutScreen(),
              ),
            ),
          ),
          IconButton(
            tooltip: 'History',
            icon: Icon(Icons.history, color: colorScheme.onSurface),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute<void>(builder: (_) => const HistoryScreen()),
            ),
          ),
          IconButton(
            tooltip: 'Settings',
            icon: Icon(Icons.settings, color: colorScheme.onSurface),
            onPressed: () async {
              await Navigator.of(context).push(
                MaterialPageRoute<void>(builder: (_) => const SettingsScreen()),
              );
              unawaited(_load());
            },
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // Above the workout card on purpose: a disconnected phone
                  // has to say so BEFORE the workout, not after it failed to
                  // count.
                  if (_syncStatus case final status?) ...[
                    SyncStatusCard(
                      status: status,
                      onRetry: () => unawaited(_refreshSyncStatus()),
                      onSetUp: _openSyncSettings,
                    ),
                    const SizedBox(height: 20),
                  ],
                  _WorkoutCard(
                    type: _nextType,
                    exercises: _exercises,
                    doneToday: _doneToday,
                    hasActiveSession: _savedSession != null,
                    onStart: _openWorkout,
                    onResume: () => _openWorkout(resume: true),
                  ),
                ],
              ),
            ),
    );
  }
}

// ── Sub-widgets ──────────────────────────────────────────────────────────────
