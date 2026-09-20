/// Active workout screen: per-rep tracking, warmup, back-button protection,
/// and crash-safe session persistence.
library;

import 'dart:async';
import 'dart:developer';
import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/material.dart';
import 'package:vibration/vibration.dart';
import 'package:workout_app/models/break_intent.dart';
import 'package:workout_app/models/break_snapshot.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/models/exercise_result.dart';
import 'package:workout_app/models/set_result.dart';
import 'package:workout_app/models/workout_session.dart';
import 'package:workout_app/sandbox/sandbox.dart';
import 'package:workout_app/sandbox/sandbox_log.dart';
import 'package:workout_app/services/break_clock.dart';
import 'package:workout_app/services/break_intent_queue.dart';
import 'package:workout_app/services/break_intent_store.dart';
import 'package:workout_app/services/break_service_controller.dart';
import 'package:workout_app/services/foreground_break_client.dart';
import 'package:workout_app/services/foreground_break_client_flutter.dart';
import 'package:workout_app/services/lock_mode.dart';
import 'package:workout_app/services/progression_sync_service.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/services/sync_service.dart';
import 'package:workout_app/services/workout_sync_service.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/break_banner.dart';
import 'package:workout_app/widgets/exercise_tile.dart';
import 'package:workout_app/widgets/workout_summary_dialog.dart';

part 'workout_screen_appbar.dart';
part 'workout_screen_body.dart';
part 'workout_screen_breaks.dart';
part 'workout_screen_dialogs.dart';
part 'workout_screen_finish.dart';
part 'workout_screen_intents.dart';
part 'workout_screen_session.dart';
part 'workout_screen_taps.dart';

/// Screen that drives an active workout session with per-rep tracking.
class WorkoutScreen extends StatefulWidget {
  /// Creates a [WorkoutScreen].
  const WorkoutScreen({
    required this.workoutType,
    required this.exercises,
    super.key,
    this.savedState,
    this.breakClient,
  });

  /// 'A' or 'B' — used for history and progression.
  final String workoutType;

  /// Ordered list of exercises for this session.
  final List<Exercise> exercises;

  /// Serialized state to restore (crash-recovery); null for a fresh session.
  final Map<String, dynamic>? savedState;

  /// Foreground-service client, injectable so tests can drive the notification
  /// path on a host that has no foreground service. Null means the real one.
  @visibleForTesting
  final ForegroundBreakClient? breakClient;

  @override
  State<WorkoutScreen> createState() => _WorkoutScreenState();
}

class _WorkoutScreenState extends State<WorkoutScreen> {
  late List<List<bool>> _tapped;
  late List<List<int>> _doneReps;
  late List<bool> _warmupTapped;
  late DateTime _startTime;
  late Timer _elapsedTimer;
  Duration _elapsed = Duration.zero;

  Map<String, ExerciseState> _exerciseStates = {};

  // Break state. The deadline is the source of truth: `_breakClock` is what
  // survives the app being backgrounded, and everything else is derived from
  // it. See services/break_clock.dart for why a tick counter could not be.
  BreakClock? _breakClock;
  Timer? _breakTimer;
  String _breakLabel = '';
  int _breakForExIdx = -1;
  int _breakForSetIdx = -1; // -1 = warmup break

  /// A break restored as already-expired, awaiting its cue after first frame.
  BreakClock? _expiredBreak;

  int get _breakRemaining => _breakClock?.remainingSecsAt(DateTime.now()) ?? 0;

  int get _breakDurationSecs => _breakClock?.durationSecs ?? 0;

  bool get _inBreak => _breakRemaining > 0;

  late final AppLifecycleListener _lifecycle;
  late final BreakServiceController _breaks;
  final _audio = AudioPlayer();
  final _sync = SyncService();
  bool _finished = false;

