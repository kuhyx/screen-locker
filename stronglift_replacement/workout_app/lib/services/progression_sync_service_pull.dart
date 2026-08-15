// Pulling remote progression back into local state.
//
// See progression_sync_service_session.dart for why this is a `part`.
part of 'progression_sync_service.dart';

/// Pulls remote progression into the local database.
extension ProgressionSyncServicePull on ProgressionSyncService {
  /// Pulls remote progression into the local DB.
  ///
  /// Applies only to a freshly-installed database
  /// ([StorageService.looksFreshlyInstalled]) — so a pull can restore a wiped
  /// install but can never clobber progression, or a deliberate reset, made on
  /// this phone. That keeps the operation safe to run unconditionally at app
  /// start.
  Future<ProgressionSyncResult> pullProgression() async {
    final client = await _openFirebase();
    if (client == null) {
      const reason =
          'progression NOT pulled: no Firebase account on this device — '
          'connect one in Settings to restore progression without storage '
          'permission';
      log(
        'ProgressionSyncService.pullProgression skipped: $reason',
        level: 900,
      );
      return const ProgressionSyncResult(changed: false, reason: reason);
    }

    try {
      // Once this install has reconciled with Firebase, local state wins.
      // Checked instead of looksFreshlyInstalled because a hand edit
      // (setExerciseWeight, resetExerciseToDefaults) writes neither history
      // nor last_workout_type: the DB still "looks fresh" afterwards, so a
      // freshness test would silently revert the user's own change on the very
      // next launch.
      if (await StorageService.instance.hasSyncedProgression()) {
        const reason =
            'progression NOT pulled: this install has already reconciled with '
            'Firebase, so local state wins and must not be overwritten';
        log('ProgressionSyncService: $reason', level: 800);
        return const ProgressionSyncResult(changed: false, reason: reason);
      }

      var applied = 0;
      for (final name in ProgressionSyncService._defaults.keys) {
        final remote = await _readRecord(
          client,
          ProgressionSyncService.pathForExercise(name),
        );
        if (remote == null) continue;
        await StorageService.instance.replaceExerciseState(
          ProgressionSyncService._stateFromJson(remote.$1),
        );
        applied++;
      }
      // Marked even when nothing came down: reaching the backend and finding
      // it empty IS a successful reconcile, and it is what unblocks this
      // device's first push. Only a thrown error leaves the flag unset.
      await StorageService.instance.markProgressionSynced();
      final reason = applied == 0
          ? 'no progression restored: Firebase holds no exercise records yet'
          : 'restored $applied exercise(s) from Firebase';
      log('ProgressionSyncService.pullProgression: $reason', level: 800);
      return ProgressionSyncResult(
        changed: applied > 0,
        count: applied,
        reason: reason,
      );
    } on Object catch (error, stackTrace) {
      final reason = 'progression pull failed: $error';
      log(
        'ProgressionSyncService.pullProgression failed',
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
