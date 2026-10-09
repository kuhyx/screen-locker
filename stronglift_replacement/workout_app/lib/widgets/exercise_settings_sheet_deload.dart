// The manual "Deload now" row of the exercise settings sheet.
//
// `part` file: split out for the 250-line cap; these widgets stay private.
part of 'exercise_settings_sheet.dart';

/// `Deload  100 kg × 5 → 97.5 kg  [Deload now]` on one fixed-height line.
///
/// Only ever a step down, and only the step a fail streak would take
/// ([targetAfterFailure]): the target goes up through finished workouts
/// alone. Disabled when the rule has nowhere lower to go.
class _DeloadRow extends StatelessWidget {
  const _DeloadRow({required this.state, required this.onDeload});

  final ExerciseState state;
  final VoidCallback onDeload;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final change = describeTargetChange(state, targetAfterFailure(state));
    final canDeload = change != 'same';
    return SizedBox(
      height: 40,
      child: Row(
        children: [
          Expanded(
            child: Text(
              canDeload
                  ? 'Deload  ${_target(state)} → $change'
                  : 'Deload  nothing lower to go to',
              style: TextStyle(
                color: colorScheme.onSurface,
                fontSize: AppTextSize.label,
              ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
          TextButton(
            onPressed: canDeload ? onDeload : null,
            child: const Text('Deload now'),
          ),
        ],
      ),
    );
  }
}

/// `100 kg × 5`: the current target, as the confirm dialog and row show it.
String _target(ExerciseState s) {
  final kg = s.weight == s.weight.roundToDouble()
      ? s.weight.toInt().toString()
      : s.weight.toString();
  return '$kg kg × ${s.reps}';
}

/// Asks before deloading [s]: the step cannot be undone by hand, only
/// earned back by finished workouts.
Future<bool> _confirmDeload(BuildContext context, ExerciseState s) async {
  final colorScheme = Theme.of(context).colorScheme;
  final change = describeTargetChange(s, targetAfterFailure(s));
  final ok = await showDialog<bool>(
    context: context,
    builder: (dialogContext) => AlertDialog(
      backgroundColor: colorScheme.surfaceContainerHigh,
      title: Text(
        'Deload ${s.name}?',
        style: TextStyle(color: colorScheme.onSurface),
      ),
      content: Text(
        '${_target(s)} → $change\n\n'
        'Streaks reset. Only finished workouts raise it again.',
        style: TextStyle(color: colorScheme.onSurfaceVariant),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(dialogContext, false),
          child: Text(
            'Cancel',
            style: TextStyle(color: colorScheme.onSurfaceVariant),
          ),
        ),
        TextButton(
          onPressed: () => Navigator.pop(dialogContext, true),
          child: Text('Deload', style: TextStyle(color: colorScheme.error)),
        ),
      ],
    ),
  );
  return ok ?? false;
}
