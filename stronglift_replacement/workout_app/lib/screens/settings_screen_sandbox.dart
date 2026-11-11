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
  ({bool ok, String spoken})? _status;

  @override
  void dispose() {
    _rest.dispose();
    super.dispose();
  }

  void _report(String status, {bool ok = true}) {
    SandboxLog.event('sandbox settings', {'status': status});
    setState(() => _status = (ok: ok, spoken: status));
  }

  Future<void> _wipe() async {
    await StorageService.instance.wipeAll();
    Sandbox.restSecs = Sandbox.defaultRestSecs;
    Sandbox.runReplayFactor = Sandbox.defaultReplayFactor;
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
      _report(
        'Rest length must be a whole number of seconds, 1 or more.',
        ok: false,
      );
      return;
    }
    await StorageService.instance.setSandboxRestSecs(secs);
    Sandbox.restSecs = secs;
    _report('Every rest now lasts $secs s.');
  }

  Future<void> _saveReplay(int factor) async {
    await StorageService.instance.setSandboxReplayFactor(factor);
    setState(() => Sandbox.runReplayFactor = factor);
    _report('GPS runs replay at $factor×.');
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // textgate: the explanation paragraph under the heading is gone.
        const _SectionHeader(Icons.science, 'SANDBOX'),
        const SizedBox(height: 12),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            ElevatedButton(
              onPressed: () => unawaited(_wipe()),
              child: Icon(
                Icons.delete_sweep,
                color: colorScheme.error,
                semanticLabel: 'Wipe sandbox data',
              ),
            ),
            ElevatedButton(
              onPressed: () => unawaited(_markTodayNotDone()),
              child: const Icon(
                Icons.undo,
                semanticLabel: 'Mark today not done',
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            // Was "Rest length (seconds)"; the field shows the number.
            const Icon(Icons.timer, semanticLabel: 'Rest length (seconds)'),
            const Spacer(),
            SizedBox(
              width: 72,
              child: TextField(
                key: const Key('sandbox-rest-secs'),
                controller: _rest,
                keyboardType: TextInputType.number,
                textAlign: TextAlign.center,
                decoration: const InputDecoration(isDense: true),
              ),
            ),
            const SizedBox(width: 8),
            TextButton(
              onPressed: () => unawaited(_saveRest()),
              // Spoken label distinct from the PC LINK "Save PC address".
              child: const Icon(Icons.save, semanticLabel: 'Save'),
            ),
          ],
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            const Padding(
              padding: EdgeInsets.only(right: 12),
              child: Icon(Icons.directions_run, semanticLabel: 'GPS replay'),
            ),
            Expanded(
              child: SegmentedButton<int>(
                key: const Key('sandbox-replay-factor'),
                showSelectedIcon: false,
                segments: [
                  for (final f in Sandbox.replayFactors)
                    ButtonSegment(value: f, label: Text('$f×')),
                ],
                selected: {Sandbox.runReplayFactor},
                onSelectionChanged: (s) => unawaited(_saveReplay(s.single)),
              ),
            ),
          ],
        ),
        if (_status case final s?) ...[
          const SizedBox(height: 8),
          _StatusGlyph(
            key: const Key('sandbox-status'),
            ok: s.ok,
            spoken: s.spoken,
          ),
        ],
      ],
    );
  }
}
