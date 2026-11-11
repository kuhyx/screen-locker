// Chart and stat sub-widgets for HistoryScreen.
//
// A `part` rather than its own library: these widgets are private to
// history_screen.dart and stay that way, so the split is a pure move and
// public_member_api_docs does not start demanding docs for them.
part of 'history_screen.dart';

// ── Shared sub-widgets ──────────────────────────────────────────────────────

/// A section heading as a glyph (textgate: was an all-caps word heading;
/// the words survive as [spoken], the glyph's semantic label).
class _SectionLabel extends StatelessWidget {
  const _SectionLabel(this.icon, this.spoken);

  final IconData icon;
  final String spoken;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Icon(
        icon,
        size: 18,
        color: Theme.of(context).colorScheme.onSurfaceVariant,
        semanticLabel: spoken,
      ),
    );
  }
}

/// The empty history: a large muted history glyph (textgate: was "No
/// workouts yet.").
class _EmptyHistory extends StatelessWidget {
  const _EmptyHistory();

  @override
  Widget build(BuildContext context) => Center(
    child: Icon(
      Icons.history,
      size: 48,
      color: Theme.of(context).colorScheme.outlineVariant,
      semanticLabel: 'No workouts yet.',
    ),
  );
}

class _ExercisePicker extends StatelessWidget {
  const _ExercisePicker({
    required this.names,
    required this.selected,
    required this.onChanged,
  });

  final List<String> names;
  final String selected;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return DropdownButton<String>(
      value: selected,
      dropdownColor: colorScheme.surfaceContainerHigh,
      style: TextStyle(color: colorScheme.onSurface),
      underline: const SizedBox(),
      isExpanded: true,
      items: names
          .map(
            (n) => DropdownMenuItem(
              value: n,
              // textgate: the all-workouts entry is a sum glyph (was
              // "Total (all workouts)"); exercise names are content.
              child: n == _kTotal
                  ? Align(
                      alignment: Alignment.centerLeft,
                      child: Icon(
                        Icons.functions,
                        color: colorScheme.onSurfaceVariant,
                        semanticLabel: _kTotal,
                      ),
                    )
                  : Text(n, style: TextStyle(color: colorScheme.onSurface)),
            ),
          )
          .toList(),
      onChanged: (v) {
        if (v != null) onChanged(v);
      },
    );
  }
}

class _ProgressStatsCard extends StatelessWidget {
  const _ProgressStatsCard({required this.state});

  final ExerciseState state;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final status = Theme.of(context).extension<AppStatusColors>()!;
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainerHigh,
        borderRadius: BorderRadius.circular(AppRadius.sm),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '${state.name}  —  ${state.weight}kg × ${state.reps}',
            style: TextStyle(
              color: colorScheme.onSurface,
              fontWeight: FontWeight.bold,
              fontSize: AppTextSize.label,
            ),
          ),
          const SizedBox(height: 8),
          _StreakRow(
            icon: Icons.trending_up,
            color: status.success,
            current: state.successStreak,
            threshold: state.successThreshold,
            // The same rule applyProgression runs, in every mode.
            actionLabel: describeTargetChange(state, targetAfterSuccess(state)),
            direction: '↑',
          ),
          const SizedBox(height: 6),
          _StreakRow(
            icon: Icons.trending_down,
            color: colorScheme.error,
            current: state.failStreak,
            threshold: state.failThreshold,
            actionLabel: describeTargetChange(state, targetAfterFailure(state)),
            direction: '↓',
          ),
        ],
      ),
    );
  }
}

class _StreakRow extends StatelessWidget {
  const _StreakRow({
    required this.icon,
    required this.color,
    required this.current,
    required this.threshold,
    required this.actionLabel,
    required this.direction,
  });

  final IconData icon;
  final Color color;
  final int current;
  final int threshold;
  final String actionLabel;
  final String direction;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    // The streak is shown counting up to its real value; the dots fill and the
    // "more" number falls in step. At rest it is exactly the stored streak.
    return AnimatedCounter(
      value: current,
      builder: (shown) => Row(
        children: [
          Icon(icon, color: color, size: 14),
          const SizedBox(width: 6),
          ...List.generate(
            threshold,
            (i) => Container(
              width: 8,
              height: 8,
              margin: const EdgeInsets.only(right: 3),
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: i < shown ? color : colorScheme.surfaceContainerHighest,
              ),
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              // textgate: was "2 more to ↑ 25 kg".
              '${threshold - shown}  $direction $actionLabel',
              style: TextStyle(
                color: colorScheme.onSurfaceVariant,
                fontSize: AppTextSize.caption,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _WeightChart extends StatelessWidget {
  const _WeightChart({required this.points});

  final List<(DateTime, double)> points;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    if (points.length < 2) {
      return Container(
        height: 80,
        alignment: Alignment.center,
        // textgate: was "Not enough data for chart".
        child: Icon(
          Icons.show_chart,
          color: colorScheme.outlineVariant,
          semanticLabel: 'Not enough data for chart',
        ),
      );
    }
    return SizedBox(
      height: 140,
      child: CustomPaint(
        painter: _ChartPainter(
          points,
          lineColor: colorScheme.primary,
          labelColor: colorScheme.onSurfaceVariant,
        ),
        size: Size.infinite,
      ),
    );
  }
}
