// The PC LINK section: where the instant workout credit is sent.
//
// A `part` like the other sections. It owns its state: the address field and
// the paired flag come from PcPairing, never from the exercise state the
// surrounding screen edits. The key itself is never shown or editable here --
// it only ever arrives over adb (scripts/pair_phone.sh on the PC).
part of 'settings_screen.dart';

/// PC address field and the "paired" indicator.
class _PcLinkSection extends StatefulWidget {
  const _PcLinkSection({required this.pairingLoader});

  /// Loads the pairing; injected through [SettingsScreen.pcPairingLoader].
  final Future<PcPairingState> Function() pairingLoader;

  @override
  State<_PcLinkSection> createState() => _PcLinkSectionState();
}

class _PcLinkSectionState extends State<_PcLinkSection> {
  final TextEditingController _host = TextEditingController();
  bool? _paired;
  String? _status;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    final state = await widget.pairingLoader();
    if (!mounted) return;
    _host.text = state.host;
    setState(() => _paired = state.paired);
  }

  @override
  void dispose() {
    _host.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final host = _host.text.trim();
    if (!isValidPcHost(host)) {
      setState(() => _status = 'Not an IPv4 address or hostname: "$host".');
      return;
    }
    await PcPairing.saveHost(host);
    SandboxLog.event('pc host saved', {'host': host});
    setState(() => _status = 'Workouts are now sent to $host:$kPcPokePort.');
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final status = Theme.of(context).extension<AppStatusColors>()!;
    final paired = _paired;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const _SectionHeader('PC LINK'),
        const SizedBox(height: AppSpacing.xs),
        Text(
          'A finished workout is sent straight to the PC on the home Wi-Fi, '
          'so the credit lands in a second. Sync still delivers it otherwise.',
          style: TextStyle(
            color: colorScheme.onSurfaceVariant,
            fontSize: AppTextSize.caption,
          ),
        ),
        const SizedBox(height: AppSpacing.sm),
        Row(
          children: [
            Expanded(
              child: TextField(
                key: const Key('pc-host'),
                controller: _host,
                keyboardType: TextInputType.url,
                decoration: const InputDecoration(
                  isDense: true,
                  labelText: 'PC address',
                ),
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            TextButton(
              key: const Key('pc-host-save'),
              onPressed: () => unawaited(_save()),
              // Distinct label: the sandbox section has its own "Save", and
              // two identical labels cannot be driven by element.
              child: const Text('Save', semanticsLabel: 'Save PC address'),
            ),
          ],
        ),
        const SizedBox(height: AppSpacing.sm),
        Text(
          switch (paired) {
            null => 'PC paired: checking…',
            true => 'PC paired ✓',
            false => 'PC paired ✗ — run scripts/pair_phone.sh on the PC',
          },
          key: const Key('pc-paired'),
          style: TextStyle(
            color: paired ?? false ? status.success : status.warning,
            fontSize: AppTextSize.caption,
          ),
        ),
        if (_status != null) ...[
          const SizedBox(height: AppSpacing.xs),
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
