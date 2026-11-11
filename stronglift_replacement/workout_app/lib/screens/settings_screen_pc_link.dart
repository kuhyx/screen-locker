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
  ({bool ok, String spoken})? _status;

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
      setState(
        () => _status = (
          ok: false,
          spoken: 'Not an IPv4 address or hostname: "$host".',
        ),
      );
      return;
    }
    await PcPairing.saveHost(host);
    SandboxLog.event('pc host saved', {'host': host});
    setState(
      () => _status = (
        ok: true,
        spoken: 'Workouts are now sent to $host:$kPcPokePort.',
      ),
    );
  }

  static String _pairedSemanticsLabel(bool? paired) => switch (paired) {
    null => 'PC paired: checking…',
    true => 'PC paired ✓',
    false => 'PC paired ✗ — run scripts/pair_phone.sh on the PC',
  };

  @override
  Widget build(BuildContext context) {
    final status = Theme.of(context).extension<AppStatusColors>()!;
    final paired = _paired;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // textgate: the explanation sentence under the heading is gone.
        const _SectionHeader(Icons.computer, 'PC LINK'),
        const SizedBox(height: AppSpacing.sm),
        Row(
          children: [
            Expanded(
              child: TextField(
                key: const Key('pc-host'),
                controller: _host,
                keyboardType: TextInputType.url,
                // Was labelText 'PC address'.
                decoration: const InputDecoration(
                  isDense: true,
                  prefixIcon: Icon(Icons.computer, semanticLabel: 'PC address'),
                ),
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            TextButton(
              key: const Key('pc-host-save'),
              onPressed: () => unawaited(_save()),
              // Distinct label: the sandbox section has its own "Save", and
              // two identical labels cannot be driven by element.
              child: const Icon(Icons.save, semanticLabel: 'Save PC address'),
            ),
          ],
        ),
        const SizedBox(height: AppSpacing.sm),
        // textgate: was "PC paired: checking…" / "PC paired ✓" / "PC
        // paired ✗ — run scripts/pair_phone.sh on the PC". Now a link glyph
        // (hourglass while checking, broken link when unpaired) in the
        // success / warning colour.
        Align(
          alignment: Alignment.centerLeft,
          child: Icon(
            switch (paired) {
              null => Icons.hourglass_empty,
              true => Icons.link,
              false => Icons.link_off,
            },
            key: const Key('pc-paired'),
            size: 20,
            color: paired ?? false ? status.success : status.warning,
            semanticLabel: _pairedSemanticsLabel(paired),
          ),
        ),
        if (_status case final s?) ...[
          const SizedBox(height: AppSpacing.xs),
          _StatusGlyph(ok: s.ok, spoken: s.spoken),
        ],
      ],
    );
  }
}
