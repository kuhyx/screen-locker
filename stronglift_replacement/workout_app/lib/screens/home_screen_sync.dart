// The home screen's sync tick: what the status card says, and when.
//
// A `part` so the extension keeps reaching the private `_HomeScreenState`
// fields; it mutates them through the `_applyState` shim because `setState`
// is `@protected` and cannot be called from an extension.
part of 'home_screen.dart';

/// Keeps the sync status card honest.
extension _HomeScreenSync on _HomeScreenState {
  /// Runs a sync tick and folds the outcome into the status card.
  ///
  /// Never throws: [WorkoutSyncService.syncNow] reports failures as a
  /// [PushResult] rather than an exception, and the card is where that
  /// reason finally becomes visible to the user.
  Future<void> _refreshSyncStatus() async {
    if (_syncing) return; // a tick is already in flight
    _syncing = true;
    final storage = StorageService.instance;
    final sync = widget.syncService ?? WorkoutSyncService();
    final now = (widget.clock ?? DateTime.now)();
    try {
      final configured = await (widget.configuredProbe ?? sync.isConfigured)();
      final storedAt = await storage.getLastSyncedAt();

      // Show what the PERSISTED state says before the tick resolves. Without
      // this pass the card can never say "out of date": by the time a tick
      // has finished it has either stamped the time (so the age is zero) or
      // failed (so the card is "Sync failed"), and a phone that has not
      // synced for days would look healthy for the whole tick. This is also
      // the honest reading while the network is still being waited on.
      if (mounted) {
        _applyState(() {
          _syncStatus = computeSyncStatus(
            configured: configured,
            now: now,
            lastSyncedAt: storedAt,
          );
        });
      }

      final result = configured ? await sync.syncNow() : null;
      if (result != null && result.pushed) {
        await storage.markSyncedNow(now);
      }
      final status = computeSyncStatus(
        configured: configured,
        now: now,
        lastResult: result,
        lastSyncedAt: await storage.getLastSyncedAt(),
      );
      if (mounted) _applyState(() => _syncStatus = status);
    } finally {
      _syncing = false;
    }
  }
}
