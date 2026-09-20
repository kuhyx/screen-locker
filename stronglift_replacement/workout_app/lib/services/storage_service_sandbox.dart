// The sandbox flavor's controls: wipe, un-do today, and the rest override.
//
// A `part` of StorageService for the same reason as the other parts: they
// need `_db` and `_getSetting`, and the sandbox must not grow a second
// storage layer with its own opinions about the schema.
part of 'storage_service.dart';

/// Settings key the sandbox's rest length is stored under.
const String kSandboxRestSecsKey = 'sandbox_rest_secs';

/// Sandbox-only maintenance on the (sandbox's own) database.
///
/// Nothing here checks `Sandbox.enabled`: the Settings screen only offers
/// these while it is, and a wipe of a database that belongs to the sandbox
/// package cannot reach the daily build's data whatever flag is set.
extension StorageServiceSandbox on StorageService {
  /// Empties every table and re-seeds the exercise defaults: a fresh install
  /// without reinstalling.
  Future<void> wipeAll() async {
    for (final table in const [
      'workout_history',
      'active_session',
      'settings',
      'exercise_state',
    ]) {
      await _db.delete(table);
    }
    await _seedDefaultsIfNeeded();
  }

  /// Deletes every history row dated [day] and returns how many went, so the
  /// home screen stops saying "Done for today" and offers the workout again.
  Future<int> deleteWorkoutsOn(DateTime day) {
    final prefix =
        '${day.year.toString().padLeft(4, '0')}-'
        '${day.month.toString().padLeft(2, '0')}-'
        '${day.day.toString().padLeft(2, '0')}';
    return _db.delete(
      'workout_history',
      where: 'date LIKE ?',
      whereArgs: ['$prefix%'],
    );
  }

  /// The saved rest override, or [fallback] when none has been saved.
  Future<int> getSandboxRestSecs(int fallback) async {
    final raw = await _getSetting(kSandboxRestSecsKey);
    return raw == null ? fallback : int.parse(raw);
  }

  /// Persists the rest override used by every sandbox break.
  Future<void> setSandboxRestSecs(int secs) =>
      _setSetting(kSandboxRestSecsKey, '$secs');
}
