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
        // Was "Finish workout?" with Cancel / Finish buttons.
        title: Icon(
          Icons.done_all,
          color: status.success,
          semanticLabel: 'Finish workout?',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: Icon(
              Icons.close,
              color: colorScheme.onSurfaceVariant,
              semanticLabel: 'Cancel',
            ),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: Icon(
              Icons.done_all,
              color: status.success,
              semanticLabel: 'Finish',
            ),
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
        // Was "Reset workout?" / "All progress will be lost." with
        // Cancel / Reset buttons: the reset glyph in the error colour.
        title: Icon(
          Icons.restart_alt,
          color: colorScheme.error,
          semanticLabel: 'Reset workout? All progress will be lost.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: Icon(
              Icons.close,
              color: colorScheme.onSurfaceVariant,
              semanticLabel: 'Cancel',
            ),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: Icon(
              Icons.restart_alt,
              color: colorScheme.error,
              semanticLabel: 'Reset',
            ),
          ),
        ],
      ),
    );
    if (ok == true) {
      // The service outlives the screen by design (stopWithTask="false"), so
      // abandoning a workout has to take it down explicitly -- otherwise the
      // notification sits there counting down a workout that no longer exists.
      await _breaks.stop();
      await StorageService.instance.clearActiveSession();
      if (mounted) Navigator.of(context).pop();
    }
  }
}
