// Rest-length rows for the exercise settings sheet.
//
// `part` file: split out for the 250-line cap; these widgets stay private.
part of 'exercise_settings_sheet.dart';

/// `Rest ✓ [3:00]  ✗ [5:00]`, then `Warmup rest [3:00]`.
///
/// The warmup line stays laid out when the warmup is off, so toggling it
/// never changes the sheet's height under the finger.
class _RestRows extends StatelessWidget {
  const _RestRows({required this.state, required this.onChanged});

  final ExerciseState state;
  final ValueChanged<ExerciseState> onChanged;

  _Stepper _stepper(String name, int value, ValueChanged<int> onChanged) =>
      _Stepper(
        name: name,
        value: value,
        min: kMinRestSecs,
        max: kMaxRestSecs,
        step: kRestStepSecs,
        format: formatRest,
        onChanged: onChanged,
      );

  @override
  Widget build(BuildContext context) {
    final style = TextStyle(
      color: Theme.of(context).colorScheme.onSurface,
      fontSize: AppTextSize.label,
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text('Rest ✓', style: style),
            const SizedBox(width: 8),
            _stepper(
              'Success rest',
              state.restSuccessSecs,
              (v) => onChanged(state.copyWith(restSuccessSecs: v)),
            ),
            const SizedBox(width: 12),
            Text('✗', style: style),
            const SizedBox(width: 8),
            _stepper(
              'Fail rest',
              state.restFailSecs,
              (v) => onChanged(state.copyWith(restFailSecs: v)),
            ),
          ],
        ),
        const SizedBox(height: 8),
        Visibility(
          visible: state.hasWarmup,
          maintainSize: true,
          maintainAnimation: true,
          maintainState: true,
          child: Row(
            children: [
              Text('Warmup rest', style: style),
              const SizedBox(width: 8),
              _stepper(
                'Warmup rest',
                state.restWarmupSecs,
                (v) => onChanged(state.copyWith(restWarmupSecs: v)),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
