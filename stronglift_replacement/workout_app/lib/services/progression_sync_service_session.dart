// The shared in-progress session, pushed to and read from Firebase.
//
// An `extension` in a `part`. Safe here because no test fake subclasses
// ProgressionSyncService -- extension methods dispatch statically, so an
// override would silently not take effect.
part of 'progression_sync_service.dart';

/// Pushing and reading the shared active session.
extension ProgressionSyncServiceSession on ProgressionSyncService {
  /// Publishes the in-progress session, or clears it when [data] is null.
  ///
  /// Called on set completion rather than per rep. `saveActiveSession` fires on
  /// every tap, and a Firebase write per tap is exactly the traffic the sync
  /// revision cache exists to avoid.
  Future<ProgressionSyncResult> pushActiveSession(
    Map<String, dynamic>? data,
  ) async {
    final client = await _openFirebase();
    if (client == null) {
      const reason = 'active session NOT pushed: no Firebase account';
      log(
        'ProgressionSyncService.pushActiveSession skipped: $reason',
        level: 900,
      );
      return const ProgressionSyncResult(changed: false, reason: reason);
    }

    try {
      if (data == null) {
        // An empty object, not a delete: the readers treat absent and empty
        // alike, and a write keeps the HLC ordering intact for the next push.
        await _writeRecord(
          client,
          kActiveSessionPath,
          'active_session',
          const {},
          Hlc.newTick(currentSyncDeviceId),
        );
        return const ProgressionSyncResult(
          changed: true,
          reason: 'cleared the shared active session',
        );
      }
      await _writeRecord(
        client,
        kActiveSessionPath,
        'active_session',
        data,
        Hlc.newTick(currentSyncDeviceId),
      );
      return const ProgressionSyncResult(
        changed: true,
        reason: 'published the active session',
      );
    } on Object catch (error, stackTrace) {
      final reason = 'active session push failed: $error';
      log(
        'ProgressionSyncService.pushActiveSession failed',
        level: 1000,
        error: error,
        stackTrace: stackTrace,
      );
      return ProgressionSyncResult(changed: false, reason: reason);
    } finally {
      client.close();
    }
  }

  /// Returns the shared in-progress session, or null when there is none.
  ///
  /// An empty payload means "explicitly cleared" and reads back as null, so a
  /// finished workout is never resurrected.
  Future<Map<String, dynamic>?> readActiveSession() async {
    final client = await _openFirebase();
    if (client == null) {
      log(
        'ProgressionSyncService.readActiveSession skipped: no Firebase account',
        level: 900,
      );
      return null;
    }
    try {
      final remote = await _readRecord(client, kActiveSessionPath);
      if (remote == null || remote.$1.isEmpty) return null;
      return remote.$1;
    } on Object catch (error, stackTrace) {
      log(
        'ProgressionSyncService.readActiveSession failed',
        level: 1000,
        error: error,
        stackTrace: stackTrace,
      );
      return null;
    } finally {
      client.close();
    }
  }
}
