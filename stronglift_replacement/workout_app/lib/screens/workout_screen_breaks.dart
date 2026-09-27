// Rest-period timers and per-exercise settings edits.
//
// See workout_screen_session.dart for why this is a `part`. `setState` is
// `@protected` and unreachable from an extension, so these mutate through the
// state class's `_applyBreakState` shim instead.
part of 'workout_screen.dart';

// How late a restored break's end cue may still be played. Long enough to
// cover the app being killed and reopened mid-rest; short enough that
// resuming yesterday's session does not blast the sound across the gym.
const _expiredBreakGraceSecs = 120;

/// Starting, ticking, cancelling and finishing the rest period between sets.
extension _WorkoutScreenBreaks on _WorkoutScreenState {
  /// Exercise [exIdx]'s stored state, or its defaults while the states are
  /// still loading: that is where its rest lengths live.
  ExerciseState _stateOf(int exIdx) {
    final ex = widget.exercises[exIdx];
    return _exerciseStates[ex.name] ?? ExerciseState.initial(ex);
  }

  void _startBreak(int secs, String label, int exIdx, int setIdx) {
    // The one place every rest is born, so the sandbox's short override
    // applies to warmup, success and fail rests alike.
    final restSecs = Sandbox.rest(secs);
    final restLabel = Sandbox.restLabel(label);
    SandboxLog.event('break start', {
      'secs': restSecs,
      // The exercise's own rest, before the sandbox override: the only way
      // to see per-exercise rest lengths in the sandbox flavor.
      'planned': secs,
      'label': restLabel,
      'exercise': exIdx,
      'set': setIdx,
    });
    _breakTimer?.cancel();
    _applyBreakState(() {
      _breakClock = BreakClock.startingAt(DateTime.now(), restSecs);
      _breakLabel = restLabel;
      _breakForExIdx = exIdx;
      _breakForSetIdx = setIdx;
    });
    _breakTimer = Timer.periodic(const Duration(seconds: 1), _tickBreak);
  }

  /// The once-a-second tick.
  void _tickBreak(Timer t) => _refreshBreak();

  /// Re-reads the deadline after the app was away, and drains any press made
  /// from the notification while it was.
  void _onResumed() {
    unawaited(_drainIntents());
    _refreshBreak();
  }

  /// Re-renders the countdown from the deadline, and ends the rest once past.
  ///
  /// Deliberately not a decrement: ticks are throttled, and in Doze dropped
  /// entirely, once the app is backgrounded — so counting them loses time.
  /// Reading the clock instead means a timer that stalled for ten minutes
  /// fires the cue on its very next tick rather than never.
  void _refreshBreak() {
    final clock = _breakClock;
    if (clock == null) return;
    if (clock.expiredAt(DateTime.now())) {
      _breakTimer?.cancel();
      unawaited(_onBreakFinished());
    } else {
      _applyBreakState(() {});
    }
  }

  void _cancelBreak() {
    SandboxLog.event('break cancel');
    _breakTimer?.cancel();
    _applyBreakState(() {
      _breakClock = null;
      _breakForExIdx = -1;
      _breakForSetIdx = -1;
    });
  }

  Future<void> _onBreakFinished() async {
    SandboxLog.event('break end');
    await _playBreakEndCue();
    _applyBreakState(() {
      _breakClock = null;
      _breakForExIdx = -1;
      _breakForSetIdx = -1;
    });
    unawaited(_saveActiveSession());
  }

  /// Persists an edit from an exercise's settings sheet and shows it.
  ///
  /// Turning a warmup off while its own rest is running ends that rest: the
  /// user just said the warmup is not part of this exercise any more.
  /// Pausing the exercise ends any rest of it, for the same reason.
  Future<void> _onSettingsChanged(ExerciseState updated) async {
    SandboxLog.event('exercise settings', {
      'exercise': updated.name,
      'mode': updated.mode.storageKey,
      'repsHigh': updated.repsHigh,
      'repsLow': updated.repsLow,
      'warmup': updated.hasWarmup,
      'pausedUntil': updated.pausedUntil?.toIso8601String(),
      'restSuccess': updated.restSuccessSecs,
      'restFail': updated.restFailSecs,
      'restWarmup': updated.restWarmupSecs,
    });
    await StorageService.instance.setExerciseSettings(updated);
    if (!mounted) return;
    _applyBreakState(() => _exerciseStates[updated.name] = updated);
    final exIdx = widget.exercises.indexWhere((e) => e.name == updated.name);
    final paused = updated.isPausedAt(DateTime.now());
    final warmupRestGone = !updated.hasWarmup && _breakForSetIdx == -1;
    if (_inBreak && _breakForExIdx == exIdx && (paused || warmupRestGone)) {
      _cancelBreak();
    }
    // Always: a pause changes the notification's "sets left" and next set.
    unawaited(_saveActiveSession());
  }
}
