// Status badge, token field and the device-code dialog.
//
// `part` file: these widgets are library-private and stay that way.
// See history_screen_charts.dart for the full reasoning.
part of 'github_mirror_screen.dart';

class _SyncStatusBadge extends StatelessWidget {
  const _SyncStatusBadge({required this.text, required this.kind});

  final String text;
  final _SyncStatusKind kind;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final status = Theme.of(context).extension<AppStatusColors>()!;
    final color = switch (kind) {
      _SyncStatusKind.success => status.success,
      _SyncStatusKind.error => colorScheme.error,
      _SyncStatusKind.pending => colorScheme.onSurfaceVariant,
    };
    // textgate: the status sentence is spoken only; the pill shows the
    // state glyph in the state colour.
    return Semantics(label: text, excludeSemantics: true, child: _pill(color));
  }

  Widget _pill(Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.4)),
      ),
      child: Row(
        children: [
          if (kind == _SyncStatusKind.pending)
            const SizedBox(
              width: 14,
              height: 14,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          else
            Icon(
              kind == _SyncStatusKind.success
                  ? Icons.check_circle
                  : Icons.error,
              color: color,
              size: 16,
            ),
        ],
      ),
    );
  }
}

class _SyncTokenField extends StatelessWidget {
  const _SyncTokenField({required this.controller, required this.onSave});

  final TextEditingController controller;
  final VoidCallback onSave;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: TextField(
            controller: controller,
            obscureText: true,
            style: TextStyle(color: colorScheme.onSurface),
            // filled/fillColor/border inherit from the shared
            // inputDecorationTheme (theme.dart) — only the field-specific
            // hint/padding need setting here.
            decoration: InputDecoration(
              hintStyle: TextStyle(color: colorScheme.onSurfaceVariant),
              contentPadding: const EdgeInsets.symmetric(
                horizontal: 12,
                vertical: 10,
              ),
              prefixIcon: const Icon(
                Icons.vpn_key,
                semanticLabel: 'GitHub PAT',
              ),
            ),
          ),
        ),
        const SizedBox(width: 8),
        ElevatedButton(
          onPressed: onSave,
          child: const Icon(Icons.save, semanticLabel: 'Save'),
        ),
      ],
    );
  }
}

/// Dialog shown during the device flow: displays the user code, opens the
/// verification page, and polls until authorized -- popping the token (or
/// null if cancelled / failed).
class _DeviceCodeDialog extends StatefulWidget {
  const _DeviceCodeDialog({required this.device, required this.auth});

  final DeviceCodeResponse device;
  final GitHubDeviceAuth auth;

  @override
  State<_DeviceCodeDialog> createState() => _DeviceCodeDialogState();
}

class _DeviceCodeDialogState extends State<_DeviceCodeDialog> {
  String? _error;

  @override
  void initState() {
    super.initState();
    unawaited(_poll());
  }

  Future<void> _poll() async {
    try {
      final token = await widget.auth.pollForToken(widget.device);
      if (mounted) Navigator.of(context).pop(token);
    } on Exception catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  Future<void> _openPage() async {
    await Clipboard.setData(ClipboardData(text: widget.device.userCode));
    await launchUrl(
      Uri.parse(widget.device.verificationUri),
      mode: LaunchMode.externalApplication,
    );
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return AlertDialog(
      backgroundColor: colorScheme.surfaceContainerHigh,
      // Was "Authorize on GitHub" / "Enter this code on GitHub:" /
      // "Waiting for authorization…": key glyph, the code, a spinner.
      title: Icon(
        Icons.vpn_key,
        color: colorScheme.onSurface,
        semanticLabel: 'Authorize on GitHub',
      ),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SelectableText(
            widget.device.userCode,
            style: TextStyle(
              color: colorScheme.onSurface,
              fontSize: AppTextSize.title,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 16),
          if (_error == null)
            const SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                semanticsLabel: 'Waiting for authorization…',
              ),
            )
          else
            // textgate: the failure is spoken only.
            Icon(
              Icons.error_outline,
              color: colorScheme.error,
              semanticLabel: _error,
            ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: Icon(
            Icons.close,
            color: colorScheme.onSurfaceVariant,
            semanticLabel: 'Cancel',
          ),
        ),
        // Was "Open GitHub & copy code".
        FilledButton(
          onPressed: _openPage,
          child: const Icon(
            Icons.open_in_new,
            semanticLabel: 'Open GitHub & copy code',
          ),
        ),
      ],
    );
  }
}
