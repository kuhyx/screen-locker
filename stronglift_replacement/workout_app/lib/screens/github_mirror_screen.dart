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

part 'github_mirror_screen_widgets.dart';

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
