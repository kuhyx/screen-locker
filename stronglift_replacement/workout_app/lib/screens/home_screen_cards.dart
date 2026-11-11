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
            // textgate: was "Done for today!" / "Next: Workout A" /
            // "Workout A in progress". Now the plan letter plus a state
            // glyph; colour is the second channel (success / warning).
            Row(
              children: [
                if (doneToday && !hasActiveSession)
                  Icon(
                    Icons.check_circle,
                    key: const Key('home_done_today'),
                    color: status.success,
                    semanticLabel: 'Done for today',
                  )
                else if (hasActiveSession)
                  Icon(
                    Icons.timelapse,
                    key: const Key('home_in_progress'),
                    color: status.warning,
                    semanticLabel: 'Workout $type in progress',
                  )
                else
                  Icon(
                    Icons.arrow_forward,
                    key: const Key('home_next'),
                    color: colorScheme.onSurface,
                    semanticLabel: 'Next: Workout $type',
                  ),
                const SizedBox(width: 8),
                Text(
                  type,
                  style: TextStyle(
                    color: hasActiveSession
                        ? status.warning
                        : colorScheme.onSurface,
                    fontSize: AppTextSize.subtitle,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
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
                  child: Icon(
                    Icons.play_arrow,
                    color: colorScheme.onPrimary,
                    semanticLabel: 'Resume Workout',
                  ),
                ),
              )
            else
              // Never hidden by "done today": the PC pays for every further
              // session, so an extra workout must stay one tap away.
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  style: ElevatedButton.styleFrom(
                    backgroundColor: colorScheme.primary,
                    padding: buttonPadding,
                  ),
                  onPressed: onStart,
                  child: Icon(
                    Icons.play_arrow,
                    color: colorScheme.onPrimary,
                    semanticLabel: 'Start Workout $type',
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
