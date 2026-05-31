/// Active workout screen: per-rep breaks, warmup, back-button protection,
/// and crash-safe session persistence.
library;

import 'dart:async';
import 'package:flutter/material.dart';
import 'package:audioplayers/audioplayers.dart';
import 'package:vibration/vibration.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/models/exercise_result.dart';
import 'package:workout_app/models/set_result.dart';
import 'package:workout_app/models/workout_session.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/services/sync_service.dart';
import 'package:workout_app/widgets/break_banner.dart';
import 'package:workout_app/widgets/exercise_tile.dart';
import 'package:workout_app/widgets/workout_summary_dialog.dart';

const _successBreakSecs = 180; // 3 min after successful rep
const _failBreakSecs = 300; // 5 min after failed rep
const _warmupBreakSecs = 180; // 3 min after warmup

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

  // Break state
  int _breakRemaining = 0;
  int _breakDurationSecs = 0;
  DateTime? _breakStartTime;
  Timer? _breakTimer;
  String _breakLabel = '';
  int _breakForExIdx = -1;
  int _breakForRepIdx = -1; // -1 = warmup break

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

    final breakEndMs = s['breakEndMs'] as int? ?? 0;
    final breakDur = s['breakDurationSecs'] as int? ?? 0;
    if (breakEndMs > 0 && breakDur > 0) {
      final endTime = DateTime.fromMillisecondsSinceEpoch(breakEndMs);
      final remaining = endTime.difference(DateTime.now()).inSeconds;
      if (remaining > 0) {
        _breakForExIdx = s['breakForExIdx'] as int? ?? -1;
        _breakForRepIdx = s['breakForRepIdx'] as int? ?? -1;
        _breakLabel = s['breakLabel'] as String? ?? 'Rest';
        _breakDurationSecs = breakDur;
        _breakStartTime = endTime.subtract(Duration(seconds: breakDur));
        _breakRemaining = remaining;
        _breakTimer = Timer.periodic(const Duration(seconds: 1), _tickBreak);
      }
    }
  }

  @override
  void dispose() {
    _elapsedTimer.cancel();
    _breakTimer?.cancel();
    _audio.dispose();
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
      'breakForExIdx': _breakForExIdx,
      'breakForRepIdx': _breakForRepIdx,
      'breakLabel': _breakLabel,
      'breakDurationSecs': _breakDurationSecs,
      'breakEndMs': _breakStartTime != null
          ? _breakStartTime!
              .add(Duration(seconds: _breakDurationSecs))
              .millisecondsSinceEpoch
          : 0,
    });
  }

  // ── Helpers ────────────────────────────────────────────────────────────────

  String _formatDuration(Duration d) {
    final m = d.inMinutes.remainder(60).toString().padLeft(2, '0');
    final s = d.inSeconds.remainder(60).toString().padLeft(2, '0');
    return '${d.inHours > 0 ? '${d.inHours}:' : ''}$m:$s';
  }

  bool get _allSetsCompleted => _tapped.every((row) => row.every((t) => t));

  bool _isLastUntappedCircle(int exIdx, int repIdx) {
    int remaining = 0;
    for (int i = 0; i < widget.exercises.length; i++) {
      for (int s = 0; s < widget.exercises[i].sets; s++) {
        if (!_tapped[i][s]) remaining++;
      }
    }
    return remaining == 1;
  }

  // ── Interaction ────────────────────────────────────────────────────────────

  void _tapCircle(int exIdx, int repIdx) {
    if (_finished) return;

    final wasNotTapped = !_tapped[exIdx][repIdx];
    if (wasNotTapped && _inBreak) return;

    setState(() {
      if (wasNotTapped) {
        _tapped[exIdx][repIdx] = true;
      } else {
        // Subsequent taps decrement reps (records actual reps done).
        _doneReps[exIdx][repIdx] =
            (_doneReps[exIdx][repIdx] - 1).clamp(0, 999);
        _recomputeBreakIfNeeded(exIdx, repIdx);
      }
    });

    if (wasNotTapped) {
      final isLast = _isLastUntappedCircle(exIdx, repIdx);
      if (!isLast) {
        final succeeded =
            _doneReps[exIdx][repIdx] >= widget.exercises[exIdx].reps;
        _startBreak(
          succeeded ? _successBreakSecs : _failBreakSecs,
          succeeded
              ? 'Rest (3 min — well done!)'
              : 'Rest (5 min — keep going!)',
          exIdx,
          repIdx,
        );
      }
    }

    _saveActiveSession();
  }

  void _tapWarmup(int exIdx) {
    if (_finished || _warmupTapped[exIdx]) return;
    setState(() => _warmupTapped[exIdx] = true);
    if (!_inBreak) {
      _startBreak(_warmupBreakSecs, 'Warmup rest (3 min)', exIdx, -1);
    }
    _saveActiveSession();
  }

  void _resetCircle(int exIdx, int repIdx) {
    if (_finished) return;
    setState(() {
      _tapped[exIdx][repIdx] = false;
      _doneReps[exIdx][repIdx] = widget.exercises[exIdx].reps;
    });
    if (_breakForExIdx == exIdx && _breakForRepIdx == repIdx) {
      _cancelBreak();
    }
    _saveActiveSession();
  }

  // ── Break management ───────────────────────────────────────────────────────

  void _startBreak(int secs, String label, int exIdx, int repIdx) {
    _breakTimer?.cancel();
    setState(() {
      _breakDurationSecs = secs;
      _breakRemaining = secs;
      _breakLabel = label;
      _breakForExIdx = exIdx;
      _breakForRepIdx = repIdx;
      _breakStartTime = DateTime.now();
    });
    _breakTimer = Timer.periodic(const Duration(seconds: 1), _tickBreak);
  }

  void _tickBreak(Timer t) {
    setState(() => _breakRemaining--);
    if (_breakRemaining <= 0) {
      t.cancel();
      _onBreakFinished();
    }
  }

  void _cancelBreak() {
    _breakTimer?.cancel();
    setState(() {
      _breakRemaining = 0;
      _breakForExIdx = -1;
      _breakForRepIdx = -1;
      _breakStartTime = null;
    });
  }

  void _skipBreak() {
    _cancelBreak();
    _saveActiveSession();
  }

  /// If the user reduces reps on the rep that triggered the current break,
  /// switch from 3-min to 5-min (or vice versa).
  void _recomputeBreakIfNeeded(int exIdx, int repIdx) {
    if (!_inBreak) return;
    if (_breakForExIdx != exIdx || _breakForRepIdx != repIdx) return;
    if (_breakForRepIdx == -1) return; // warmup break, never recompute

    final succeeded =
        _doneReps[exIdx][repIdx] >= widget.exercises[exIdx].reps;
    final newDuration = succeeded ? _successBreakSecs : _failBreakSecs;
    if (newDuration == _breakDurationSecs) return;

    final elapsed = DateTime.now().difference(_breakStartTime!).inSeconds;
    final newRemaining = (newDuration - elapsed).clamp(0, newDuration);

    _breakDurationSecs = newDuration;
    _breakRemaining = newRemaining;
    _breakLabel =
        succeeded ? 'Rest (3 min — well done!)' : 'Rest (5 min — keep going!)';
  }

  Future<void> _onBreakFinished() async {
    await _audio.play(AssetSource('sounds/break_end.mp3')).catchError((_) {});
    final hasVibrator = await Vibration.hasVibrator() == true;
    if (hasVibrator) Vibration.vibrate(duration: 800);
    setState(() {
      _breakForExIdx = -1;
      _breakForRepIdx = -1;
      _breakStartTime = null;
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
            child:
                const Text('Cancel', style: TextStyle(color: Colors.white70)),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text(
              'Finish',
              style: TextStyle(color: Colors.greenAccent),
            ),
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
    _breakTimer?.cancel();
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
        body: Column(
          children: [
            if (_inBreak)
              BreakBanner(
                breakRemaining: _breakRemaining,
                breakLabel: _breakLabel,
                onSkip: _skipBreak,
              ),
            Expanded(
              child: ListView.separated(
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
          ],
        ),
      ),
    );
  }
}
