// The active-workout body: optional break banner over the exercise list.
//
// See workout_screen_session.dart for why this is a `part`.
part of 'workout_screen.dart';

/// Scrolling exercise list for [WorkoutScreen], with the rest banner above it.
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
    required this.breakLabel,
    required this.onSkipBreak,
    required this.onTapCircle,
    required this.onLongPressCircle,
    required this.onTapWarmup,
    required this.onThresholdChanged,
  });

  /// The exercises in this session, in display order.
  final List<Exercise> exercises;

  /// Progression state per exercise name; a missing entry falls back to
  /// the tile's default thresholds.
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

  /// Human-readable label for the current rest period.
  final String breakLabel;

  /// Invoked when the user skips the rest period.
  final VoidCallback onSkipBreak;

  /// Invoked with (exerciseIndex, setIndex) when a set circle is tapped.
  final void Function(int exIdx, int setIdx) onTapCircle;

  /// Invoked with (exerciseIndex, setIndex) when a set circle is long-pressed.
  final void Function(int exIdx, int setIdx) onLongPressCircle;

  /// Invoked with the exercise index when its warmup is tapped.
  final void Function(int exIdx) onTapWarmup;

  /// Invoked with (exerciseName, successThreshold, failThreshold) on edit.
  final void Function(String name, int success, int fail) onThresholdChanged;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        if (inBreak)
          BreakBanner(
            breakRemaining: breakRemaining,
            breakLabel: breakLabel,
            onSkip: onSkipBreak,
          ),
        Expanded(
          child: ListView.separated(
            padding: const EdgeInsets.all(12),
            itemCount: exercises.length,
            separatorBuilder: (_, _) => const SizedBox(height: 8),
            itemBuilder: (_, i) {
              final exName = exercises[i].name;
              final state = exerciseStates[exName];
              return ExerciseTile(
                exercise: exercises[i],
                tapped: tapped[i],
                doneReps: doneReps[i],
                warmupTapped: warmupTapped[i],
                successThreshold: state?.successThreshold ?? 3,
                failThreshold: state?.failThreshold ?? 2,
                onTapCircle: (s) => onTapCircle(i, s),
                onLongPressCircle: (s) => onLongPressCircle(i, s),
                onTapWarmup: () => onTapWarmup(i),
                onThresholdChanged: (success, fail) =>
                    onThresholdChanged(exName, success, fail),
              );
            },
          ),
        ),
      ],
    );
  }
}
