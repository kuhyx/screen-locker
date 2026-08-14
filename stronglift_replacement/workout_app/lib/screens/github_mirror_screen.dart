/// The GitHub mirror screen: cutover-only sync transport, not a peer of
/// Firebase.
///
/// Kept app-local rather than folded into the shared `sync_settings_ui`
/// package because the shared package's `SyncSettingsScreen` has no GitHub
/// surface at all -- unlike todo, connecting here does NOT run a data sync:
/// `_connectGitHub` only saves the token and then verifies it can actually
/// reach `$syncRepoOwner/$syncRepoName` ([_verifyConnection]), with a
/// same-token-different-source fallback ([SyncSettings.recoverFromBackup]).
/// See `lib/screens/settings_screen.dart` for the link to this screen and to
/// the shared Sync settings screen.
library;

import 'dart:async';
import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:url_launcher/url_launcher.dart';
import 'package:workout_app/services/github_device_auth.dart';
import 'package:workout_app/services/sync_settings.dart';
import 'package:workout_app/ui/theme.dart';

/// How to style a [_SyncStatusBadge].
enum _SyncStatusKind { success, pending, error }

/// Screen for connecting/saving the GitHub mirror token.
class GitHubMirrorScreen extends StatefulWidget {
  /// Creates a [GitHubMirrorScreen].
  const GitHubMirrorScreen({super.key, this.httpClient});

  /// Injectable HTTP client; tests pass a `MockClient` so the device-flow
  /// requests never hit the real network.
  final http.Client? httpClient;

  @override
  State<GitHubMirrorScreen> createState() => _GitHubMirrorScreenState();
}

class _GitHubMirrorScreenState extends State<GitHubMirrorScreen> {
  final _tokenController = TextEditingController();
  bool _loading = true;

  // Persistent (not a transient SnackBar) so the result of Connect GitHub /
  // Save is still visible if the user looks back at the screen later --
  // mirrors diet-guard/todo's `_status` field in their settings screens.
  String? _syncStatus;
  _SyncStatusKind _syncStatusKind = _SyncStatusKind.pending;

