// Rows and steppers for the exercise settings sheet.
//
// `part` file: split out for the 250-line cap; these widgets stay private.
part of 'exercise_settings_sheet.dart';

/// `label [stepper] suffix [trailing]` on one line.
class _SettingRow extends StatelessWidget {
  const _SettingRow({
    required this.label,
    required this.name,
    required this.value,
    required this.min,
    required this.max,
    required this.suffix,
    required this.trailing,
    required this.onChanged,
  });

  final String label;

  /// Semantic name of the leading stepper.
  final String name;
  final int value;
  final int min;
  final int max;
  final String suffix;
  final Widget trailing;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    final style = TextStyle(
      color: Theme.of(context).colorScheme.onSurface,
      fontSize: AppTextSize.label,
    );
    return Row(
      children: [
        Text(label, style: style),
        const SizedBox(width: 8),
        _Stepper(
          name: name,
          value: value,
          min: min,
          max: max,
          onChanged: onChanged,
        ),
        const SizedBox(width: 8),
        Text(suffix, style: style),
        const SizedBox(width: 8),
        trailing,
      ],
    );
  }
}

/// `[-] value [+]`, with the buttons disabled at the bounds.
class _Stepper extends StatelessWidget {
  const _Stepper({
    required this.name,
    required this.value,
    required this.min,
    required this.max,
    required this.onChanged,
    this.step = 1,
    this.format,
  });

  /// What is being stepped; names the buttons for screen readers and
  /// `android_ui`, which otherwise see two identical unlabelled icons.
  final String name;
  final int value;
  final int min;
  final int max;
  final ValueChanged<int> onChanged;

  /// How far one press moves [value].
  final int step;

  /// Renders [value]; plain digits when null. A formatted value gets a
  /// wider box so `10:00` fits.
  final String Function(int)? format;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final fmt = format;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        _btn(
          context,
          '$name down',
          Icons.remove,
          value > min ? value - step : null,
        ),
        SizedBox(
          width: fmt == null ? 28 : 44,
          child: Text(
            fmt == null ? '$value' : fmt(value),
            textAlign: TextAlign.center,
            style: TextStyle(
              color: colorScheme.onSurface,
              fontSize: AppTextSize.label,
              fontWeight: FontWeight.bold,
            ),
          ),
        ),
        _btn(context, '$name up', Icons.add, value < max ? value + step : null),
      ],
    );
  }

  Widget _btn(BuildContext context, String label, IconData icon, int? next) {
    final colorScheme = Theme.of(context).colorScheme;
    return Semantics(
      container: true,
      button: true,
      label: label,
      excludeSemantics: true,
      child: InkWell(
        onTap: next == null ? null : () => onChanged(next),
        borderRadius: BorderRadius.circular(AppRadius.sm),
        child: Container(
          width: 32,
          height: 32,
          decoration: BoxDecoration(
            color: colorScheme.surfaceContainerHighest,
            borderRadius: BorderRadius.circular(AppRadius.sm),
          ),
          alignment: Alignment.center,
          child: Icon(
            icon,
            size: 16,
            color: next != null
                ? colorScheme.onSurface
                : colorScheme.onSurfaceVariant,
          ),
        ),
      ),
    );
  }
}

/// Pause controls, one fixed-height line in both states:
/// `Pause for [14] days [Pause]`, or `Paused — back on 11 Oct [Resume]`.
class _PauseRow extends StatelessWidget {
  const _PauseRow({
    required this.pausedUntil,
    required this.days,
    required this.onDaysChanged,
    required this.onPause,
    required this.onResume,
  });

  /// End of the running pause, or null when not paused.
  final DateTime? pausedUntil;
  final int days;
  final ValueChanged<int> onDaysChanged;
  final VoidCallback onPause;
  final VoidCallback onResume;

  static const int _maxDays = 60;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final style = TextStyle(
      color: colorScheme.onSurface,
      fontSize: AppTextSize.label,
    );
    final until = pausedUntil;
    return SizedBox(
      height: 40,
      child: Row(
        children: until == null
            ? [
                Text('Pause for', style: style),
                const SizedBox(width: 8),
                _Stepper(
                  name: 'Pause days',
                  value: days,
                  min: 1,
                  max: _maxDays,
                  onChanged: onDaysChanged,
                ),
                const SizedBox(width: 8),
                Text('days', style: style),
                const Spacer(),
                TextButton(onPressed: onPause, child: const Text('Pause')),
              ]
            : [
                Icon(
                  Icons.pause_circle_outline,
                  size: 18,
                  color: colorScheme.error,
                ),
                const SizedBox(width: 8),
                Text(
                  'Paused — back on ${formatShortDate(until)}',
                  style: style,
                ),
                const Spacer(),
                TextButton(onPressed: onResume, child: const Text('Resume')),
              ],
      ),
    );
  }
}
