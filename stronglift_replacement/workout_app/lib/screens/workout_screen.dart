/// Active workout screen: warmup, back-button protection,
/// and crash-safe session persistence.
library;

import 'dart:async';
import 'package:flutter/material.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/models/exercise_result.dart';
import 'package:workout_app/models/set_result.dart';
import 'package:workout_app/models/workout_session.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/services/sync_service.dart';
import 'package:workout_app/widgets/exercise_tile.dart';
import 'package:workout_app/widgets/workout_summary_dialog.dart';

class WorkoutScreen extends StatefulWidget {
  const WorkoutScreen({
    super.key,
    required this.workoutType,
    required this.exercises,
    this.savedState,
  });

  final String workoutType;
  final List<Exercise> exercises;

  /// Non-null when resuming a previously interrupted session.
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

  void _restoreFromSaved(Map<String, dynamic> s) {
    _startTime = DateTime.fromMillisecondsSinceEpoch(s['startTimeMs'] as int);
    _tapped = (s['tapped'] as List)
        .map((row) => (row as List).cast<bool>())
        .toList();
    _doneReps = (s['doneReps'] as List)
        .map((row) => (row as List).cast<int>())
        .toList();
    _warmupTapped = (s['warmupTapped'] as List).cast<bool>();
  }

  @override
  void dispose() {
    _elapsedTimer.cancel();
    super.dispose();
  }

  // ── Persistence ────────────────────────────────────────────────────────────

  Future<void> _saveActiveSession() async {
    await StorageService.instance.saveActiveSession({
      'workoutType': widget.workoutType,
      'startTimeMs': _startTime.millisecondsSinceEpoch,
      'tapped': _tapped,
      'doneReps': _doneReps,
      'warmupTapped': _warmupTapped,
    });
  }

  // ── Helpers ────────────────────────────────────────────────────────────────

  String _formatDuration(Duration d) {
    final m = d.inMinutes.remainder(60).toString().padLeft(2, '0');
    final s = d.inSeconds.remainder(60).toString().padLeft(2, '0');
    return '${d.inHours > 0 ? '${d.inHours}:' : ''}$m:$s';
  }

  bool get _allSetsCompleted => _tapped.every((row) => row.every((t) => t));

  // ── Interaction ────────────────────────────────────────────────────────────

  void _tapCircle(int exIdx, int setIdx) {
    if (_finished) return;
    setState(() {
      if (!_tapped[exIdx][setIdx]) {
        _tapped[exIdx][setIdx] = true;
      } else {
        // Subsequent taps decrement reps (records actual reps done).
        _doneReps[exIdx][setIdx] =
            (_doneReps[exIdx][setIdx] - 1).clamp(0, 999);
      }
    });
    _saveActiveSession();
  }

  void _tapWarmup(int exIdx) {
    if (_finished || _warmupTapped[exIdx]) return;
    setState(() => _warmupTapped[exIdx] = true);
    _saveActiveSession();
  }

  void _resetCircle(int exIdx, int setIdx) {
    if (_finished) return;
    setState(() {
      _tapped[exIdx][setIdx] = false;
      _doneReps[exIdx][setIdx] = widget.exercises[exIdx].reps;
    });
    _saveActiveSession();
  }

  // ── Finish / Reset ─────────────────────────────────────────────────────────

  Future<void> _confirmFinish() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: Colors.grey.shade900,
        title: const Text(
          'Finish workout?',
          style: TextStyle(color: Colors.white),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel', style: TextStyle(color: Colors.white70)),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child:
                const Text('Finish', style: TextStyle(color: Colors.greenAccent)),
          ),
        ],
      ),
    );
    if (ok == true) await _finishWorkout();
  }

  Future<void> _confirmReset() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: Colors.grey.shade900,
        title: const Text(
          'Reset workout?',
          style: TextStyle(color: Colors.white),
        ),
        content: const Text(
          'All progress will be lost.',
          style: TextStyle(color: Colors.white70),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child:
                const Text('Cancel', style: TextStyle(color: Colors.white70)),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child:
                const Text('Reset', style: TextStyle(color: Colors.redAccent)),
          ),
        ],
      ),
    );
    if (ok == true) {
      await StorageService.instance.clearActiveSession();
      if (mounted) Navigator.of(context).pop();
    }
  }

  Future<void> _finishWorkout() async {
    _elapsedTimer.cancel();
    setState(() => _finished = true);

    final endTime = DateTime.now();
    final results = <ExerciseResult>[];

    for (int i = 0; i < widget.exercises.length; i++) {
      final ex = widget.exercises[i];
      results.add(ExerciseResult(
        exercise: ex,
        sets: List.generate(
          ex.sets,
          (s) => SetResult(
            targetReps: ex.reps,
            doneReps: _tapped[i][s] ? _doneReps[i][s] : 0,
            weight: ex.weight,
          ),
        ),
      ));
    }

    final session = WorkoutSession(
      workoutType: widget.workoutType,
      startTime: _startTime,
      endTime: endTime,
      exercises: results,
    );

    final storage = StorageService.instance;
    await storage.saveSession(
      date: _startTime.toIso8601String().substring(0, 10),
      workoutType: widget.workoutType,
      durationSeconds: session.duration.inSeconds,
      succeeded: session.fullySucceeded,
      json: session.toJsonString(),
    );

    final lastDate = await storage.getLastWorkoutDate() ?? _startTime;
    await storage.applyProgression(
      succeededExercises: {
        for (int i = 0; i < widget.exercises.length; i++)
          widget.exercises[i].name: results[i].succeeded,
      },
      lastWorkoutDate: lastDate,
    );
    await storage.setLastWorkoutType(widget.workoutType);
    await storage.clearActiveSession();

    final syncResult = await _sync.writeWorkoutResult(session);

    if (!mounted) return;
    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (_) => WorkoutSummaryDialog(
        session: session,
        syncResult: syncResult,
      ),
    );
  }

  // ── Build ──────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    return PopScope(
      // canPop: true → back navigates home, workout stays in DB
      // ignore: avoid_redundant_argument_values
      canPop: true,
      child: Scaffold(
        backgroundColor: Colors.grey.shade900,
        appBar: AppBar(
          automaticallyImplyLeading: false,
          backgroundColor: Colors.grey.shade800,
          title: Text(
            'Workout ${widget.workoutType}  ·  ${_formatDuration(_elapsed)}',
            style: const TextStyle(color: Colors.white),
          ),
          actions: [
            if (!_finished)
              TextButton(
                onPressed: () => _confirmReset(),
                child: const Text(
                  'Reset',
                  style: TextStyle(color: Colors.redAccent),
                ),
              ),
            if (!_finished)
              TextButton(
                onPressed: _allSetsCompleted ? _confirmFinish : null,
                child: Text(
                  'Finish',
                  style: TextStyle(
                    color:
                        _allSetsCompleted ? Colors.greenAccent : Colors.grey,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
          ],
        ),
        body: ListView.separated(
          padding: const EdgeInsets.all(12),
          itemCount: widget.exercises.length,
          separatorBuilder: (_, _) => const SizedBox(height: 8),
          itemBuilder: (_, i) => ExerciseTile(
            exercise: widget.exercises[i],
            tapped: _tapped[i],
            doneReps: _doneReps[i],
            warmupTapped: _warmupTapped[i],
            onTapCircle: (s) => _tapCircle(i, s),
            onLongPressCircle: (s) => _resetCircle(i, s),
            onTapWarmup: () => _tapWarmup(i),
          ),
        ),
      ),
    );
  }
}
