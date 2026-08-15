// The workout and status cards on the home screen.
//
// `part` file: these widgets are library-private and stay that way.
// See history_screen_charts.dart for the full reasoning.
part of 'home_screen.dart';

class _WorkoutCard extends StatelessWidget {
  const _WorkoutCard({
    required this.type,
    required this.exercises,
    required this.doneToday,
    required this.hasActiveSession,
    required this.onStart,
    required this.onResume,
  });

  final String type;
  final List<Exercise> exercises;
  final bool doneToday;
  final bool hasActiveSession;
  final VoidCallback onStart;
  final VoidCallback onResume;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final status = Theme.of(context).extension<AppStatusColors>()!;
    // Canonical button padding (rule 22): vertical 12, horizontal 24 — an
    // exact 2x ratio, both on the 4px spacing scale (tokens.md's own example).
    const buttonPadding = EdgeInsets.symmetric(horizontal: 24, vertical: 12);
    return Card(
      color: colorScheme.surfaceContainerHigh,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (doneToday && !hasActiveSession) ...[
              Row(
                children: [
                  Icon(Icons.check_circle, color: status.success, size: 18),
                  const SizedBox(width: 8),
                  Text(
                    'Done for today!',
                    style: TextStyle(
                      color: status.success,
                      fontWeight: FontWeight.bold,
                      fontSize: AppTextSize.body,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 6),
              Text(
                'Next: Workout $type — tomorrow',
                style: TextStyle(
                  color: colorScheme.onSurface,
                  fontSize: AppTextSize.body,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ] else ...[
              Text(
                hasActiveSession
                    ? 'Workout $type in progress'
                    : 'Next: Workout $type',
                style: TextStyle(
                  color: hasActiveSession
                      ? status.warning
                      : colorScheme.onSurface,
                  fontSize: AppTextSize.subtitle,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
            const SizedBox(height: 10),
            ...exercises.map(
              (e) => Text(
                '${e.name}  ${e.sets}×${e.reps}×${e.weight}kg',
                style: TextStyle(
                  color: colorScheme.onSurfaceVariant,
                  fontSize: AppTextSize.label,
                ),
              ),
            ),
            const SizedBox(height: 14),
            if (hasActiveSession)
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  style: ElevatedButton.styleFrom(
                    backgroundColor: status.warning,
                    padding: buttonPadding,
                  ),
                  onPressed: onResume,
                  child: Text(
                    'Resume Workout',
                    style: TextStyle(
                      color: colorScheme.onPrimary,
                      fontSize: AppTextSize.body,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
              )
            else if (!doneToday)
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  style: ElevatedButton.styleFrom(
                    backgroundColor: colorScheme.primary,
                    padding: buttonPadding,
                  ),
                  onPressed: onStart,
                  child: Text(
                    'Start Workout $type',
                    style: TextStyle(
                      color: colorScheme.onPrimary,
                      fontSize: AppTextSize.body,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
