// Section header and the reps/weight adjustment rows.
//
// `part` files: these widgets are library-private and stay that way.
// See history_screen_charts.dart for the full reasoning.
part of 'settings_screen.dart';

/// A section heading as a glyph (textgate: was an all-caps word; the word
/// survives as [spoken], the glyph's semantic label).
class _SectionHeader extends StatelessWidget {
  const _SectionHeader(this.icon, this.spoken);

  final IconData icon;
  final String spoken;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Icon(
        icon,
        size: 20,
        color: Theme.of(context).colorScheme.onSurfaceVariant,
        semanticLabel: spoken,
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
              // textgate: was "12 reps"; the section's repeat glyph says it.
              '×$reps',
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
            onTap: () =>
                onChanged((weight - kWeightIncrement).clamp(0.0, 999.0)),
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

/// An action's outcome as a glyph: a tick (success colour) or a warning
/// sign (warning colour). textgate: replaces a painted status sentence;
/// the sentence survives as [spoken], the glyph's semantic label.
class _StatusGlyph extends StatelessWidget {
  const _StatusGlyph({required this.ok, required this.spoken, super.key});

  final bool ok;
  final String spoken;

  @override
  Widget build(BuildContext context) {
    final status = Theme.of(context).extension<AppStatusColors>()!;
    return Align(
      alignment: Alignment.centerLeft,
      child: Icon(
        ok ? Icons.check_circle : Icons.error_outline,
        size: 18,
        color: ok ? status.success : status.warning,
        semanticLabel: spoken,
      ),
    );
  }
}