  @override
  void initState() {
    super.initState();
    final saved = widget.savedState;
    if (saved != null) {
      _restoreFromSaved(saved);
    } else {
      _initFresh();
    }
    _elapsedTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      setState(() => _elapsed = DateTime.now().difference(_startTime));
    });
    // Coming back to the foreground is the one moment the countdown is
    // guaranteed to be stale: ticks stop while the app is away, and the clock
    // has to be re-read before the user sees a frame.
    _lifecycle = AppLifecycleListener(onResume: _onResumed);
    _breaks = BreakServiceController(
      widget.breakClient ?? FlutterForegroundBreakClient(),
      BreakIntentQueue(PrefsBreakIntentStore()),
    );
    unawaited(_loadExerciseStates());
    WidgetsBinding.instance.addPostFrameCallback((_) {
      unawaited(_settleExpiredBreak());
      unawaited(_startBreakService());
    });
  }

  void _initFresh() {
    _startTime = DateTime.now();
    _tapped = List.generate(
      widget.exercises.length,
      (i) => List.filled(widget.exercises[i].sets, false),
    );
    _doneReps = List.generate(
      widget.exercises.length,
      (i) => List.filled(widget.exercises[i].sets, widget.exercises[i].reps),
    );
    _warmupTapped = List.filled(widget.exercises.length, false);
  }

  Future<void> _loadExerciseStates() async {
    final states = await StorageService.instance.getAllExerciseStates();
    if (mounted) {
      setState(() {
        _exerciseStates = {for (final s in states) s.name: s};
      });
    }
  }

  @override
  void dispose() {
    _elapsedTimer.cancel();
    _breakTimer?.cancel();
    _lifecycle.dispose();
    // Deliberately NOT stopping the break service here. The back button pops
    // this screen while the workout carries on in the database, and stopping
    // the service on dispose killed the countdown and the notification with
    // it -- silently putting the user back on the bug this feature fixes.
    // The service is stopped only by Finish, by Reset, and by the stale-service
    // reaper in main() for the case where neither ever happens.
    unawaited(_audio.dispose());
    super.dispose();
  }

  // ── Persistence ────────────────────────────────────────────────────────────

  /// The most recent remote active-session write, so the clear-on-finish can
  /// be ordered after it instead of racing it.
  Future<void> _lastActiveSessionPush = Future.value();

  // ── Helpers ────────────────────────────────────────────────────────────────

  bool get _allSetsCompleted => _tapped.every((row) => row.every((t) => t));

  /// Runs [fn] inside `setState` on behalf of this library's extensions.
  ///
  /// `setState` is `@protected`, so an extension cannot call it directly. This
  /// shim is the one seam through which `workout_screen_breaks.dart` and
  /// `workout_screen_taps.dart` mutate state; keeping it named makes those
  /// writes greppable from here.
  void _applyBreakState(VoidCallback fn) => setState(fn);

  // ── Finish / Reset ─────────────────────────────────────────────────────────

  /// Stops the timers, marks the workout finished, and persists everything.
  ///
  /// Only the `setState` lives here — `setState` is `@protected` and cannot be
  /// called from an extension, so the rest is in [_persistFinishedWorkout].
  Future<void> _finishWorkout() async {
    SandboxLog.event('workout finish', {'type': widget.workoutType});
    _elapsedTimer.cancel();
    _breakTimer?.cancel();
    // Before the state flips: the service must not outlive the workout, and
    // with stopWithTask="false" nothing else will ever stop it.
    await _breaks.stop();
    setState(() => _finished = true);
    await _persistFinishedWorkout();
  }

  // ── Build ──────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    return PopScope(
      // In lock mode the workout IS the lock: popping back to the home screen
      // would leave a fullscreen window holding the X grab with no way to
      // finish, so the route is pinned until the workout is finished or reset.
      // Outside lock mode the back button behaves exactly as it always has.
      canPop: !lockModeEnabled,
      child: Scaffold(
        appBar: _WorkoutAppBar(
          title:
              'Workout ${widget.workoutType}  ·  ${_formatDuration(_elapsed)}',
          finished: _finished,
          allSetsCompleted: _allSetsCompleted,
          onReset: () => unawaited(_confirmReset()),
          onFinish: () => unawaited(_confirmFinish()),
        ),
        body: _WorkoutBody(
          exercises: widget.exercises,
          exerciseStates: _exerciseStates,
          tapped: _tapped,
          doneReps: _doneReps,
          warmupTapped: _warmupTapped,
          inBreak: _inBreak,
          breakRemaining: _breakRemaining,
          breakLabel: _breakLabel,
          onSkipBreak: _skipBreak,
          onTapCircle: _tapCircle,
          onLongPressCircle: _resetCircle,
          onTapWarmup: _tapWarmup,
          onThresholdChanged: (name, success, fail) =>
              unawaited(_onThresholdChanged(name, success, fail)),
        ),
      ),
    );
  }
}
