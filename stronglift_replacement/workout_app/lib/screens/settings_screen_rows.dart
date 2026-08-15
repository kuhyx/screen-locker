// Section header and the reps/weight adjustment rows.
//
// `part` files: these widgets are library-private and stay that way.
// See history_screen_charts.dart for the full reasoning.
part of 'settings_screen.dart';

class _SectionHeader extends StatelessWidget {
  const _SectionHeader(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: TextStyle(
        color: Theme.of(context).colorScheme.onSurfaceVariant,
        fontSize: AppTextSize.caption,
        letterSpacing: 1.4,
      ),
    );
  }
}

class _RepsRow extends StatelessWidget {
  const _RepsRow({
    required this.name,
    required this.reps,
    required this.onChanged,
  });

  final String name;
  final int reps;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        children: [
          Expanded(
            child: Text(
              name,
              style: TextStyle(
                color: colorScheme.onSurfaceVariant,
                fontSize: AppTextSize.label,
              ),
            ),
          ),
          _StepperButton(
            icon: Icons.remove,
            onTap: () => onChanged((reps - 1).clamp(1, 999)),
          ),
          SizedBox(
            width: 72,
            child: Text(
              '$reps reps',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: colorScheme.onSurface,
                fontSize: AppTextSize.label,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
          _StepperButton(
            icon: Icons.add,
            onTap: () => onChanged((reps + 1).clamp(1, 999)),
          ),
        ],
      ),
    );
  }
}

class _WeightRow extends StatelessWidget {
  const _WeightRow({
    required this.name,
    required this.weight,
    required this.onChanged,
  });

  final String name;
  final double weight;
  final ValueChanged<double> onChanged;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        children: [
          Expanded(
            child: Text(
              name,
              style: TextStyle(
                color: colorScheme.onSurfaceVariant,
                fontSize: AppTextSize.label,
              ),
            ),
          ),
          _StepperButton(
            icon: Icons.remove,
            onTap: () => onChanged(
              (weight - kWeightIncrement).clamp(0.0, 999.0),
            ),
          ),
          // Fixed-width container supports up to "999.9kg" (7 chars).
          SizedBox(
            width: 72,
            child: Text(
              '${weight}kg',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: colorScheme.onSurface,
                fontSize: AppTextSize.label,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
          _StepperButton(
            icon: Icons.add,
            onTap: () => onChanged(weight + kWeightIncrement),
          ),
        ],
      ),
    );
  }
}

class _StepperButton extends StatelessWidget {
  const _StepperButton({required this.icon, required this.onTap});

  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 36,
        height: 36,
        decoration: BoxDecoration(
          color: colorScheme.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(6),
        ),
        alignment: Alignment.center,
        child: Icon(icon, color: colorScheme.onSurface, size: 18),
      ),
    );
  }
}
