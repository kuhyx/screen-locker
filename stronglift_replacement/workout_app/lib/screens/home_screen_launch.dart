// The launch-time decision: open the workout straight away, or show home.
//
// A `part` for the same reason as home_screen_navigation.dart: it reaches the
// private `_HomeScreenState` members, and stays setState-free so `_load` keeps
// the one `setState` that applies the answer.
part of 'home_screen.dart';

/// How long a cold launch waits for the synced records before opening the
/// workout anyway. Fail-open on purpose: a wrong auto-open costs one back
/// press (the break service only starts on the first tap), while a dead
/// network must never hold the workout hostage.
const Duration _kSyncedTodayTimeout = Duration(seconds: 4);

/// What the first load of this process decided.
typedef _LaunchDecision = ({
  /// Push the workout (resuming if a session is saved) without showing home.
  bool open,

  /// A synced record already covers today.
  bool syncedToday,

  /// This device has no sync credentials; the workout screen must say so.
  bool syncNotSetUp,
});

/// Opening the workout on launch, the way todo opens the editor.
extension _HomeScreenLaunch on _HomeScreenState {
  /// Decides whether this load skips the home screen.
  ///
  /// Only the first load of the process decides anything: coming back from a
  /// workout, settings or the background must land on home. A saved session
  /// always resumes (as it always has). A fresh workout opens only when
  /// nothing counts for today yet -- and never in PC lock mode, where the
  /// workout route cannot be popped and the manual-log button on home would
  /// become unreachable.
  Future<_LaunchDecision> _decideLaunch({
    required bool firstLoad,
    required bool hasSaved,
    required bool doneLocally,
    required DateTime today,
  }) async {
    const stay = (open: false, syncedToday: false, syncNotSetUp: false);
    if (!firstLoad || !widget.openWorkoutOnLaunch) return stay;
    final wantsFresh = !hasSaved && !doneLocally && !lockModeEnabled;
    if (!hasSaved && !wantsFresh) return stay;

    final sync = widget.syncService ?? WorkoutSyncService();
    final configured = await (widget.configuredProbe ?? sync.isConfigured)();
    final syncedToday =
        wantsFresh && configured && await _syncedWorkoutToday(sync, today);
    return (
      open: hasSaved || !syncedToday,
      syncedToday: syncedToday,
      syncNotSetUp: !configured,
    );
  }

  /// Whether a synced record -- a manual workout, the PC's verified run, a
  /// session from another device -- is dated [today].
  ///
  /// Never throws: an unreadable backend answers "no", loudly, so the
  /// workout still opens.
  Future<bool> _syncedWorkoutToday(
    WorkoutSyncService sync,
    DateTime today,
  ) async {
    try {
      final payloads = await sync.readMergedWorkoutPayloads().timeout(
        _kSyncedTodayTimeout,
      );
      return anyWorkoutOn(payloads, today);
    } on Object catch (error) {
      log(
        'HomeScreen: could not read synced workouts to check for one logged '
        'today ($error) — opening the workout anyway; back out if you '
        'already trained.',
        level: 900,
      );
      return false;
    }
  }
}
