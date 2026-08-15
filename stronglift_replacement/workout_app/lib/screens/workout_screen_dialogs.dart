// Confirmation dialogs for finishing and resetting an active workout.
//
// See workout_screen_session.dart for why these are a `part`.
part of 'workout_screen.dart';

/// The destructive-action confirmations shown from the workout app bar.
extension _WorkoutScreenDialogs on _WorkoutScreenState {
  /// Asks for confirmation, then finishes the workout.
  Future<void> _confirmFinish() async {
    final colorScheme = Theme.of(context).colorScheme;
    final status = Theme.of(context).extension<AppStatusColors>()!;
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: colorScheme.surfaceContainerHigh,
        title: Text(
          'Finish workout?',
          style: TextStyle(color: colorScheme.onSurface),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: Text(
              'Cancel',
              style: TextStyle(color: colorScheme.onSurfaceVariant),
            ),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: Text('Finish', style: TextStyle(color: status.success)),
          ),
        ],
      ),
    );
    if (ok == true) await _finishWorkout();
  }

  /// Asks for confirmation, then discards the session and leaves the screen.
  Future<void> _confirmReset() async {
    final colorScheme = Theme.of(context).colorScheme;
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: colorScheme.surfaceContainerHigh,
        title: Text(
          'Reset workout?',
          style: TextStyle(color: colorScheme.onSurface),
        ),
        content: Text(
          'All progress will be lost.',
          style: TextStyle(color: colorScheme.onSurfaceVariant),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: Text(
              'Cancel',
              style: TextStyle(color: colorScheme.onSurfaceVariant),
            ),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: Text('Reset', style: TextStyle(color: colorScheme.error)),
          ),
        ],
      ),
    );
    if (ok == true) {
      await StorageService.instance.clearActiveSession();
      if (mounted) Navigator.of(context).pop();
    }
  }
}
