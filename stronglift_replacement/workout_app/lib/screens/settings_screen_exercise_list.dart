// The PER EXERCISE section: one row per exercise, opening the same settings
// sheet as the mode chip on its workout tile.
//
// See settings_screen_rows.dart for why this is a `part` file. Reusing the
// sheet rather than mirroring its controls here is the point: the two
// surfaces cannot drift apart when there is only one of them.
part of 'settings_screen.dart';

/// The PER EXERCISE section.
class _ExercisesSection extends StatelessWidget {
  const _ExercisesSection({
    required this.orderedNames,
    required this.states,
    required this.onOpen,
  });

  /// Exercise names in display order.
  final List<String> orderedNames;

  /// Stored state per exercise; a missing entry renders nothing.
  final Map<String, ExerciseState> states;

  /// Opens the settings sheet for the tapped exercise.
  final ValueChanged<ExerciseState> onOpen;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const _SectionHeader('PER EXERCISE'),
        const SizedBox(height: 4),
        Text(
          'Progression, warmup, rest and injury pause. '
          'Same settings as the workout tile.',
          style: TextStyle(
            color: colorScheme.onSurfaceVariant,
            fontSize: AppTextSize.caption,
          ),
        ),
        const SizedBox(height: 12),
        ...orderedNames.map((name) {
          final s = states[name];
          if (s == null) return const SizedBox.shrink();
          return _ExerciseSettingsRow(state: s, onTap: () => onOpen(s));
        }),
      ],
    );
  }
}

/// `Squat` over `kg · ↑3 ↓2 · rest 3:00 / 5:00 · warmup 3:00`.
class _ExerciseSettingsRow extends StatelessWidget {
  const _ExerciseSettingsRow({required this.state, required this.onTap});

  final ExerciseState state;
  final VoidCallback onTap;

  String get _summary {
    final s = state;
    final mode = switch (s.mode) {
      ProgressionMode.weight => 'kg',
      ProgressionMode.reps => 'reps',
      ProgressionMode.doubleProgression => '${s.repsLow}→${s.repsHigh} reps',
    };
    final warmup = s.hasWarmup
        ? 'warmup ${formatRest(s.restWarmupSecs)}'
        : 'no warmup';
    return '$mode · ↑${s.successThreshold} ↓${s.failThreshold} · '
        'rest ${formatRest(s.restSuccessSecs)} / '
        '${formatRest(s.restFailSecs)} · $warmup';
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final until = state.isPausedAt(DateTime.now()) ? state.pausedUntil : null;
    return Semantics(
      container: true,
      button: true,
      label: '${state.name} exercise settings',
      excludeSemantics: true,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(AppRadius.sm),
        child: Container(
          margin: const EdgeInsets.only(bottom: 12),
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: colorScheme.surfaceContainerHigh,
            borderRadius: BorderRadius.circular(AppRadius.sm),
          ),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      state.name,
                      style: TextStyle(
                        color: colorScheme.onSurface,
                        fontWeight: FontWeight.bold,
                        fontSize: AppTextSize.label,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      _summary,
                      style: TextStyle(
                        color: colorScheme.onSurfaceVariant,
                        fontSize: AppTextSize.caption,
                      ),
                    ),
                    if (until != null) ...[
                      const SizedBox(height: 4),
                      Text(
                        'Paused — back on ${formatShortDate(until)}',
                        style: TextStyle(
                          color: colorScheme.error,
                          fontSize: AppTextSize.caption,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              Icon(Icons.tune, color: colorScheme.onSurfaceVariant),
            ],
          ),
        ),
      ),
    );
  }
}
