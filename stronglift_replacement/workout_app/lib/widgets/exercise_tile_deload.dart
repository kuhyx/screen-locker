// The struck-through pre-deload target on an exercise tile's header.
//
// A `part` like exercise_tile_rows.dart: private to the tile.
part of 'exercise_tile.dart';

/// The pre-deload target, struck through, and a small down arrow: what a
/// gap deload took off. Numerals only (textgate); only the part that
/// changed is shown, `25kg` or `×12`.
class _DeloadedFrom extends StatelessWidget {
  const _DeloadedFrom({
    required this.from,
    required this.exercise,
    required this.color,
  });

  final ProgressionTarget from;
  final Exercise exercise;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final parts = [
      if (from.reps != exercise.reps) '×${from.reps}',
      if (from.weight != exercise.weight) '${from.weight}kg',
    ];
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(
          Icons.arrow_downward,
          size: 14,
          color: color,
          semanticLabel: '${exercise.name} deloaded after a break',
        ),
        const SizedBox(width: 2),
        Text(
          parts.join(' '),
          style: TextStyle(
            color: color,
            fontSize: AppTextSize.label,
            decoration: TextDecoration.lineThrough,
          ),
        ),
        const SizedBox(width: 6),
      ],
    );
  }
}
