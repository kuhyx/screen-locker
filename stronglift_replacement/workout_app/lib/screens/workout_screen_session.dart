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
  /// A break whose recorded end time has already passed is *not* dropped: it is
  /// parked in `_expiredBreak` so the screen can say so and, if the user only
  /// just missed it, play the cue they were waiting for.
  void _restoreFromSaved(Map<String, dynamic> s) {
    SandboxLog.event('session restore', {'keys': s.keys.toList()});
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
      final clock = BreakClock(endTime: endTime, durationSecs: breakDur);
      if (!clock.expiredAt(DateTime.now())) {
        _breakForExIdx = s['breakForExIdx'] as int? ?? -1;
        _breakForSetIdx = s['breakForSetIdx'] as int? ?? -1;
        _breakLabel = s['breakLabel'] as String? ?? 'Rest';
        _breakClock = clock;
        _breakTimer = Timer.periodic(const Duration(seconds: 1), _tickBreak);
      } else {
        // NEVER fail silently. This branch used to be an implicit no-op, which
        // is why "the break never rang" was indistinguishable from "there was
        // no break": the app was away when the rest ended, and said nothing
        // about it on the way back.
        log(
          'WorkoutScreen: the restored session had a rest period that ended '
          '${clock.secondsOverdueAt(DateTime.now())}s ago while the app was '
          'not running, so its end cue never played.',
          level: 900,
        );
        _expiredBreak = clock;
      }
    }
  }

  /// Plays the cue for a break that ended while the app was away, if it is
  /// still recent enough to be useful.
  ///
  /// Called once, after the first frame. Beyond the grace window the rest is
  /// ancient history and firing the sound would just be startling — but the
  /// `log` above has already recorded it either way.
  Future<void> _settleExpiredBreak() async {
    final clock = _expiredBreak;
    _expiredBreak = null;
    if (clock == null) return;
    final overdue = clock.secondsOverdueAt(DateTime.now());
    if (overdue > _expiredBreakGraceSecs) {
      log(
        'WorkoutScreen: not replaying the rest-end cue — it is ${overdue}s '
        'late, past the ${_expiredBreakGraceSecs}s grace window.',
        level: 800,
      );
      return;
    }
    await _playBreakEndCue();
    // Forget the break now it has been settled. Without this the saved session
    // still carries its deadline, so relaunching twice inside the grace window
    // would sound the cue again for a rest that ended once.
    unawaited(_saveActiveSession());
  }

  /// Persists the active session locally, and to Firebase when [toFirebase].
  ///
  /// [toFirebase] is false on the per-tap paths (rep decrements, break
  /// bookkeeping) and true only on set/warmup completion. `saveActiveSession`
  /// runs on every tap, and a Firebase write per tap is exactly the traffic the
  /// sync revision cache exists to avoid — so the remote copy is debounced to
  /// the events that actually change which set the user is standing on.
  Future<void> _saveActiveSession({bool toFirebase = false}) async {
    SandboxLog.event('session save', {'toFirebase': toFirebase});
    final data = _activeSessionData();
    await StorageService.instance.saveActiveSession(data);
    // The one seam the notification is fed from. Every event that moves the
    // workout on -- a set, a warmup, a rep decrement, a skip, a reset, a
    // drained press -- already comes through here, so hanging the push on it
    // means none of them can be forgotten.
    unawaited(_breaks.push(_buildSnapshot()));
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
      'breakEndMs': _breakClock?.endTime.millisecondsSinceEpoch ?? 0,
    };
  }

  /// When the user decrements reps on the set that triggered the current break,
  /// switch between 3-min (success) and 5-min (fail) durations.
  void _recomputeBreakIfNeeded(int exIdx, int setIdx) {
    // Read the clock ONCE. `_inBreak` re-reads DateTime.now() every time it is
    // touched, so guarding on it and then dereferencing `_breakClock!` is a
    // null-assertion waiting for the break to expire between the two lines.
    final clock = _breakClock;
    if (clock == null || clock.expiredAt(DateTime.now())) return;
    if (_breakForExIdx != exIdx || _breakForSetIdx != setIdx) return;
    if (_breakForSetIdx == -1) return; // warmup break, never recompute

    final succeeded = _doneReps[exIdx][setIdx] >= widget.exercises[exIdx].reps;
    final newDuration = Sandbox.rest(
      succeeded ? _successBreakSecs : _failBreakSecs,
    );
    if (newDuration == clock.durationSecs) return;

    _breakClock = clock.withDuration(newDuration);
    _breakLabel = Sandbox.restLabel(
      succeeded ? 'Rest (3 min — well done!)' : 'Rest (5 min — keep going!)',
    );
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
    await _audio.play(AssetSource('sounds/break_end.mp3')).catchError((
      Object error,
    ) {
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
    SandboxLog.event('break skip');
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
