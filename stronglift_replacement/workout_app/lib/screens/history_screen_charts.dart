// Chart and stat sub-widgets for HistoryScreen.
//
// A `part` rather than its own library: these widgets are private to
// history_screen.dart and stay that way, so the split is a pure move and
// public_member_api_docs does not start demanding docs for them.
part of 'history_screen.dart';

// ── Shared sub-widgets ──────────────────────────────────────────────────────

class _SectionLabel extends StatelessWidget {
  const _SectionLabel(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: TextStyle(
        color: Theme.of(context).colorScheme.onSurfaceVariant,
        fontSize: AppTextSize.caption,
        letterSpacing: 1.3,
      ),
    );
  }
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
              child: Text(
                n,
                style: TextStyle(
                  color: n == _kTotal
                      ? colorScheme.onSurfaceVariant
                      : colorScheme.onSurface,
                  fontStyle: n == _kTotal ? FontStyle.italic : FontStyle.normal,
                ),
              ),
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

  String _nextWeightLabel(double current, double max, double inc) {
    if (current >= max) return '+1 rep';
    return '+${inc}kg (${(current + inc).clamp(0.0, max)}kg)';
  }

  String _prevWeightLabel(double current, double inc) {
    return '-${inc}kg (${(current - inc).clamp(0.0, double.infinity)}kg)';
  }

  @override
  Widget build(BuildContext context) {
    final successLeft = state.successThreshold - state.successStreak;
    final failLeft = state.failThreshold - state.failStreak;

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
            '${state.name}  —  ${state.weight}kg',
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
            leftLabel: '$successLeft more',
            actionLabel: _nextWeightLabel(
              state.weight,
              state.maxWeight,
              kWeightIncrement,
            ),
            direction: '↑',
          ),
          const SizedBox(height: 6),
          _StreakRow(
            icon: Icons.trending_down,
            color: colorScheme.error,
            current: state.failStreak,
            threshold: state.failThreshold,
            leftLabel: '$failLeft more',
            actionLabel: _prevWeightLabel(state.weight, kWeightIncrement),
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
    required this.leftLabel,
    required this.actionLabel,
    required this.direction,
  });

  final IconData icon;
  final Color color;
  final int current;
  final int threshold;
  final String leftLabel;
  final String actionLabel;
  final String direction;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Row(
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
              color: i < current ? color : colorScheme.surfaceContainerHighest,
            ),
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            '$leftLabel to $direction $actionLabel',
            style: TextStyle(
              color: colorScheme.onSurfaceVariant,
              fontSize: AppTextSize.caption,
            ),
          ),
        ),
      ],
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
        child: Text(
          'Not enough data for chart',
          style: TextStyle(color: colorScheme.onSurfaceVariant),
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
