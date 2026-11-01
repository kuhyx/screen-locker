// The sound switch of the settings list.
//
// A `part` so it stays library-private. Stateless on purpose: the screen reads
// the stored choice in `_load` with its other settings, so this widget starts
// no database read of its own when it is scrolled into view.
part of 'settings_screen.dart';

/// One switch for every sound the app makes: the finish chime and the
/// break-end cue. Haptics are not sound and stay on either way.
class _SoundSection extends StatelessWidget {
  const _SoundSection({required this.enabled, required this.onChanged});

  /// Whether sound is on.
  final bool enabled;

  /// Called with the new choice when the switch is flipped.
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Card(
      margin: EdgeInsets.zero,
      color: colorScheme.surfaceContainerHigh,
      child: SwitchListTile(
        value: enabled,
        onChanged: onChanged,
        title: Text('Sound', style: TextStyle(color: colorScheme.onSurface)),
      ),
    );
  }
}
