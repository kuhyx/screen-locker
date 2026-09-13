// Applying notification button presses, and describing the workout for the
// foreground service.
//
// A `part` for the same reason as workout_screen_session.dart: the extension
// reaches private `_WorkoutScreenState` fields, and mutations go through the
// `_applyBreakState` shim because `setState` is `@protected`.
part of 'workout_screen.dart';

/// The bridge between the status-bar notification and the workout state.
extension _WorkoutScreenIntents on _WorkoutScreenState {
  /// Describes the workout exactly as the notification should show it.
  BreakSnapshot _buildSnapshot() {
    final next = _nextTarget();
    final last = _lastRecorded();
    final nextEx = next == null ? null : widget.exercises[next.$1];
    return BreakSnapshot(
      workoutType: widget.workoutType,
      breakEndMs: _breakClock?.endTime.millisecondsSinceEpoch ?? 0,
      breakDurationSecs: _breakDurationSecs,
      breakLabel: _breakLabel,
      breakForExIdx: _breakForExIdx,
      breakForSetIdx: _breakForSetIdx,
      nextExIdx: next?.$1 ?? -1,
      nextSetIdx: next?.$2 ?? -1,
      nextExName: nextEx?.name ?? '',
      nextSetNumber: (next?.$2 ?? -1) + 1,
      nextTotalSets: nextEx?.sets ?? 0,
      nextReps: nextEx?.reps ?? 0,
      nextWeight: nextEx?.weight ?? 0,
      lastExIdx: last?.$1 ?? -1,
      lastSetIdx: last?.$2 ?? -1,
      setsRemaining: _setsRemaining(),
      finished: _finished,
    );
  }

  /// The set `✓ Done` would record: the first untapped one.
  ///
  /// Scans the break's own exercise first, so finishing a rest offers the next
  /// set of the lift the user is standing at rather than jumping ahead.
  (int, int)? _nextTarget() {
    final preferred = _breakForExIdx;
    if (preferred >= 0 && preferred < widget.exercises.length) {
      final inExercise = _firstUntappedIn(preferred);
      if (inExercise != null) return (preferred, inExercise);
    }
    for (var ex = 0; ex < widget.exercises.length; ex++) {
      final setIdx = _firstUntappedIn(ex);
      if (setIdx != null) return (ex, setIdx);
    }
    return null;
  }

  int? _firstUntappedIn(int exIdx) {
    for (var s = 0; s < _tapped[exIdx].length; s++) {
      if (!_tapped[exIdx][s]) return s;
    }
    return null;
  }

  /// The set `− 1 rep` would decrement: the one the break belongs to, else the
  /// last tapped set in plan order.
  (int, int)? _lastRecorded() {
    if (_breakForExIdx >= 0 && _breakForSetIdx >= 0) {
      return (_breakForExIdx, _breakForSetIdx);
    }
    for (var ex = widget.exercises.length - 1; ex >= 0; ex--) {
      for (var s = _tapped[ex].length - 1; s >= 0; s--) {
        if (_tapped[ex][s]) return (ex, s);
      }
    }
    return null;
  }

  int _setsRemaining() {
    var count = 0;
    for (final row in _tapped) {
      for (final done in row) {
        if (!done) count++;
      }
    }
    return count;
  }

  /// Hands the workout to the foreground service, then applies anything the
  /// user already pressed on a notification from a previous run of the app.
  ///
  /// Order matters: `_restoreFromSaved` has already rebuilt the base state from
  /// sqflite, and the queue is the delta on top of it. Draining first would be
  /// overwritten by the stale base.
  Future<void> _startBreakService() async {
    final result = await _breaks.start(
      _buildSnapshot(),
      onDrainNudge: () => unawaited(_drainIntents()),
    );
    if (result.needsPermissionWarning && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Notifications are off — the rest timer still runs and still '
            'sounds, but there will be no status-bar countdown.',
          ),
          duration: Duration(seconds: 6),
        ),
      );
    }
    await _drainIntents();
  }

  /// Applies every press the user made from the notification, oldest first.
  Future<void> _drainIntents() =>
      _breaks.drain((intent) async => _applyIntent(intent));

  /// Applies one press, or says out loud why it could not be.
  ///
  /// Every path goes through the same `_tapCircle` / `_skipBreak` the on-screen
  /// buttons use, so the notification can never invent a rule the UI does not
  /// have. A press that no longer makes sense is dropped rather than forced:
  /// the state moved on while the press was in the queue.
  void _applyIntent(BreakIntent intent) {
    if (_finished) {
      _dropIntent(intent, 'the workout is already finished');
      return;
    }
    switch (intent.kind) {
      case BreakIntentKind.skipBreak:
        if (!_inBreak) {
          _dropIntent(intent, 'no rest period is running any more');
          return;
        }
        _skipBreak();
      case BreakIntentKind.done:
        if (!_isValidSet(intent)) return;
        if (_tapped[intent.exIdx][intent.setIdx]) {
          _dropIntent(intent, 'that set was already recorded');
          return;
        }
        // Pressing Done during a rest means "I am done resting AND done with
        // the set" -- the two taps the user would make by hand. `_tapCircle`
        // refuses a new set mid-break, so the rest is ended first.
        if (_inBreak) _skipBreak();
        _tapCircle(intent.exIdx, intent.setIdx);
      case BreakIntentKind.minusRep:
        if (!_isValidSet(intent)) return;
        if (!_tapped[intent.exIdx][intent.setIdx]) {
          _dropIntent(intent, 'that set is no longer recorded');
          return;
        }
        _tapCircle(intent.exIdx, intent.setIdx);
    }
  }

  bool _isValidSet(BreakIntent intent) {
    final exOk = intent.exIdx >= 0 && intent.exIdx < widget.exercises.length;
    if (!exOk || intent.setIdx < 0 ||
        intent.setIdx >= _tapped[intent.exIdx].length) {
      _dropIntent(intent, 'it points at a set this workout does not have');
      return false;
    }
    return true;
  }

  void _dropIntent(BreakIntent intent, String why) => log(
    'WorkoutScreen: dropped notification press $intent — $why. The button '
    'press was recorded before the workout moved on.',
    level: 900,
  );
}
