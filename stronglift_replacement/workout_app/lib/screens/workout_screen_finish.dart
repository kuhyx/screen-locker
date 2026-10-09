// Finishing a workout: persisting the session, progression, and the summary.
//
// See workout_screen_session.dart for why this is a `part`.
part of 'workout_screen.dart';

/// The write-everything step that runs once a workout is marked finished.
extension _WorkoutScreenFinish on _WorkoutScreenState {
  /// Starts tearing down the break service and returns the stop, which the
  /// caller awaits only after the summary is up.
  ///
  /// The stop is *started* before `_finished` flips -- the service must not
  /// outlive the workout, and with stopWithTask="false" nothing else stops it
  /// -- and its synchronous part (dropping the drain-nudge listener) runs
  /// right here. Only its completion (~120 ms of platform-channel teardown on
  /// the phone, 2026-10-09) no longer gates the summary. If it fails, the
  /// failure is logged loudly and the next launch's `stopStaleBreakService`
  /// takes the service down, since the active session is cleared by then.
  Future<void> _beginFinish() {
    SandboxLog.event('workout finish', {'type': widget.workoutType});
    _breakTimer?.cancel();
    return _breaks.stop().catchError((Object error, StackTrace stack) {
      log(
        'Break service did not stop at finish ($error); the next launch '
        'stops it as stale.',
        level: 1000,
        error: error,
        stackTrace: stack,
      );
    });
  }

  /// Writes the finished session, applies progression, and shows the summary.
  ///
  /// Called by [_WorkoutScreenState._finishWorkout], which owns the `setState`
  /// that marks the workout finished before this runs.
  Future<void> _persistFinishedWorkout(Stopwatch sinceTap) async {
    final endTime = DateTime.now();
    final results = <ExerciseResult>[];

    for (var i = 0; i < _exercises.length; i++) {
      final ex = _exercises[i];
      // A paused exercise is recorded as FAILED every time, whatever was
      // tapped before the pause: the user asked for it to step down while
      // they are injured, not to come back at the load it left with.
      final paused = _isPaused(i);
      results.add(
        ExerciseResult(
          exercise: ex,
          warmupDone: !paused && _warmupTapped[i],
          sets: List.generate(
            ex.sets,
            (s) => SetResult(
              targetReps: ex.reps,
              doneReps: !paused && _tapped[i][s] ? _doneReps[i][s] : 0,
              weight: ex.weight,
            ),
          ),
        ),
      );
    }

    final session = WorkoutSession(
      workoutType: widget.workoutType,
      startTime: _startTime,
      endTime: endTime,
      exercises: results,
    );
    // The direct PC poke starts the moment the session exists, before any
    // local write: it needs nothing from storage, and every millisecond here
    // is a millisecond of "instant" credit. It runs in parallel with the
    // sync push below (never after it); the PC dedups by record id, so
    // whichever lands first credits and the other reads as a duplicate.
    // Bounded to 2 s and never throws.
    final pcPoke = PcPokeService().poke(session);
    SandboxLog.event('pc poke started', {
      'ms_since_tap': sinceTap.elapsedMilliseconds,
    });

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
        for (int i = 0; i < _exercises.length; i++)
          _exercises[i].name: results[i].succeeded,
      },
      lastWorkoutDate: lastDate,
    );
    await storage.setLastWorkoutType(widget.workoutType);
    await storage.clearActiveSession();

    // applyProgression just moved weights/reps/streaks, so this is the moment
    // the remote copy goes stale. Pushed here (not on every set) because a
    // finished workout is the only thing that changes progression.
    unawaited(
      ProgressionSyncService().pushProgression().then((result) {
        if (!result.changed) {
          log('Progression not synced: ${result.reason}', level: 1000);
        }
      }),
    );
    // The workout is over: retract the shared in-progress session so another
    // device cannot resume a session that no longer exists.
    //
    // Chained onto the in-flight publish rather than fired alongside it: the
    // last set's `_saveActiveSession(toFirebase: true)` is unawaited, so two
    // concurrent PUTs to the same path can land out of order and strand a
    // finished session that the next install would faithfully restore.
    unawaited(
      _lastActiveSessionPush.then(
        (_) => ProgressionSyncService().pushActiveSession(null),
      ),
    );

    final syncResult = await _sync.writeWorkoutResult(session);
    // Not awaited: a slow or unreachable backend must not delay the summary
    // dialog. But the result is no longer discarded -- a failed push logs at
    // error level inside push(), so an unpushed workout is diagnosable
    // instead of silently absent from every other device.
    unawaited(
      WorkoutSyncService().push(session).then((result) {
        if (!result.pushed) {
          log('Workout not synced: ${result.reason}', level: 1000);
        }
      }),
    );

    if (!mounted) return;
    SandboxLog.event('summary shown', {
      'ms_since_tap': sinceTap.elapsedMilliseconds,
    });
    // The first frame that draws the dialog: "finish tap -> summary visible".
    WidgetsBinding.instance.addPostFrameCallback(
      (_) => SandboxLog.event('summary first frame', {
        'ms_since_tap': sinceTap.elapsedMilliseconds,
      }),
    );
    unawaited(
      showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (_) => WorkoutSummaryDialog(
          session: session,
          syncResult: syncResult,
          pcPoke: pcPoke,
        ),
      ),
    );
  }
}
