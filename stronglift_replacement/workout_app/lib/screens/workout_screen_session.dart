// Session persistence and restore for the active workout screen.
//
// A `part` rather than a separate library so the extension keeps reaching the
// private `_WorkoutScreenState` fields. Everything here is deliberately
// setState-free: `setState` is `@protected` and cannot be called from an
// extension, so the state-mutating wrappers stay in the class.
part of 'workout_screen.dart';

/// Save/restore of the crash-recovery session blob and break bookkeeping.
extension _WorkoutScreenSession on _WorkoutScreenState {
  /// Rebuilds in-memory session state from a persisted [s] blob.
  ///
  /// Restores a break only when its recorded end time is still in the future,
  /// so a session resumed after the rest period simply has no break running.
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
        _breakForSetIdx = s['breakForSetIdx'] as int? ?? -1;
        _breakLabel = s['breakLabel'] as String? ?? 'Rest';
        _breakDurationSecs = breakDur;
        _breakStartTime = endTime.subtract(Duration(seconds: breakDur));
        _breakRemaining = remaining;
        _breakTimer = Timer.periodic(const Duration(seconds: 1), _tickBreak);
      }
    }
  }

  /// Persists the active session locally, and to Firebase when [toFirebase].
  ///
  /// [toFirebase] is false on the per-tap paths (rep decrements, break
  /// bookkeeping) and true only on set/warmup completion. `saveActiveSession`
  /// runs on every tap, and a Firebase write per tap is exactly the traffic the
  /// sync revision cache exists to avoid — so the remote copy is debounced to
  /// the events that actually change which set the user is standing on.
  Future<void> _saveActiveSession({bool toFirebase = false}) async {
    final data = _activeSessionData();
    await StorageService.instance.saveActiveSession(data);
    if (!toFirebase) return;
    _lastActiveSessionPush = ProgressionSyncService()
        .pushActiveSession(data)
        .then((result) {
          if (!result.changed) {
            debugPrint(
              'WorkoutScreen: active session not shared — ${result.reason}',
            );
          }
        });
    await _lastActiveSessionPush;
  }

  /// The serializable snapshot of the in-progress workout.
  Map<String, dynamic> _activeSessionData() {
    return {
      'workoutType': widget.workoutType,
      'startTimeMs': _startTime.millisecondsSinceEpoch,
      'tapped': _tapped,
      'doneReps': _doneReps,
      'warmupTapped': _warmupTapped,
      'breakForExIdx': _breakForExIdx,
      'breakForSetIdx': _breakForSetIdx,
      'breakLabel': _breakLabel,
      'breakDurationSecs': _breakDurationSecs,
      'breakEndMs': _breakStartTime != null
          ? _breakStartTime!
                .add(Duration(seconds: _breakDurationSecs))
                .millisecondsSinceEpoch
          : 0,
    };
  }

  /// When the user decrements reps on the set that triggered the current break,
  /// switch between 3-min (success) and 5-min (fail) durations.
  void _recomputeBreakIfNeeded(int exIdx, int setIdx) {
    if (!_inBreak) return;
    if (_breakForExIdx != exIdx || _breakForSetIdx != setIdx) return;
    if (_breakForSetIdx == -1) return; // warmup break, never recompute

    final succeeded = _doneReps[exIdx][setIdx] >= widget.exercises[exIdx].reps;
    final newDuration = succeeded ? _successBreakSecs : _failBreakSecs;
    if (newDuration == _breakDurationSecs) return;

    final elapsed = DateTime.now().difference(_breakStartTime!).inSeconds;
    final newRemaining = (newDuration - elapsed).clamp(0, newDuration);

    _breakDurationSecs = newDuration;
    _breakRemaining = newRemaining;
    _breakLabel = succeeded
        ? 'Rest (3 min — well done!)'
        : 'Rest (5 min — keep going!)';
  }

  /// True when [setIdx] is the last untapped set of exercise [exIdx].
  bool _isLastSetOfExercise(int exIdx, int setIdx) {
    final sets = widget.exercises[exIdx].sets;
    for (var s = 0; s < sets; s++) {
      if (s != setIdx && !_tapped[exIdx][s]) return false;
    }
    return true;
  }

  /// The rest period earned by just completing set [setIdx] of [exIdx].
  ///
  /// Null on the exercise's final set — the user moves straight on rather than
  /// resting inside an exercise they have finished.
  _Rest? _restAfterSet(int exIdx, int setIdx) {
    if (_isLastSetOfExercise(exIdx, setIdx)) return null;
    final succeeded = _doneReps[exIdx][setIdx] >= widget.exercises[exIdx].reps;
    return succeeded
        ? const _Rest(_successBreakSecs, 'Rest (3 min — well done!)')
        : const _Rest(_failBreakSecs, 'Rest (5 min — keep going!)');
  }

  /// Plays the sound and haptic that tell the user the rest period is over.
  Future<void> _playBreakEndCue() async {
    await _audio
        .play(AssetSource('sounds/break_end.mp3'))
        .catchError((Object error) {
          // Never fatal: a missing audio route must not interrupt the workout.
          // But it is the break-end cue, so a silent failure looks like the
          // timer itself is broken.
          debugPrint('WorkoutApp: break-end sound failed to play ($error).');
        });
    if (await Vibration.hasVibrator()) {
      // Android/iOS-only: hasVibrator() returns false on the Linux test host
      // (no Platform.isAndroid/isIOS), so this body never runs there.
      // coverage:ignore-start
      unawaited(Vibration.vibrate(duration: 800));
      // coverage:ignore-end
    }
  }

  /// Rewrites [name]'s thresholds in `_exerciseStates`, in place.
  ///
  /// A no-op when the screen holds no state for [name], so editing an unloaded
  /// exercise cannot insert a half-built entry.
  void _writeThresholds(String name, int success, int fail) {
    final s = _exerciseStates[name];
    if (s != null) {
      _exerciseStates[name] = ExerciseState(
        name: s.name,
        weight: s.weight,
        reps: s.reps,
        successStreak: s.successStreak,
        failStreak: s.failStreak,
        maxWeight: s.maxWeight,
        successThreshold: success,
        failThreshold: fail,
      );
    }
  }

  /// Ends the break early at the user's request and re-persists the session.
  void _skipBreak() {
    _cancelBreak();
    unawaited(_saveActiveSession());
  }
}

/// Formats [d] as `h:mm:ss`, dropping the hours part under an hour.
String _formatDuration(Duration d) {
  final m = d.inMinutes.remainder(60).toString().padLeft(2, '0');
  final s = d.inSeconds.remainder(60).toString().padLeft(2, '0');
  return '${d.inHours > 0 ? '${d.inHours}:' : ''}$m:$s';
}

/// A rest period's duration and the label shown on the break banner.
class _Rest {
  const _Rest(this.seconds, this.label);

  /// How long the rest lasts.
  final int seconds;

  /// Banner text explaining why this rest length was chosen.
  final String label;
}
