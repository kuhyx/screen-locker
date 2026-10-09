/// Card widget for a single exercise: header with the progression-mode chip,
/// one row of warmup + set circles, and the progress line.
library;

import 'package:flutter/material.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/models/exercise_state.dart';
import 'package:workout_app/models/progression.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/exercise_settings_sheet.dart';
import 'package:workout_app/widgets/rep_circle.dart';

part 'exercise_tile_rows.dart';

/// Card widget displaying warmup and working-set rep circles for one exercise.
///
/// Its height is the same in every state — warmup on or off, any mode, any
/// streak, done or not — so the workout column never rescales mid-workout.
/// A disabled warmup leaves its slot empty rather than closing it up.
class ExerciseTile extends StatelessWidget {
  /// Creates an [ExerciseTile].
  const ExerciseTile({
    required this.exercise,
    required this.state,
    required this.tapped,
    required this.doneReps,
    required this.warmupTapped,
    required this.onTapCircle,
    required this.onLongPressCircle,
    required this.onTapWarmup,
    required this.onSettingsChanged,
    required this.onDeload,
    super.key,
  });

  /// The exercise definition to display (this session's targets).
  final Exercise exercise;

  /// Progression state: mode, streaks, thresholds, warmup toggle.
  final ExerciseState state;

  /// Per-set tap state; true when a set circle has been tapped.
  final List<bool> tapped;

  /// Per-set rep count; may be less than target after repeated taps.
  final List<int> doneReps;

  /// Whether the warmup circle has been tapped.
  final bool warmupTapped;

  /// Called when a working-set circle is tapped.
  final void Function(int setIdx) onTapCircle;

  /// Called when a working-set circle is long-pressed (resets to neutral).
  final void Function(int setIdx) onLongPressCircle;

  /// Called when the warmup circle is tapped.
  final VoidCallback onTapWarmup;

  /// Called with the edited state after every change in the settings sheet.
  final ValueChanged<ExerciseState> onSettingsChanged;

  /// Called when the user confirms "Deload now" in the settings sheet;
  /// returns the deloaded state, or null when nothing changed.
  final Future<ExerciseState?> Function() onDeload;

  /// Gap between circles in the set row.
  static const double circleGap = 8;

  /// Height of the set row; the paused placeholder takes exactly this.
  static const double setRowHeight = 52;

  bool get _allCompleted => tapped.every((t) => t);

  bool get _allSucceeded =>
      _allCompleted && doneReps.every((r) => r >= exercise.reps);

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final status = Theme.of(context).extension<AppStatusColors>()!;
    final paused = state.isPausedAt(DateTime.now());
    var headerColor = colorScheme.surfaceContainerHigh;
    // A paused card never turns green/red: its taps no longer count.
    if (_allCompleted && !paused) {
      headerColor = _allSucceeded ? status.success : colorScheme.error;
    }
    // A filled success/danger card needs on-fill text throughout (tokens.md:
    // one on-fill value for all four fills, never a per-fill judgment call).
    final filled = _allCompleted && !paused;
    final onHeaderMuted = filled
        ? colorScheme.onPrimary
        : colorScheme.onSurfaceVariant;
    // Paused: the whole header recedes to the muted ink.
    final onHeader = filled
        ? colorScheme.onPrimary
        : paused
        ? onHeaderMuted
        : colorScheme.onSurface;

    return Card(
      color: headerColor,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    exercise.name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: onHeader,
                      fontWeight: FontWeight.bold,
                      fontSize: AppTextSize.body,
                    ),
                  ),
                ),
                const SizedBox(width: 6),
                _ModeChip(
                  state: state,
                  color: onHeaderMuted,
                  onTap: () => showExerciseSettings(context),
                ),
                const SizedBox(width: 8),
                Text(
                  '${exercise.sets}×${exercise.reps}×${exercise.weight}kg',
                  style: TextStyle(
                    color: onHeaderMuted,
                    fontSize: AppTextSize.label,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            // A Row, not a Wrap: a set row that spilled onto a second line
            // would change the tile's height, and a Row overflowing fails
            // loudly in tests instead.
            if (paused)
              _PausedRow(until: state.pausedUntil!, color: onHeaderMuted)
            else
              Row(
                children: [
                  Visibility(
                    visible: state.hasWarmup,
                    maintainSize: true,
                    maintainAnimation: true,
                    maintainState: true,
                    child: _WarmupCircle(
                      semanticLabel: '${exercise.name} warmup',
                      warmupWeight: exercise.warmupWeight,
                      tapped: warmupTapped,
                      onTap: onTapWarmup,
                    ),
                  ),
                  for (var s = 0; s < exercise.sets; s++) ...[
                    const SizedBox(width: circleGap),
                    RepCircle(
                      semanticLabel: '${exercise.name} set ${s + 1}',
                      targetReps: exercise.reps,
                      doneReps: doneReps[s],
                      tapped: tapped[s],
                      onTap: () => onTapCircle(s),
                      onLongPress: () => onLongPressCircle(s),
                    ),
                  ],
                ],
              ),
            // Color inherited from the shared dividerTheme (line-dark).
            const Divider(height: 20),
            _ProgressRow(state: state, onFill: filled),
          ],
        ),
      ),
    );
  }

  /// Opens the settings sheet for this exercise.
  Future<void> showExerciseSettings(BuildContext context) =>
      showExerciseSettingsSheet(
        context,
        state: state,
        onChanged: onSettingsChanged,
        onDeload: onDeload,
      );
}
