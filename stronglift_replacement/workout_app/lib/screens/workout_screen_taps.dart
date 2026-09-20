// Rep-circle and warmup tap handlers for the active workout screen.
//
// A `part` rather than a separate library so the extension keeps reaching the
// private `_WorkoutScreenState` fields. `setState` is `@protected` and cannot
// be called from an extension, so these mutate through the state class's
// `_applyBreakState` shim — the same seam `workout_screen_breaks.dart` uses.
part of 'workout_screen.dart';

/// The three ways a user records work: tap a set, tap a warmup, undo a set.
extension _WorkoutScreenTaps on _WorkoutScreenState {
  /// Records set [setIdx] of exercise [exIdx], or decrements its reps.
  ///
  /// First tap marks the set done at the exercise's full target reps and earns
  /// the rest period. Every later tap decrements the reps by one, which can
  /// flip the running break between its 3-minute and 5-minute durations.
  void _tapCircle(int exIdx, int setIdx) {
    if (_finished) return;

    final wasNotTapped = !_tapped[exIdx][setIdx];
    SandboxLog.event('tap set', {
      'exercise': exIdx,
      'set': setIdx,
      'first': wasNotTapped,
      'ignored': wasNotTapped && _inBreak,
    });
    if (wasNotTapped && _inBreak) return;

    _applyBreakState(() {
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

  /// Marks exercise [exIdx]'s warmup done and starts the warmup rest.
  void _tapWarmup(int exIdx) {
    SandboxLog.event('tap warmup', {'exercise': exIdx});
    if (_finished || _warmupTapped[exIdx]) return;
    _applyBreakState(() => _warmupTapped[exIdx] = true);
    if (!_inBreak) {
      _startBreak(_warmupBreakSecs, 'Warmup rest (3 min)', exIdx, -1);
    }
    unawaited(_saveActiveSession(toFirebase: true));
  }

  /// Undoes set [setIdx] of [exIdx], restoring its full target reps.
  void _resetCircle(int exIdx, int setIdx) {
    SandboxLog.event('reset set', {'exercise': exIdx, 'set': setIdx});
    if (_finished) return;
    _applyBreakState(() {
      _tapped[exIdx][setIdx] = false;
      _doneReps[exIdx][setIdx] = widget.exercises[exIdx].reps;
    });
    if (_breakForExIdx == exIdx && _breakForSetIdx == setIdx) {
      _cancelBreak();
    }
    unawaited(_saveActiveSession());
  }
}
