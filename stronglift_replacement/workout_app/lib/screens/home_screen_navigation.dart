// Navigation off the home screen: settings, and starting/resuming a workout.
//
// A `part` so the extension keeps reaching the private `_HomeScreenState`
// fields. Both methods are setState-free — `setState` is `@protected` and
// cannot be called from an extension — and both end by reloading the screen.
part of 'home_screen.dart';

/// The two routes the home screen pushes, and the reload each returns to.
extension _HomeScreenNavigation on _HomeScreenState {
  Future<void> _openSyncSettings() async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(builder: (_) => const SettingsScreen()),
    );
    unawaited(_load());
  }

  Future<void> _openWorkout({bool resume = false}) async {
    final storage = StorageService.instance;
    Map<String, dynamic>? savedState;
    var type = _nextType;
    var exercises = _exercises;

    if (resume && _savedSession != null) {
      savedState = _savedSession;
      final savedType = savedState!['workoutType'] as String? ?? _nextType;
      type = savedType;
      exercises = await storage.getCurrentExercises(savedType);
    }

    if (!mounted) return;
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => WorkoutScreen(
          workoutType: type,
          exercises: exercises,
          savedState: savedState,
        ),
      ),
    );
    unawaited(_load());
  }
}
