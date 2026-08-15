// Pushing local progression up to Firebase.
//
// See progression_sync_service_session.dart for why this is a `part`.
part of 'progression_sync_service.dart';

/// Pushes local progression state to the remote backend.
extension ProgressionSyncServicePush on ProgressionSyncService {
  /// Pushes local progression to Firebase, one record per exercise.
  ///
  /// Each record carries an HLC derived from the remote one it replaces
  /// (`previous:`), so the stamps form a causal chain per exercise rather than
  /// depending on device clocks agreeing.
  ///
  /// Refuses to push at all from a freshly-installed database that still has
  /// remote records to lose. Without that, the seed-then-push sequence a
  /// reinstall performs would overwrite real progression with factory defaults
  /// and leave Firebase as the only — wrong — copy. The test is
  /// [StorageService.looksFreshlyInstalled], not a per-exercise value
  /// comparison: a deliberate [StorageService.resetExerciseToDefaults] can
  /// produce a row identical to a seeded one, and that reset must still sync.
  Future<ProgressionSyncResult> pushProgression() async {
    final client = await _openFirebase();
    if (client == null) {
      const reason =
          'progression NOT pushed: no Firebase account on this device — '
          'connect one in Settings, or progression lives only on this phone';
      log(
        'ProgressionSyncService.pushProgression skipped: $reason',
        level: 900,
      );
      return const ProgressionSyncResult(changed: false, reason: reason);
    }

    try {
      final states = await StorageService.instance.getAllExerciseStates();

      // Decided ONCE, before any write. Evaluating this per exercise would
      // still write every record Firebase happens not to hold yet before
      // hitting the first one it does — a fresh install would leak factory
      // defaults for exactly the exercises with no remote copy to protect them.
      //
      // Gated on hasSyncedProgression, NOT looksFreshlyInstalled: the only
      // production caller finishes a workout (writing history and
      // last_workout_type) before pushing, so a freshness test would already
      // be false here and could never fire.
      if (!await StorageService.instance.hasSyncedProgression() &&
          await _remoteHasAnyProgression(client, states)) {
        const reason =
            'progression NOT pushed: this install has never pulled from '
            'Firebase, but Firebase already holds progression. Refusing to '
            'overwrite it with local state that may be factory defaults — '
            'restart the app (or reconnect sync) so the real state is pulled '
            'down first.';
        log('ProgressionSyncService: $reason', level: 1000);
        return const ProgressionSyncResult(changed: false, reason: reason);
      }

      var written = 0;
      for (final state in states) {
        final path = ProgressionSyncService.pathForExercise(state.name);
        final remote = await _readRecord(client, path);

        await _writeRecord(
          client,
          path,
          'exercise_state:${state.name}',
          ProgressionSyncService._stateToJson(state),
          // Chain from the record being replaced so the stamp is causal, not
          // merely wall-clock: an offline device cannot mint a "newer" tick
          // just by having a fast clock.
          Hlc.newTick(currentSyncDeviceId, previous: remote?.$2),
        );
        written++;
      }
      return ProgressionSyncResult(
        changed: written > 0,
        count: written,
        reason: 'pushed $written exercise(s) to Firebase',
      );
    } on Object catch (error, stackTrace) {
      // Deliberately broad and swallowed: a sync failure must never cost the
      // user their workout. Never silent, though — this logs at error level
      // and the reason travels back to the caller.
      final reason = 'progression push failed: $error';
      log(
        'ProgressionSyncService.pushProgression failed',
        level: 1000,
        error: error,
        stackTrace: stackTrace,
      );
      return ProgressionSyncResult(changed: false, reason: reason);
    } finally {
      client.close();
    }
  }
}
