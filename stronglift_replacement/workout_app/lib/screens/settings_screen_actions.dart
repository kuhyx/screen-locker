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
        title: Text(
          'Reset to defaults?',
          style: TextStyle(color: colorScheme.onSurface),
        ),
        content: Text(
          'All weights and thresholds will be reset. '
          'Streak counters will be cleared.',
          style: TextStyle(color: colorScheme.onSurfaceVariant),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: Text(
              'Cancel',
              style: TextStyle(color: colorScheme.onSurfaceVariant),
            ),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: Text('Reset', style: TextStyle(color: colorScheme.error)),
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
}
