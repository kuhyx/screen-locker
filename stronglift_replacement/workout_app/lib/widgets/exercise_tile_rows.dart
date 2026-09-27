// Mode chip, inline warmup circle and progress line for ExerciseTile.
//
// `part` file: these widgets are library-private and stay that way.
// See history_screen_charts.dart for the full reasoning.
part of 'exercise_tile.dart';

/// Tappable chip naming the progression mode; opens the settings sheet.
///
/// Fixed width, so switching mode never moves the header's other text.
class _ModeChip extends StatelessWidget {
  const _ModeChip({
    required this.state,
    required this.color,
    required this.onTap,
  });

  final ExerciseState state;
  final Color color;
  final VoidCallback onTap;

  static const double width = 64;

  String get _text => switch (state.mode) {
    ProgressionMode.weight => 'kg',
    ProgressionMode.reps => 'reps',
    ProgressionMode.doubleProgression => '${state.repsLow}→${state.repsHigh}',
  };

  @override
  Widget build(BuildContext context) {
    return Semantics(
      container: true,
      button: true,
      label: '${state.name} progression settings',
      excludeSemantics: true,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(AppRadius.sm),
        child: Container(
          width: width,
          height: 26,
          decoration: BoxDecoration(
            border: Border.all(color: color),
            borderRadius: BorderRadius.circular(AppRadius.sm),
          ),
          alignment: Alignment.center,
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.tune, size: 13, color: color),
              const SizedBox(width: 3),
              Flexible(
                child: Text(
                  _text,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(color: color, fontSize: AppTextSize.caption),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// The warmup as the first circle of the set row: outlined, the size of a
/// set circle, showing `W×5` over the warmup weight.
class _WarmupCircle extends StatelessWidget {
  const _WarmupCircle({
    required this.semanticLabel,
    required this.warmupWeight,
    required this.tapped,
    required this.onTap,
  });

  final String semanticLabel;
  final double warmupWeight;
  final bool tapped;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final status = Theme.of(context).extension<AppStatusColors>()!;
    // Tapped = a completed milestone, same semantic as every other "done"
    // indicator in this app. On-fill ink on the filled circle; muted on the
    // outline-only one, which is what sets it apart from a working set.
    final fg = tapped ? colorScheme.onPrimary : colorScheme.onSurfaceVariant;
    final small = TextStyle(color: fg, fontSize: AppTextSize.caption);
    return GestureDetector(
      onTap: tapped ? null : onTap,
      child: Semantics(
        container: true,
        button: true,
        label: semanticLabel,
        excludeSemantics: true,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          width: 52,
          height: 52,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: tapped ? status.success : Colors.transparent,
            border: Border.all(
              color: tapped ? status.success : colorScheme.outline,
              width: 2,
            ),
          ),
          alignment: Alignment.center,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                'W×5',
                style: small.copyWith(fontWeight: FontWeight.bold, height: 1.1),
              ),
              Text('$warmupWeight', style: small.copyWith(height: 1.1)),
            ],
          ),
        ),
      ),
    );
  }
}

/// `↑ 2/3 → 25 kg` … `↓ 0/2 → 20 kg`: both streaks against their
/// thresholds, and what the next step up or down will set.
///
/// The targets come from the same rule `applyProgression` runs, so the
/// line cannot promise a step the finish would not take.
class _ProgressRow extends StatelessWidget {
  const _ProgressRow({required this.state, required this.onFill});

  final ExerciseState state;

  /// Whether the card is a filled success/danger colour.
  final bool onFill;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final status = Theme.of(context).extension<AppStatusColors>()!;
    final textColor = onFill
        ? colorScheme.onPrimary
        : colorScheme.onSurfaceVariant;
    final up = describeTargetChange(state, targetAfterSuccess(state));
    final down = describeTargetChange(state, targetAfterFailure(state));
    return Row(
      children: [
        Expanded(
          child: _half(
            Icons.trending_up,
            onFill ? textColor : status.success,
            '${state.successStreak}/${state.successThreshold} → $up',
            textColor,
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: _half(
            Icons.trending_down,
            onFill ? textColor : colorScheme.error,
            '${state.failStreak}/${state.failThreshold} → $down',
            textColor,
          ),
        ),
      ],
    );
  }

  Widget _half(IconData icon, Color iconColor, String text, Color color) {
    return Row(
      children: [
        Icon(icon, size: 14, color: iconColor),
        const SizedBox(width: 4),
        Expanded(
          child: Text(
            text,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(color: color, fontSize: AppTextSize.caption),
          ),
        ),
      ],
    );
  }
}

/// Stands in for the set row while the exercise is paused: same height, so
/// pausing moves nothing on the screen.
class _PausedRow extends StatelessWidget {
  const _PausedRow({required this.until, required this.color});

  final DateTime until;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: ExerciseTile.setRowHeight,
      child: Row(
        children: [
          Icon(Icons.pause_circle_outline, size: 20, color: color),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              'Paused — back on ${formatShortDate(until)} · counts as failed',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(color: color, fontSize: AppTextSize.label),
            ),
          ),
        ],
      ),
    );
  }
}
