// Threshold row, mini stepper and warm-up row for ExerciseTile.
//
// `part` file: these widgets are library-private and stay that way.
// See history_screen_charts.dart for the full reasoning.
part of 'exercise_tile.dart';

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
