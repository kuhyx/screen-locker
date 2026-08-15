/// Card widget for a single exercise showing warmup and main-set rep circles.
library;

import 'package:flutter/material.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/rep_circle.dart';

part 'exercise_tile_rows.dart';

/// Card widget displaying warmup and working-set rep circles for one exercise.
class ExerciseTile extends StatelessWidget {
  /// Creates an [ExerciseTile].
  const ExerciseTile({
    required this.exercise,
    required this.tapped,
    required this.doneReps,
    required this.warmupTapped,
    required this.successThreshold,
    required this.failThreshold,
    required this.onTapCircle,
    required this.onLongPressCircle,
    required this.onTapWarmup,
    required this.onThresholdChanged,
    super.key,
  });

  /// The exercise definition to display.
  final Exercise exercise;

  /// Per-set tap state; true when a set circle has been tapped.
  final List<bool> tapped;

  /// Per-set rep count; may be less than target after repeated taps.
  final List<int> doneReps;

  /// Whether the warmup circle has been tapped.
  final bool warmupTapped;

  /// Success streak threshold shown in the inline settings row.
  final int successThreshold;

  /// Fail streak threshold shown in the inline settings row.
  final int failThreshold;

  /// Called when a working-set circle is tapped.
  final void Function(int setIdx) onTapCircle;

  /// Called when a working-set circle is long-pressed (resets to neutral).
  final void Function(int setIdx) onLongPressCircle;

  /// Called when the warmup circle is tapped.
  final VoidCallback onTapWarmup;

  /// Called when the user changes thresholds inline (newSuccess, newFail).
  final void Function(int success, int fail) onThresholdChanged;

  bool get _allCompleted => tapped.every((t) => t);

  bool get _allSucceeded =>
      _allCompleted && doneReps.every((r) => r >= exercise.reps);

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final status = Theme.of(context).extension<AppStatusColors>()!;
    var headerColor = colorScheme.surfaceContainerHigh;
    if (_allCompleted) {
      headerColor = _allSucceeded ? status.success : colorScheme.error;
    }
    // A filled success/danger card needs on-fill text throughout (tokens.md:
    // one on-fill value for all four fills, never a per-fill judgment call).
    final onHeader = _allCompleted
        ? colorScheme.onPrimary
        : colorScheme.onSurface;
    final onHeaderMuted = _allCompleted
        ? colorScheme.onPrimary
        : colorScheme.onSurfaceVariant;

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
                    style: TextStyle(
                      color: onHeader,
                      fontWeight: FontWeight.bold,
                      fontSize: AppTextSize.body,
                    ),
                  ),
                ),
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
            if (exercise.hasWarmup) ...[
              _WarmupRow(
                warmupWeight: exercise.warmupWeight,
                tapped: warmupTapped,
                onTap: onTapWarmup,
              ),
              const SizedBox(height: 10),
            ],
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: List.generate(
                exercise.sets,
                (s) => RepCircle(
                  targetReps: exercise.reps,
                  doneReps: doneReps[s],
                  tapped: tapped[s],
                  onTap: () => onTapCircle(s),
                  onLongPress: () => onLongPressCircle(s),
                ),
              ),
            ),
            // Color inherited from the shared dividerTheme (line-dark).
            const Divider(height: 20),
            _ThresholdRow(
              successThreshold: successThreshold,
              failThreshold: failThreshold,
              onSuccessChanged: (v) => onThresholdChanged(v, failThreshold),
              onFailChanged: (v) => onThresholdChanged(successThreshold, v),
            ),
          ],
        ),
      ),
    );
  }
}
