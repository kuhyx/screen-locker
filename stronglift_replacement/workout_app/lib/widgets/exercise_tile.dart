/// Card widget for a single exercise showing warmup and main-set rep circles.
library;

import 'package:flutter/material.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/rep_circle.dart';

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

class _ThresholdRow extends StatelessWidget {
  const _ThresholdRow({
    required this.successThreshold,
    required this.failThreshold,
    required this.onSuccessChanged,
    required this.onFailChanged,
  });

  final int successThreshold;
  final int failThreshold;
  final ValueChanged<int> onSuccessChanged;
  final ValueChanged<int> onFailChanged;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final status = Theme.of(context).extension<AppStatusColors>()!;
    final captionStyle = TextStyle(
      color: colorScheme.onSurfaceVariant,
      fontSize: AppTextSize.caption,
    );
    return Row(
      children: [
        Icon(Icons.trending_up, size: 13, color: status.success),
        const SizedBox(width: 4),
        Text('after', style: captionStyle),
        const SizedBox(width: 6),
        _MiniStepper(
          value: successThreshold,
          onChanged: onSuccessChanged,
        ),
        const SizedBox(width: 4),
        Text('↑', style: captionStyle),
        const Spacer(),
        Icon(Icons.trending_down, size: 13, color: colorScheme.error),
        const SizedBox(width: 4),
        Text('after', style: captionStyle),
        const SizedBox(width: 6),
        _MiniStepper(
          value: failThreshold,
          onChanged: onFailChanged,
        ),
        const SizedBox(width: 4),
        Text('↓', style: captionStyle),
      ],
    );
  }
}

class _MiniStepper extends StatelessWidget {
  const _MiniStepper({required this.value, required this.onChanged});

  final int value;
  final ValueChanged<int> onChanged;

  static const _min = 1;
  static const _max = 5;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        _btn(
          context,
          Icons.remove,
          value > _min ? () => onChanged(value - 1) : null,
        ),
        SizedBox(
          width: 22,
          child: Text(
            '$value',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: colorScheme.onSurface,
              fontSize: AppTextSize.caption,
            ),
          ),
        ),
        _btn(
          context,
          Icons.add,
          value < _max ? () => onChanged(value + 1) : null,
        ),
      ],
    );
  }

  Widget _btn(BuildContext context, IconData icon, VoidCallback? onTap) {
    final colorScheme = Theme.of(context).colorScheme;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 22,
        height: 22,
        decoration: BoxDecoration(
          color: colorScheme.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(4),
        ),
        alignment: Alignment.center,
        child: Icon(
          icon,
          size: 12,
          color: onTap != null
              ? colorScheme.onSurface
              : colorScheme.onSurfaceVariant,
        ),
      ),
    );
  }
}

class _WarmupRow extends StatelessWidget {
  const _WarmupRow({
    required this.warmupWeight,
    required this.tapped,
    required this.onTap,
  });

  final double warmupWeight;
  final bool tapped;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final status = Theme.of(context).extension<AppStatusColors>()!;
    final mutedStyle = TextStyle(
      color: colorScheme.onSurfaceVariant,
      fontSize: AppTextSize.caption,
    );
    return Row(
      children: [
        Text('Warmup  1×5×', style: mutedStyle),
        Text('${warmupWeight}kg', style: mutedStyle),
        const SizedBox(width: 10),
        GestureDetector(
          onTap: tapped ? null : onTap,
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            width: 36,
            height: 36,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              // Tapped = a completed milestone, same semantic as every other
              // "done" indicator in this app (rep circles, calendar days).
              color: tapped ? status.success : Colors.transparent,
              border: Border.all(
                color: tapped ? status.success : colorScheme.outline,
                width: 2,
              ),
            ),
            alignment: Alignment.center,
            child: Icon(
              tapped ? Icons.check : Icons.fitness_center,
              // on-fill on the filled circle; muted on the empty outline one.
              color: tapped
                  ? colorScheme.onPrimary
                  : colorScheme.onSurfaceVariant,
              size: 16,
            ),
          ),
        ),
        const SizedBox(width: 6),
        Text(
          tapped ? 'done' : 'optional',
          style: TextStyle(
            color: tapped ? status.success : colorScheme.onSurfaceVariant,
            fontSize: AppTextSize.caption,
          ),
        ),
      ],
    );
  }
}
