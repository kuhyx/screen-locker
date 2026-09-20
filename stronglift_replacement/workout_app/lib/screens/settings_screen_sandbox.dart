// The SANDBOX section of the settings list, shown by the sandbox flavor only.
//
// A `part` like the other sections (see settings_screen_sections.dart). It
// owns its own state: the three controls act on the sandbox's database
// directly and report back in a status line, and none of it touches the
// exercise state the surrounding screen is editing.
part of 'settings_screen.dart';

/// Wipe, "not done today", and the rest-length override.
class _SandboxSection extends StatefulWidget {
  const _SandboxSection();

  @override
  State<_SandboxSection> createState() => _SandboxSectionState();
}

class _SandboxSectionState extends State<_SandboxSection> {
  late final TextEditingController _rest = TextEditingController(
    text: '${Sandbox.restSecs}',
  );
  String? _status;

  @override
  void dispose() {
    _rest.dispose();
    super.dispose();
  }

  void _report(String status) {
    SandboxLog.event('sandbox settings', {'status': status});
    setState(() => _status = status);
  }

  Future<void> _wipe() async {
    await StorageService.instance.wipeAll();
    Sandbox.restSecs = Sandbox.defaultRestSecs;
    _rest.text = '${Sandbox.restSecs}';
    _report('Wiped — the sandbox is back to a fresh install.');
  }

  Future<void> _markTodayNotDone() async {
    final removed = await StorageService.instance.deleteWorkoutsOn(
      DateTime.now(),
    );
    _report(
      removed == 0
          ? 'Nothing logged today; the workout is already offered.'
          : 'Removed $removed workout(s) logged today.',
    );
  }

  Future<void> _saveRest() async {
    final secs = int.tryParse(_rest.text.trim());
    if (secs == null || secs < 1) {
      _report('Rest length must be a whole number of seconds, 1 or more.');
      return;
    }
    await StorageService.instance.setSandboxRestSecs(secs);
    Sandbox.restSecs = secs;
    _report('Every rest now lasts $secs s.');
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const _SectionHeader('SANDBOX'),
        const SizedBox(height: 4),
        Text(
          'This install is the sandbox: its own data, no network, no LAN '
          'server. Nothing here can reach the daily build.',
          style: TextStyle(
            color: colorScheme.onSurfaceVariant,
            fontSize: AppTextSize.caption,
          ),
        ),
        const SizedBox(height: 12),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            ElevatedButton.icon(
              onPressed: () => unawaited(_wipe()),
              icon: const Icon(Icons.delete_sweep),
              label: const Text('Wipe sandbox data'),
            ),
            ElevatedButton.icon(
              onPressed: () => unawaited(_markTodayNotDone()),
              icon: const Icon(Icons.undo),
              label: const Text('Mark today not done'),
            ),
          ],
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            const Expanded(child: Text('Rest length (seconds)')),
            SizedBox(
              width: 72,
              child: TextField(
                key: const Key('sandbox-rest-secs'),
                controller: _rest,
                keyboardType: TextInputType.number,
                textAlign: TextAlign.center,
                decoration: const InputDecoration(
                  isDense: true,
                  hintText: 'seconds',
                ),
              ),
            ),
            const SizedBox(width: 8),
            TextButton(
              onPressed: () => unawaited(_saveRest()),
              child: const Text('Save'),
            ),
          ],
        ),
        if (_status != null) ...[
          const SizedBox(height: 8),
          Text(
            _status!,
            style: TextStyle(
              color: colorScheme.onSurfaceVariant,
              fontSize: AppTextSize.caption,
            ),
          ),
        ],
      ],
    );
  }
}
