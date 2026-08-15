// Finishing a workout: persisting the session, progression, and the summary.
//
// See workout_screen_session.dart for why this is a `part`.
part of 'workout_screen.dart';

/// The write-everything step that runs once a workout is marked finished.
extension _WorkoutScreenFinish on _WorkoutScreenState {

  /// Writes the finished session, applies progression, and shows the summary.
  ///
  /// Called by [_WorkoutScreenState._finishWorkout], which owns the `setState`
  /// that marks the workout finished before this runs.
  Future<void> _persistFinishedWorkout() async {
    final endTime = DateTime.now();
    final results = <ExerciseResult>[];

    for (var i = 0; i < widget.exercises.length; i++) {
      final ex = widget.exercises[i];
      results.add(
        ExerciseResult(
          exercise: ex,
          warmupDone: _warmupTapped[i],
          sets: List.generate(
            ex.sets,
            (s) => SetResult(
              targetReps: ex.reps,
              doneReps: _tapped[i][s] ? _doneReps[i][s] : 0,
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
    unawaited(
      showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (_) => WorkoutSummaryDialog(
          session: session,
          syncResult: syncResult,
        ),
      ),
    );
  }
}
