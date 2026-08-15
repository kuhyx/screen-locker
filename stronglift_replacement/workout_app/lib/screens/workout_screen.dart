/// Active workout screen: per-rep tracking, warmup, back-button protection,
/// and crash-safe session persistence.
library;

import 'dart:async';
import 'dart:developer';
import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/material.dart';
import 'package:vibration/vibration.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/models/exercise_result.dart';
import 'package:workout_app/models/set_result.dart';
import 'package:workout_app/models/workout_session.dart';
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
part 'workout_screen_session.dart';

const _successBreakSecs = 180; // 3 min after successful set
const _failBreakSecs = 300; // 5 min after failed set
const _warmupBreakSecs = 180; // 3 min after warmup

/// Screen that drives an active workout session with per-rep tracking.
class WorkoutScreen extends StatefulWidget {
  /// Creates a [WorkoutScreen].
  const WorkoutScreen({
    required this.workoutType,
    required this.exercises,
    super.key,
    this.savedState,
  });

  /// 'A' or 'B' — used for history and progression.
  final String workoutType;

  /// Ordered list of exercises for this session.
  final List<Exercise> exercises;

  /// Serialized state to restore (crash-recovery); null for a fresh session.
  final Map<String, dynamic>? savedState;

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

  // Break state
  int _breakRemaining = 0;
  int _breakDurationSecs = 0;
  DateTime? _breakStartTime;
  Timer? _breakTimer;
  String _breakLabel = '';
  int _breakForExIdx = -1;
  int _breakForSetIdx = -1; // -1 = warmup break

  bool get _inBreak => _breakRemaining > 0;

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
    unawaited(_loadExerciseStates());
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
    unawaited(_audio.dispose());
    super.dispose();
  }

  // ── Persistence ────────────────────────────────────────────────────────────

  /// The most recent remote active-session write, so the clear-on-finish can
  /// be ordered after it instead of racing it.
  Future<void> _lastActiveSessionPush = Future.value();

  // ── Helpers ────────────────────────────────────────────────────────────────

  bool get _allSetsCompleted => _tapped.every((row) => row.every((t) => t));

  // ── Interaction ────────────────────────────────────────────────────────────

  void _tapCircle(int exIdx, int setIdx) {
    if (_finished) return;

    final wasNotTapped = !_tapped[exIdx][setIdx];
    if (wasNotTapped && _inBreak) return;

    setState(() {
      if (wasNotTapped) {
        _tapped[exIdx][setIdx] = true;
      } else {
        _doneReps[exIdx][setIdx] = (_doneReps[exIdx][setIdx] - 1).clamp(0, 999);
        _recomputeBreakIfNeeded(exIdx, setIdx);
      }
    });

    if (wasNotTapped) {
      final rest = _restAfterSet(exIdx, setIdx);
      if (rest != null) {
        _startBreak(rest.seconds, rest.label, exIdx, setIdx);
      }
    }

    // Only a newly-completed set moves the workout forward; a rep decrement
    // re-enters here and must not cost a remote write.
    unawaited(_saveActiveSession(toFirebase: wasNotTapped));
  }

  void _tapWarmup(int exIdx) {
    if (_finished || _warmupTapped[exIdx]) return;
    setState(() => _warmupTapped[exIdx] = true);
    if (!_inBreak) {
      _startBreak(_warmupBreakSecs, 'Warmup rest (3 min)', exIdx, -1);
    }
    unawaited(_saveActiveSession(toFirebase: true));
  }

  void _resetCircle(int exIdx, int setIdx) {
    if (_finished) return;
    setState(() {
      _tapped[exIdx][setIdx] = false;
      _doneReps[exIdx][setIdx] = widget.exercises[exIdx].reps;
    });
    if (_breakForExIdx == exIdx && _breakForSetIdx == setIdx) {
      _cancelBreak();
    }
    unawaited(_saveActiveSession());
  }

  /// Runs [fn] inside `setState` on behalf of the break/threshold extensions.
  ///
  /// `setState` is `@protected`, so an extension cannot call it directly. This
  /// shim is the one seam through which `workout_screen_breaks.dart` mutates
  /// state; keeping it named makes those writes greppable from here.
  void _applyBreakState(VoidCallback fn) => setState(fn);

  // ── Finish / Reset ─────────────────────────────────────────────────────────

  /// Stops the timers, marks the workout finished, and persists everything.
  ///
  /// Only the `setState` lives here — `setState` is `@protected` and cannot be
  /// called from an extension, so the rest is in [_persistFinishedWorkout].
  Future<void> _finishWorkout() async {
    _elapsedTimer.cancel();
    _breakTimer?.cancel();
    setState(() => _finished = true);
    await _persistFinishedWorkout();
  }

  // ── Build ──────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    return PopScope(
      // Explicit `canPop: true` makes it clear this scope never blocks the back
      // button — a future reader must not assume the default silently.
      // ignore: avoid_redundant_argument_values
      canPop: true,
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