  void _setSyncStatus(String message, _SyncStatusKind kind) {
    setState(() {
      _syncStatus = message;
      _syncStatusKind = kind;
    });
  }

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _tokenController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final syncSettings = await SyncSettings.load();
    if (!mounted) return;
    setState(() {
      _tokenController.text = syncSettings.token;
      _loading = false;
    });
    // Never claim "Connected" just because a token STRING exists — check it
    // against the API. A revoked/expired token otherwise shows a reassuring
    // green badge while every sync 401s and the history silently stays empty.
    if (syncSettings.isConfigured) {
      _setSyncStatus('Verifying…', _SyncStatusKind.pending);
      await _verifyConnection(syncSettings.token);
    }
  }

  Future<void> _saveToken() async {
    final saved = await SyncSettings(
      token: _tokenController.text.trim(),
    ).save();
    if (!mounted) return;
    _setSyncStatus(
      saved ? 'Sync token saved.' : 'Could not save token on this device.',
      saved ? _SyncStatusKind.success : _SyncStatusKind.error,
    );
  }

  /// Runs the OAuth device flow and, on success, saves the resulting token
  /// and verifies it actually works against the sync repo -- a saved token
  /// that can't reach `$syncRepoOwner/$syncRepoName` (wrong scope, revoked,
  /// etc.) must be surfaced immediately, not discovered on the next workout.
  Future<void> _connectGitHub() async {
    final auth = GitHubDeviceAuth(
      clientId: SyncSettings.defaultClientId,
      httpClient: widget.httpClient,
    );
    try {
      final device = await auth.requestDeviceCode();
      if (!mounted) return;
      final token = await showDialog<String>(
        context: context,
        barrierDismissible: false,
        builder: (_) => _DeviceCodeDialog(device: device, auth: auth),
      );
      if (token != null && token.isNotEmpty) {
        setState(() => _tokenController.text = token);
        _setSyncStatus('Connected — verifying…', _SyncStatusKind.pending);
        final saved = await SyncSettings(token: token).save();
        if (!saved) {
          if (!mounted) return;
          _setSyncStatus(
            'Connected, but could not save the token on this device.',
            _SyncStatusKind.error,
          );
          return;
        }
        await _verifyConnection(token);
      }
    } on Exception catch (e) {
      if (!mounted) return;
      _setSyncStatus('Could not start device flow: $e', _SyncStatusKind.error);
    } finally {
      auth.close();
    }
  }

  /// Confirms [token] can actually read `$syncRepoOwner/$syncRepoName`.
  /// Returns null when [token] works, else the error GitHub gave.
  Future<GitHubSyncError?> _tryVerify(String token) async {
    final client = GitHubClient(
      owner: syncRepoOwner,
      repo: syncRepoName,
      token: token,
      httpClient: widget.httpClient,
    );
    try {
      await client.getFileText('devices/phone/log.json');
      return null;
    } on GitHubSyncError catch (e) {
      return e;
    } finally {
      client.close();
    }
  }

  Future<void> _verifyConnection(String token) async {
    final error = await _tryVerify(token);
    if (error == null) {
      if (!mounted) return;
      _setSyncStatus(
        'Connected and verified via GitHub.',
        _SyncStatusKind.success,
      );
      return;
    }

    // The keystore's token may be a stale one shadowing a good backup, and
    // load() only consults the backup when the keystore is EMPTY. Try the
    // backup once before making the user re-authorize for nothing.
    final recovered = await SyncSettings.recoverFromBackup(token);
    if (recovered != null && await _tryVerify(recovered) == null) {
      if (!mounted) return;
      _tokenController.text = recovered;
      _setSyncStatus(
        'Connected and verified via GitHub (recovered the saved token from '
        'backup — the stored one had been rejected).',
        _SyncStatusKind.success,
      );
      return;
    }

    if (!mounted) return;
    // Say plainly that sync is broken. "Connected, but…" reads as success
    // and is how a dead token hid behind a green badge.
    _setSyncStatus(
      error.toString().contains('401')
          ? 'NOT connected: GitHub rejected this token (401) and no working '
                'backup was found. Tap Connect GitHub to re-authorize — '
                'until then nothing syncs.'
          : 'NOT syncing: could not reach GitHub ($error)',
      _SyncStatusKind.error,
    );
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        backgroundColor: colorScheme.surfaceContainerHigh,
        title: Text(
          'Advanced sync (GitHub)',
          style: TextStyle(color: colorScheme.onSurface),
        ),
        iconTheme: IconThemeData(color: colorScheme.onSurface),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Text(
                  'Authorize in your browser -- no token to paste. '
                  'Syncs to $syncRepoOwner/$syncRepoName.',
                  style: TextStyle(
                    color: colorScheme.onSurfaceVariant,
                    fontSize: AppTextSize.caption,
                  ),
                ),
                const SizedBox(height: 12),
                if (_syncStatus != null) ...[
                  _SyncStatusBadge(text: _syncStatus!, kind: _syncStatusKind),
                  const SizedBox(height: 12),
                ],
                Align(
                  alignment: Alignment.centerLeft,
                  child: ElevatedButton.icon(
                    onPressed: _connectGitHub,
                    icon: const Icon(Icons.login),
                    label: const Text('Connect GitHub'),
                  ),
                ),
                const SizedBox(height: 12),
                // The PAT fallback lives alongside the connect button: two
                // sibling entry points made it look like there were two
                // independent things to configure.
                _SyncTokenField(
                  controller: _tokenController,
                  onSave: _saveToken,
                ),
              ],
            ),
    );
  }
}

/// A visible, colored status pill for the GitHub sync connection state.
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
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              text,
              style: TextStyle(
                color: color,
                fontSize: AppTextSize.label,
                fontWeight: FontWeight.w600,
              ),
            ),
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
              hintText: 'GitHub PAT',
              hintStyle: TextStyle(color: colorScheme.onSurfaceVariant),
              contentPadding: const EdgeInsets.symmetric(
                horizontal: 12,
                vertical: 10,
              ),
            ),
          ),
        ),
        const SizedBox(width: 8),
        ElevatedButton(onPressed: onSave, child: const Text('Save')),
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
      title: Text(
        'Authorize on GitHub',
        style: TextStyle(color: colorScheme.onSurface),
      ),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Enter this code on GitHub:',
            style: TextStyle(color: colorScheme.onSurfaceVariant),
          ),
          const SizedBox(height: 8),
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
            Row(
              children: [
                const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    'Waiting for authorization…',
                    style: TextStyle(color: colorScheme.onSurfaceVariant),
                  ),
                ),
              ],
            )
          else
            Text(_error!, style: TextStyle(color: colorScheme.error)),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: Text(
            'Cancel',
            style: TextStyle(color: colorScheme.onSurfaceVariant),
          ),
        ),
        FilledButton.icon(
          onPressed: _openPage,
          icon: const Icon(Icons.open_in_new),
          label: const Text('Open GitHub & copy code'),
        ),
      ],
    );
  }
}
