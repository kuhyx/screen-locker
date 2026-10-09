// The Settings screen's side of a manual deload.
//
// A `part` so the extension keeps reaching the debounce timers and `context`;
// the one `setState` it needs goes through `_showDeloaded`.
part of 'settings_screen.dart';

/// Manual deload from the exercise settings sheet opened on this screen.
extension _SettingsScreenDeload on _SettingsScreenState {
  /// Runs a manual deload of [name] and shows the new target.
  ///
  /// Cancels that exercise's pending weight/reps debounce first: a stepper
  /// write queued 600 ms earlier would otherwise land after the deload and
  /// quietly undo it.
  Future<ExerciseState?> _deload(String name) async {
    _weightTimers.remove(name)?.cancel();
    _repsTimers.remove(name)?.cancel();
    final result = await StorageService.instance.manualDeload(
      name,
      source: DeloadSource.settings,
    );
    if (!mounted) return null;
    final next = result.state;
    if (next == null) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(result.reason)));
      return null;
    }
    SandboxLog.event('manual deload', {
      'exercise': name,
      'source': DeloadSource.settings.storageKey,
      'weight': next.weight,
      'reps': next.reps,
    });
    _showDeloaded(next);
    return next;
  }
}
