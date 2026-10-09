// The active-workout body: a reserved break strip over the exercise column.
//
// See workout_screen_session.dart for why this is a `part`.
part of 'workout_screen.dart';

/// Non-scrolling exercise column for [WorkoutScreen] under a reserved rest
/// strip.
///
/// Every tile stays visible and in place under all circumstances: the strip
/// is always laid out (so a rest starting moves nothing), and the column is
/// scaled down as a whole when it would not fit, instead of scrolling.
///
/// A widget rather than a method so the state class stays under the
/// file-length cap. It holds no state of its own — every value and callback is
/// passed in, and the `setState` that drives them stays in the state class.
class _WorkoutBody extends StatelessWidget {
  const _WorkoutBody({
    required this.exercises,
    required this.exerciseStates,
    required this.tapped,
    required this.doneReps,
    required this.warmupTapped,
    required this.inBreak,
    required this.breakRemaining,
    required this.finished,
    required this.syncNotSetUp,
    required this.allSetsCompleted,
    required this.onSkipBreak,
    required this.onReset,
    required this.onFinish,
    required this.onTapCircle,
    required this.onLongPressCircle,
    required this.onTapWarmup,
    required this.onSettingsChanged,
    required this.onDeload,
  });

  /// The exercises in this session, in display order.
  final List<Exercise> exercises;

  /// Progression state per exercise name; a missing entry (not loaded yet)
  /// falls back to [ExerciseState.initial] for this session's targets.
  final Map<String, ExerciseState> exerciseStates;

  /// Per-exercise, per-set completion flags.
  final List<List<bool>> tapped;

  /// Per-exercise, per-set completed rep counts.
  final List<List<int>> doneReps;

  /// Per-exercise warmup completion flags.
  final List<bool> warmupTapped;

  /// Whether a rest period is running; shows the banner when true.
  final bool inBreak;

  /// Seconds left in the current rest period.
  final int breakRemaining;

  /// Whether the workout is over; hides Reset and Finish.
  final bool finished;

  /// Whether to show the "sync not set up" strip above the rest strip.
  final bool syncNotSetUp;

  /// Whether every set is recorded; enables Finish.
  final bool allSetsCompleted;

  /// Invoked when the user skips the rest period.
  final VoidCallback onSkipBreak;

  /// Invoked when the user taps Reset.
  final VoidCallback onReset;

  /// Invoked when the user taps Finish.
  final VoidCallback onFinish;

  /// Invoked with (exerciseIndex, setIndex) when a set circle is tapped.
  final void Function(int exIdx, int setIdx) onTapCircle;

  /// Invoked with (exerciseIndex, setIndex) when a set circle is long-pressed.
  final void Function(int exIdx, int setIdx) onLongPressCircle;

  /// Invoked with the exercise index when its warmup is tapped.
  final void Function(int exIdx) onTapWarmup;

  /// Invoked with the edited state after every settings-sheet change.
  final ValueChanged<ExerciseState> onSettingsChanged;

  /// Invoked with the exercise index on a confirmed "Deload now"; resolves to
  /// the exercise's new state, or null when nothing changed.
  final Future<ExerciseState?> Function(int exIdx) onDeload;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        if (syncNotSetUp) const SyncSetupBanner(),
        BreakBanner(
          active: inBreak,
          breakRemaining: breakRemaining,
          onSkip: onSkipBreak,
          finished: finished,
          canFinish: allSetsCompleted,
          onReset: onReset,
          onFinish: onFinish,
        ),
        Expanded(
          child: LayoutBuilder(
            builder: (context, constraints) => FittedBox(
              fit: BoxFit.scaleDown,
              alignment: Alignment.topCenter,
              child: SizedBox(
                width: constraints.maxWidth,
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      for (var i = 0; i < exercises.length; i++) ...[
                        if (i > 0) const SizedBox(height: 8),
                        _tile(i),
                      ],
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _tile(int i) {
    final ex = exercises[i];
    return ExerciseTile(
      exercise: ex,
      state: exerciseStates[ex.name] ?? ExerciseState.initial(ex),
      tapped: tapped[i],
      doneReps: doneReps[i],
      warmupTapped: warmupTapped[i],
      onTapCircle: (s) => onTapCircle(i, s),
      onLongPressCircle: (s) => onLongPressCircle(i, s),
      onTapWarmup: () => onTapWarmup(i),
      onSettingsChanged: onSettingsChanged,
      onDeload: () => onDeload(i),
    );
  }
}
