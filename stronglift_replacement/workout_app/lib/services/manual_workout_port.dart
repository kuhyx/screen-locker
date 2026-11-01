/// The remote manual-workout log, as the data export/import sees it.
library;

import 'package:crdt_sync/crdt_sync.dart';
import 'package:workout_app/services/workout_sync_service.dart';

/// Where manual workouts live: only in the remote crdt_sync log.
abstract interface class ManualWorkoutPort {
  /// All manual records (tombstones included), or null when the remote is
  /// unreachable or this device is not signed in.
  Future<Log?> read();

  /// Merges [records] into the remote log; false when that did not happen.
  Future<bool> push(Log records);
}

/// The real port: the app's existing crdt_sync/Firebase client.
class SyncManualWorkoutPort implements ManualWorkoutPort {
  /// Creates the port over [service] (a default service when omitted).
  SyncManualWorkoutPort([WorkoutSyncService? service])
    : _service = service ?? WorkoutSyncService();

  final WorkoutSyncService _service;

  @override
  Future<Log?> read() => _service.readManualLog();

  @override
  Future<bool> push(Log records) async =>
      (await _service.pushManualLog(records)).pushed;
}

/// A port that is always offline; the default under test.
class OfflineManualWorkoutPort implements ManualWorkoutPort {
  /// Creates the offline port.
  const OfflineManualWorkoutPort();

  @override
  Future<Log?> read() async => null;

  @override
  Future<bool> push(Log records) async => false;
}
