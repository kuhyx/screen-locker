/// Settings screen: per-exercise streak thresholds and manual weight overrides.
/// Changes are saved immediately; a "Reset to defaults" button reverts all.
library;

import 'dart:async';
import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:url_launcher/url_launcher.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/models/workout_plan.dart';
import 'package:workout_app/services/github_device_auth.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/services/sync_settings.dart';

/// How to style a [_SyncStatusBadge].
enum _SyncStatusKind { success, pending, error }

/// Screen for editing per-exercise thresholds and manual weight overrides.
class SettingsScreen extends StatefulWidget {
  /// Creates a [SettingsScreen].
  const SettingsScreen({super.key, this.httpClient});

  /// Injectable HTTP client; tests pass a `MockClient` so the device-flow
  /// requests never hit the real network.
  final http.Client? httpClient;

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  bool _loading = true;

  final Map<String, int> _successThresholds = {};
  final Map<String, int> _failThresholds = {};
  final Map<String, double> _weights = {};

  // Debounce weight saves to avoid resetting streaks on every tap.
  final Map<String, Timer> _weightTimers = {};

  final _tokenController = TextEditingController();

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
    for (final t in _weightTimers.values) {
      t.cancel();
    }
    _tokenController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final states = await StorageService.instance.getAllExerciseStates();
    final syncSettings = await SyncSettings.load();
    if (mounted) {
      setState(() {
        for (final s in states) {
          _successThresholds[s.name] = s.successThreshold;
          _failThresholds[s.name] = s.failThreshold;
          _weights[s.name] = s.weight;
        }
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

  void _onWeightChanged(String name, double value) {
    setState(() => _weights[name] = value);
    _weightTimers[name]?.cancel();
    _weightTimers[name] = Timer(const Duration(milliseconds: 600), () {
      unawaited(StorageService.instance.setExerciseWeight(name, value));
    });
  }

  Future<void> _onThresholdChanged(String name, int success, int fail) async {
    setState(() {
      _successThresholds[name] = success;
      _failThresholds[name] = fail;
    });
    await StorageService.instance.setExerciseThresholds(
      name,
      successThreshold: success,
      failThreshold: fail,
    );
  }

  Future<void> _resetToDefaults() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: Colors.grey.shade900,
        title: const Text(
          'Reset to defaults?',
          style: TextStyle(color: Colors.white),
        ),
        content: const Text(
          'All weights and thresholds will be reset. '
          'Streak counters will be cleared.',
          style: TextStyle(color: Colors.white70),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text(
              'Cancel',
              style: TextStyle(color: Colors.white70),
            ),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text(
              'Reset',
              style: TextStyle(color: Colors.redAccent),
            ),
          ),
        ],
      ),
    );
    if (ok == true) {
      for (final name in _orderedNames) {
        await StorageService.instance.resetExerciseToDefaults(name);
      }
      await _load();
    }
  }

  List<String> get _orderedNames {
    final seen = <String>{};
    return [
      ...workoutA,
      ...workoutB,
    ].map((e) => e.name).where(seen.add).toList();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.grey.shade900,
      appBar: AppBar(
        backgroundColor: Colors.grey.shade800,
        title: const Text('Settings', style: TextStyle(color: Colors.white)),
        iconTheme: const IconThemeData(color: Colors.white),
        actions: [
          TextButton(
            onPressed: _loading ? null : _resetToDefaults,
            child: const Text(
              'Reset defaults',
              style: TextStyle(color: Colors.redAccent),
            ),
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                const _SectionHeader('WEIGHTS'),
                const SizedBox(height: 4),
                const Text(
                  'Override current working weight. '
                  'Resets streak counters. Rounded to 2.5 kg.',
                  style: TextStyle(color: Colors.white54, fontSize: 12),
                ),
                const SizedBox(height: 12),
                ..._orderedNames.map((name) {
                  final w = _weights[name];
                  if (w == null) return const SizedBox.shrink();
                  return _WeightRow(
                    name: name,
                    weight: w,
                    onChanged: (v) => _onWeightChanged(name, v),
                  );
                }),
                const SizedBox(height: 20),
                const _SectionHeader('PROGRESSION THRESHOLDS'),
                const SizedBox(height: 4),
                const Text(
                  'Consecutive successes (↑) or failures (↓) '
                  'before weight changes.',
                  style: TextStyle(color: Colors.white54, fontSize: 12),
                ),
                const SizedBox(height: 12),
                ..._orderedNames.map((name) {
                  final sThresh = _successThresholds[name] ?? 3;
                  final fThresh = _failThresholds[name] ?? 2;
                  return _ExerciseThresholdCard(
                    name: name,
                    successThreshold: sThresh,
                    failThreshold: fThresh,
                    onSuccessChanged: (v) =>
                        _onThresholdChanged(name, v, _failThresholds[name]!),
                    onFailChanged: (v) =>
                        _onThresholdChanged(name, _successThresholds[name]!, v),
                  );
                }),
                const SizedBox(height: 20),
                const _SectionHeader('GITHUB SYNC'),
                const SizedBox(height: 4),
                const Text(
                  'Authorize in your browser -- no token to paste. Syncs to '
                  '$syncRepoOwner/$syncRepoName. Workouts push automatically '
                  'on completion.',
                  style: TextStyle(color: Colors.white54, fontSize: 12),
                ),
                const SizedBox(height: 12),
                if (_syncStatus != null) ...[
                  _SyncStatusBadge(text: _syncStatus!, kind: _syncStatusKind),
                  const SizedBox(height: 12),
                ],
                ElevatedButton.icon(
                  onPressed: _connectGitHub,
                  icon: const Icon(Icons.login),
                  label: const Text('Connect GitHub'),
                ),
                const SizedBox(height: 8),
                ExpansionTile(
                  title: const Text(
                    'Advanced: paste a token instead',
                    style: TextStyle(color: Colors.white70, fontSize: 13),
                  ),
                  collapsedIconColor: Colors.white54,
                  iconColor: Colors.white54,
                  tilePadding: EdgeInsets.zero,
                  childrenPadding: const EdgeInsets.only(top: 8, bottom: 8),
                  children: [
                    _SyncTokenField(
                      controller: _tokenController,
                      onSave: _saveToken,
                    ),
                  ],
                ),
              ],
            ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: const TextStyle(
        color: Colors.white54,
        fontSize: 11,
        letterSpacing: 1.4,
      ),
    );
  }
}

