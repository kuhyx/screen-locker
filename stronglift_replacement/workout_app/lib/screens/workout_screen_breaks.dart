// Rest-period timers and per-exercise threshold edits.
//
// See workout_screen_session.dart for why this is a `part`. `setState` is
// `@protected` and unreachable from an extension, so these mutate through the
// state class's `_applyBreakState` shim instead.
part of 'workout_screen.dart';

/// Starting, ticking, cancelling and finishing the rest period between sets.
extension _WorkoutScreenBreaks on _WorkoutScreenState {
  void _startBreak(int secs, String label, int exIdx, int setIdx) {
    _breakTimer?.cancel();
    _applyBreakState(() {
      _breakDurationSecs = secs;
      _breakRemaining = secs;
      _breakLabel = label;
      _breakForExIdx = exIdx;
      _breakForSetIdx = setIdx;
      _breakStartTime = DateTime.now();
    });
    _breakTimer = Timer.periodic(const Duration(seconds: 1), _tickBreak);
  }

  void _tickBreak(Timer t) {
    _applyBreakState(() => _breakRemaining--);
    if (_breakRemaining <= 0) {
      t.cancel();
      unawaited(_onBreakFinished());
    }
  }

  void _cancelBreak() {
    _breakTimer?.cancel();
    _applyBreakState(() {
      _breakRemaining = 0;
      _breakForExIdx = -1;
      _breakForSetIdx = -1;
      _breakStartTime = null;
    });
  }

  Future<void> _onBreakFinished() async {
    await _playBreakEndCue();
    _applyBreakState(() {
      _breakForExIdx = -1;
      _breakForSetIdx = -1;
      _breakStartTime = null;
    });
    unawaited(_saveActiveSession());
  }

  Future<void> _onThresholdChanged(
    String name,
    int success,
    int fail,
  ) async {
    await StorageService.instance.setExerciseThresholds(
      name,
      successThreshold: success,
      failThreshold: fail,
    );
    if (mounted) {
      _applyBreakState(() {
        _writeThresholds(name, success, fail);
      });
    }
  }
}
