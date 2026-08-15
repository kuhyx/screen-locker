// The active-workout app bar: elapsed clock plus Reset / Finish actions.
//
// See workout_screen_session.dart for why this is a `part`.
part of 'workout_screen.dart';

/// App bar for [WorkoutScreen], showing the running clock and the two
/// destructive actions.
///
/// A widget rather than a method so the state class stays under the file-length
/// cap; it reads only what it is given and never calls `setState` itself.
class _WorkoutAppBar extends StatelessWidget implements PreferredSizeWidget {
  const _WorkoutAppBar({
    required this.title,
    required this.finished,
    required this.allSetsCompleted,
    required this.onReset,
    required this.onFinish,
  });

  /// Full app-bar title, already including the formatted elapsed time.
  final String title;

  /// Whether the workout is over — hides both actions once true.
  final bool finished;

  /// Whether every set is tapped; Finish stays disabled until it is.
  final bool allSetsCompleted;

  /// Invoked when the user taps Reset.
  final VoidCallback onReset;

  /// Invoked when the user taps Finish.
  final VoidCallback onFinish;

  @override
  Size get preferredSize => const Size.fromHeight(kToolbarHeight);

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final status = Theme.of(context).extension<AppStatusColors>()!;
    return AppBar(
      automaticallyImplyLeading: false,
      backgroundColor: colorScheme.surfaceContainerHigh,
      title: Text(title, style: TextStyle(color: colorScheme.onSurface)),
      actions: [
        if (!finished)
          TextButton(
            onPressed: onReset,
            child: Text('Reset', style: TextStyle(color: colorScheme.error)),
          ),
        if (!finished)
          TextButton(
            onPressed: allSetsCompleted ? onFinish : null,
            child: Text(
              'Finish',
              style: TextStyle(
                color: allSetsCompleted
                    ? status.success
                    : colorScheme.onSurfaceVariant,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
      ],
    );
  }
}
