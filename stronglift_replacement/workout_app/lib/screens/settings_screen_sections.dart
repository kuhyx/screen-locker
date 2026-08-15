// The SYNC and OFFLINE BACKUP sections of the settings list.
//
// A `part` so these stay library-private: making them public would trip
// `public_member_api_docs` and widen the app's API for no reason.
//
// Both are pure widgets rather than list-building methods on the state class.
// Every conditional here is the one the original `build()` had, in the same
// shape — no defaulted parameters, no `??` fallbacks, no extra null checks —
// because a new branch is a line no existing test covers and the coverage
// gate is at 100%.
part of 'settings_screen.dart';

/// The SYNC section: progression status line plus the two sync routes.
class _SyncSection extends StatelessWidget {
  const _SyncSection({
    required this.progressionStatus,
    required this.onOpenSyncSettings,
    required this.onOpenGitHubMirror,
  });

  /// Last progression-sync outcome, or null when there is nothing to report.
  final String? progressionStatus;

  /// Opens the Firebase sync settings screen.
  final VoidCallback onOpenSyncSettings;

  /// Opens the legacy GitHub mirror screen.
  final VoidCallback onOpenGitHubMirror;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const _SectionHeader('SYNC'),
        const SizedBox(height: 4),
        if (progressionStatus != null) ...[
          Text(
            progressionStatus!,
            style: TextStyle(
              color: colorScheme.onSurfaceVariant,
              fontSize: AppTextSize.caption,
            ),
          ),
          const SizedBox(height: 8),
        ],
        Card(
          margin: EdgeInsets.zero,
          color: colorScheme.surfaceContainerHigh,
          child: Column(
            children: [
              ListTile(
                title: Text(
                  'Sync settings',
                  style: TextStyle(color: colorScheme.onSurface),
                ),
                subtitle: Text(
                  'Firebase sync',
                  style: TextStyle(color: colorScheme.onSurfaceVariant),
                ),
                trailing: Icon(
                  Icons.chevron_right,
                  color: colorScheme.onSurfaceVariant,
                ),
                onTap: onOpenSyncSettings,
              ),
              Divider(
                height: 1,
                color: colorScheme.onSurfaceVariant.withValues(alpha: 0.2),
              ),
              ListTile(
                title: Text(
                  'Advanced sync (GitHub)',
                  style: TextStyle(color: colorScheme.onSurface),
                ),
                subtitle: Text(
                  'Cutover mirror — not recommended',
                  style: TextStyle(color: colorScheme.onSurfaceVariant),
                ),
                trailing: Icon(
                  Icons.chevron_right,
                  color: colorScheme.onSurfaceVariant,
                ),
                onTap: onOpenGitHubMirror,
              ),
            ],
          ),
        ),
      ],
    );
  }
}

/// The OFFLINE BACKUP section: what the permission buys, and how to grant it.
class _OfflineBackupSection extends StatelessWidget {
  const _OfflineBackupSection({
    required this.storageGranted,
    required this.onGrantStorage,
  });

  /// Whether storage permission is already held.
  final bool storageGranted;

  /// Asks the OS for storage permission.
  final VoidCallback onGrantStorage;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const _SectionHeader('OFFLINE BACKUP'),
        const SizedBox(height: 4),
        Text(
          storageGranted
              ? 'Granted. Progression is also written to '
                    '$kBackupPath, so it survives a reinstall even '
                    'with no network.'
              : 'Optional. Progression is restored from Firebase on '
                    'a fresh install, so this is a second, offline '
                    'copy — not a requirement. Granting it also keeps '
                    'a readable snapshot at $kBackupPath.',
          style: TextStyle(
            color: colorScheme.onSurfaceVariant,
            fontSize: AppTextSize.caption,
          ),
        ),
        const SizedBox(height: 12),
        if (storageGranted)
          const Row(
            children: [
              Icon(Icons.check_circle, size: 20),
              SizedBox(width: 8),
              Expanded(child: Text('Storage permission granted')),
            ],
          )
        else
          Align(
            alignment: Alignment.centerLeft,
            child: ElevatedButton.icon(
              onPressed: onGrantStorage,
              icon: const Icon(Icons.sd_storage),
              label: const Text('Grant storage permission'),
            ),
          ),
      ],
    );
  }
}

/// App bar for the settings screen, with the Reset-defaults action.
///
/// Reset is disabled while [loading] so it cannot fire against half-read
/// state — the same `_loading ? null : ...` the original `build()` used.
class _SettingsAppBar extends StatelessWidget implements PreferredSizeWidget {
  const _SettingsAppBar({required this.loading, required this.onReset});

  /// Whether settings are still being read; disables Reset while true.
  final bool loading;

  /// Invoked when the user taps Reset defaults.
  final VoidCallback onReset;

  @override
  Size get preferredSize => const Size.fromHeight(kToolbarHeight);

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return AppBar(
      backgroundColor: colorScheme.surfaceContainerHigh,
      title: Text(
        'Settings',
        style: TextStyle(color: colorScheme.onSurface),
      ),
      iconTheme: IconThemeData(color: colorScheme.onSurface),
      actions: [
        TextButton(
          onPressed: loading ? null : onReset,
          child: Text(
            'Reset defaults',
            style: TextStyle(color: colorScheme.error),
          ),
        ),
      ],
    );
  }
}
