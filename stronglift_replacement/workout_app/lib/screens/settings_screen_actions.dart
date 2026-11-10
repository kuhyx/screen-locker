// Settings actions that need no `setState`: the GitHub-mirror route, the
// reset-to-defaults confirmation, and the exercise ordering both use.
//
// A `part` so the extension keeps reaching `_load`, `widget` and `context`.
// `setState` is `@protected` and unreachable from an extension, which is
// exactly the line these three sit on the safe side of — each either
// navigates or delegates to `_load`, and `_load` owns the setState.
part of 'settings_screen.dart';

/// The settings screen's setState-free actions.
extension _SettingsScreenActions on _SettingsScreenState {
  Future<void> _openGitHubMirror() async {
    await Navigator.of(context).push<void>(
      MaterialPageRoute(
        builder: (_) => GitHubMirrorScreen(httpClient: widget.httpClient),
      ),
    );
  }

  Future<void> _resetToDefaults() async {
    final colorScheme = Theme.of(context).colorScheme;
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: colorScheme.surfaceContainerHigh,
        // Was "Reset to defaults?" / "All weights and thresholds will be
        // reset. Streak counters will be cleared.".
        title: Icon(
          Icons.restart_alt,
          color: colorScheme.error,
          semanticLabel: 'Reset to defaults?',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: Icon(
              Icons.close,
              color: colorScheme.onSurfaceVariant,
              semanticLabel: 'Cancel',
            ),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: Icon(
              Icons.restart_alt,
              color: colorScheme.error,
              semanticLabel: 'Reset',
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

  /// Pushes the shared sync-settings screen, wiring every injectable seam.
  ///
  /// Split from [_SettingsScreenState._openSyncSettings], which keeps the
  /// post-return progression pull because that half calls `setState`.
  Future<void> _pushSyncSettingsScreen() async {
    await Navigator.of(context).push<void>(
      MaterialPageRoute(
        builder: (_) => SyncSettingsScreen(
          accountLoader: widget.accountLoader ?? loadAccount,
          accountSaver: widget.accountSaver ?? saveAccount,
          accountClearer: widget.accountClearer ?? clearAccount,
          sessionProbe: widget.sessionProbe ?? isFirebaseConfigured,
          firebaseFactory: widget.firebaseFactory ?? openFirebase,
          googleFirebaseFactory:
              widget.googleFirebaseFactory ?? openFirebaseWithGoogle,
          googleAvailable: widget.googleAvailable ?? googleSignInSupported,
        ),
      ),
    );
  }

  /// Flags an exercise edit that stayed on this phone (the push did not
  /// happen). Was "Saved on this phone, not synced: `reason`"; the reason
  /// now goes to the log, the screen shows the glyph.
  void _flagUnsynced(String reason) {
    log('Settings: saved on this phone, not synced: $reason', level: 900);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Icon(
          Icons.cloud_off,
          color: Theme.of(context).colorScheme.error,
          semanticLabel: 'Saved on this phone, not synced',
        ),
      ),
    );
  }
}
