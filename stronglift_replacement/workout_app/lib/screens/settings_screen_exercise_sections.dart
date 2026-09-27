// The WEIGHTS and TARGET REPS sections.
//
// A `part` for the same reason as settings_screen_sections.dart: these stay
// library-private. Each takes the ordered names plus the one map it reads, so
// every `if (x == null)` and `?? default` below is the one the original
// `build()` already had — the coverage gate is at 100% and a new branch is a
// line no test reaches.
part of 'settings_screen.dart';

/// The WEIGHTS section: per-exercise working-weight overrides.
class _WeightsSection extends StatelessWidget {
  const _WeightsSection({
    required this.orderedNames,
    required this.weights,
    required this.onWeightChanged,
  });

  /// Exercise names in display order.
  final List<String> orderedNames;

  /// Current working weight per exercise; a missing entry renders nothing.
  final Map<String, double> weights;

  /// Invoked with (name, newWeight) when a row changes.
  final void Function(String name, double value) onWeightChanged;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const _SectionHeader('WEIGHTS'),
        const SizedBox(height: 4),
        Text(
          'Override current working weight. '
          'Resets streak counters. Rounded to 2.5 kg.',
          style: TextStyle(
            color: colorScheme.onSurfaceVariant,
            fontSize: AppTextSize.caption,
          ),
        ),
        const SizedBox(height: 12),
        ...orderedNames.map((name) {
          final w = weights[name];
          if (w == null) return const SizedBox.shrink();
          return _WeightRow(
            name: name,
            weight: w,
            onChanged: (v) => onWeightChanged(name, v),
          );
        }),
      ],
    );
  }
}

/// The TARGET REPS section: per-exercise target-rep overrides.
class _RepsSection extends StatelessWidget {
  const _RepsSection({
    required this.orderedNames,
    required this.reps,
    required this.onRepsChanged,
  });

  /// Exercise names in display order.
  final List<String> orderedNames;

  /// Target reps per exercise; a missing entry renders nothing.
  final Map<String, int> reps;

  /// Invoked with (name, newReps) when a row changes.
  final void Function(String name, int value) onRepsChanged;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const _SectionHeader('TARGET REPS'),
        const SizedBox(height: 4),
        Text(
          'Override target reps per set. Resets streak counters. '
          'Progression only ever raises reps, so this is the only way '
          'to lower one.',
          style: TextStyle(
            color: colorScheme.onSurfaceVariant,
            fontSize: AppTextSize.caption,
          ),
        ),
        const SizedBox(height: 12),
        ...orderedNames.map((name) {
          final r = reps[name];
          if (r == null) return const SizedBox.shrink();
          return _RepsRow(
            name: name,
            reps: r,
            onChanged: (v) => onRepsChanged(name, v),
          );
        }),
      ],
    );
  }
}