class _WeightRow extends StatelessWidget {
  const _WeightRow({
    required this.name,
    required this.weight,
    required this.onChanged,
  });

  final String name;
  final double weight;
  final ValueChanged<double> onChanged;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        children: [
          Expanded(
            child: Text(
              name,
              style: const TextStyle(color: Colors.white70, fontSize: 13),
            ),
          ),
          _StepperButton(
            icon: Icons.remove,
            onTap: () => onChanged(
              (weight - kWeightIncrement).clamp(0.0, 999.0),
            ),
          ),
          // Fixed-width container supports up to "999.9kg" (7 chars).
          SizedBox(
            width: 72,
            child: Text(
              '${weight}kg',
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 14,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
          _StepperButton(
            icon: Icons.add,
            onTap: () => onChanged(weight + kWeightIncrement),
          ),
        ],
      ),
    );
  }
}

class _StepperButton extends StatelessWidget {
  const _StepperButton({required this.icon, required this.onTap});

  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 36,
        height: 36,
        decoration: BoxDecoration(
          color: Colors.grey.shade700,
          borderRadius: BorderRadius.circular(6),
        ),
        alignment: Alignment.center,
        child: Icon(icon, color: Colors.white, size: 18),
      ),
    );
  }
}

/// A visible, colored status pill for the GitHub sync connection state --
/// placed directly under the section description (not buried below the
/// collapsed Advanced field) so "am I connected?" has an immediate answer.
class _SyncStatusBadge extends StatelessWidget {
  const _SyncStatusBadge({required this.text, required this.kind});

  final String text;
  final _SyncStatusKind kind;

  @override
  Widget build(BuildContext context) {
    final color = switch (kind) {
      _SyncStatusKind.success => Colors.greenAccent,
      _SyncStatusKind.error => Colors.redAccent,
      _SyncStatusKind.pending => Colors.white70,
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
                fontSize: 13,
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
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: TextField(
            controller: controller,
            obscureText: true,
            style: const TextStyle(color: Colors.white),
            decoration: InputDecoration(
              hintText: 'GitHub PAT',
              hintStyle: TextStyle(color: Colors.grey.shade600),
              filled: true,
              fillColor: Colors.grey.shade800,
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: BorderSide.none,
              ),
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

class _ExerciseThresholdCard extends StatelessWidget {
  const _ExerciseThresholdCard({
    required this.name,
    required this.successThreshold,
    required this.failThreshold,
    required this.onSuccessChanged,
    required this.onFailChanged,
  });

  final String name;
  final int successThreshold;
  final int failThreshold;
  final ValueChanged<int> onSuccessChanged;
  final ValueChanged<int> onFailChanged;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.grey.shade800,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            name,
            style: const TextStyle(
              color: Colors.white,
              fontWeight: FontWeight.bold,
              fontSize: 14,
            ),
          ),
          const SizedBox(height: 10),
          _ThresholdRow(
            label: '↑ Increase after N successes',
            value: successThreshold,
            color: Colors.green,
            onChanged: onSuccessChanged,
          ),
          const SizedBox(height: 6),
          _ThresholdRow(
            label: '↓ Decrease after N failures',
            value: failThreshold,
            color: Colors.red,
            onChanged: onFailChanged,
          ),
        ],
      ),
    );
  }
}

class _ThresholdRow extends StatelessWidget {
  const _ThresholdRow({
    required this.label,
    required this.value,
    required this.color,
    required this.onChanged,
  });

  final String label;
  final int value;
  final Color color;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Text(
            label,
            style: const TextStyle(color: Colors.white70, fontSize: 12),
          ),
        ),
        const SizedBox(width: 8),
        for (int i = 1; i <= 5; i++)
          Padding(
            padding: const EdgeInsets.only(left: 4),
            child: GestureDetector(
              onTap: () => onChanged(i),
              child: Container(
                width: 32,
                height: 32,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: i == value ? color : Colors.grey.shade700,
                ),
                alignment: Alignment.center,
                child: Text(
                  '$i',
                  style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.bold,
                    fontSize: 13,
                  ),
                ),
              ),
            ),
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
    return AlertDialog(
      backgroundColor: Colors.grey.shade900,
      title: const Text(
        'Authorize on GitHub',
        style: TextStyle(color: Colors.white),
      ),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Enter this code on GitHub:',
            style: TextStyle(color: Colors.white70),
          ),
          const SizedBox(height: 8),
          SelectableText(
            widget.device.userCode,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 22,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 16),
          if (_error == null)
            const Row(
              children: [
                SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
                SizedBox(width: 12),
                Expanded(
                  child: Text(
                    'Waiting for authorization…',
                    style: TextStyle(color: Colors.white70),
                  ),
                ),
              ],
            )
          else
            Text(_error!, style: const TextStyle(color: Colors.redAccent)),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text(
            'Cancel',
            style: TextStyle(color: Colors.white70),
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
