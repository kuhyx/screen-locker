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
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // textgate: the helper sentence under the heading is gone.
        const _SectionHeader(Icons.tune, 'PER EXERCISE'),
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

  // textgate: was "kg · ↑3 ↓2 · rest 3:00 / 5:00 · warmup 1:00" (or
  // "no warmup"). Now the mode glyph (or rep range), the thresholds, a
  // timer glyph before the rests, and a sun glyph before the warmup rest
  // (absent when there is no warmup).
  Widget _summary(Color color) {
    final s = state;
    final style = TextStyle(color: color, fontSize: AppTextSize.caption);
    final modeIcon = switch (s.mode) {
      ProgressionMode.weight => Icons.fitness_center,
      ProgressionMode.reps => Icons.repeat,
      ProgressionMode.doubleProgression => null,
    };
    return Row(
      key: const Key('exercise_settings_summary'),
      children: [
        if (modeIcon == null)
          Text('${s.repsLow}→${s.repsHigh}', style: style)
        else
          Icon(modeIcon, size: 14, color: color),
        Text('  ↑${s.successThreshold} ↓${s.failThreshold}  ', style: style),
        Icon(Icons.timer, size: 14, color: color),
        Text(
          ' ${formatRest(s.restSuccessSecs)} / ${formatRest(s.restFailSecs)}',
          style: style,
        ),
        if (s.hasWarmup) ...[
          const SizedBox(width: 8),
          Icon(Icons.wb_sunny, size: 14, color: color),
          Text(' ${formatRest(s.restWarmupSecs)}', style: style),
        ],
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final until = state.isPausedAt(DateTime.now()) ? state.pausedUntil : null;
    // Spoken only: excludeSemantics hides the painted children from it.
    final semanticsLabel = '${state.name} exercise settings';
    return Semantics(
      container: true,
      button: true,
      label: semanticsLabel,
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
                    _summary(colorScheme.onSurfaceVariant),
                    if (until != null) ...[
                      const SizedBox(height: 4),
                      // textgate: was "Paused — back on 11 Oct".
                      Row(
                        children: [
                          Icon(
                            Icons.pause_circle_outline,
                            size: 14,
                            color: colorScheme.error,
                          ),
                          const SizedBox(width: 4),
                          Text(
                            formatShortDate(until),
                            style: TextStyle(
                              color: colorScheme.error,
                              fontSize: AppTextSize.caption,
                            ),
                          ),
                        ],
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
