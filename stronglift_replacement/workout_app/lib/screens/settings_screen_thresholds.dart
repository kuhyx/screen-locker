// The stepper button and the per-exercise threshold card.
//
// See settings_screen_rows.dart for why these are `part` files.
part of 'settings_screen.dart';

class _ExerciseThresholdCard extends StatelessWidget {
  const _ExerciseThresholdCard({
    required this.name,
    required this.successThreshold,
    required this.failThreshold,
    required this.onSuccessChanged,
    required this.onFailChanged,
  });

  final String name;
  final int successThreshold;
  final int failThreshold;
  final ValueChanged<int> onSuccessChanged;
  final ValueChanged<int> onFailChanged;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final status = Theme.of(context).extension<AppStatusColors>()!;
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainerHigh,
        borderRadius: BorderRadius.circular(AppRadius.sm),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            name,
            style: TextStyle(
              color: colorScheme.onSurface,
              fontWeight: FontWeight.bold,
              fontSize: AppTextSize.label,
            ),
          ),
          const SizedBox(height: 10),
          _ThresholdRow(
            label: '↑ Increase after N successes',
            value: successThreshold,
            color: status.success,
            onChanged: onSuccessChanged,
          ),
          const SizedBox(height: 6),
          _ThresholdRow(
            label: '↓ Decrease after N failures',
            value: failThreshold,
            color: colorScheme.error,
            onChanged: onFailChanged,
          ),
        ],
      ),
    );
  }
}

class _ThresholdRow extends StatelessWidget {
  const _ThresholdRow({
    required this.label,
    required this.value,
    required this.color,
    required this.onChanged,
  });

  final String label;
  final int value;
  final Color color;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Row(
      children: [
        Expanded(
          child: Text(
            label,
            style: TextStyle(
              color: colorScheme.onSurfaceVariant,
              fontSize: AppTextSize.caption,
            ),
          ),
        ),
        const SizedBox(width: 8),
        for (int i = 1; i <= 5; i++)
          Padding(
            padding: const EdgeInsets.only(left: 4),
            child: GestureDetector(
              onTap: () => onChanged(i),
              child: Container(
                width: 32,
                height: 32,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: i == value
                      ? color
                      : colorScheme.surfaceContainerHighest,
                ),
                alignment: Alignment.center,
                child: Text(
                  '$i',
                  style: TextStyle(
                    // on-fill on the selected (filled) circle.
                    color: i == value
                        ? colorScheme.onPrimary
                        : colorScheme.onSurface,
                    fontWeight: FontWeight.bold,
                    fontSize: AppTextSize.label,
                  ),
                ),
              ),
            ),
          ),
      ],
    );
  }
}
