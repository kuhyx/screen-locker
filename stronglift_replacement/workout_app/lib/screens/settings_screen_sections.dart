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
    required this.restoredCount,
    required this.onOpenSyncSettings,
    required this.onOpenGitHubMirror,
  });

  /// Exercises the last progression pull restored, or null when none did.
  final int? restoredCount;

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
        const _SectionHeader(Icons.sync, 'SYNC'),
        const SizedBox(height: 4),
        // textgate: was "Restored N exercise(s) from Firebase."; now a
        // download glyph and the count, in the success colour.
        if (restoredCount != null) ...[
          Row(
            key: const Key('settings_restored'),
            children: [
              Icon(
                Icons.cloud_download,
                size: 18,
                color: Theme.of(context).extension<AppStatusColors>()!.success,
                semanticLabel: 'Restored from Firebase',
              ),
              const SizedBox(width: 6),
              Text(
                '$restoredCount',
                style: TextStyle(
                  color: colorScheme.onSurfaceVariant,
                  fontSize: AppTextSize.caption,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
        ],
        Card(
          margin: EdgeInsets.zero,
          color: colorScheme.surfaceContainerHigh,
          child: Column(
            children: [
              // textgate: was "Sync settings" / "Firebase sync".
              ListTile(
                leading: Icon(
                  Icons.cloud,
                  color: colorScheme.onSurface,
                  semanticLabel: 'Sync settings',
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
              // textgate: was "Advanced sync (GitHub)" / "Cutover mirror —
              // not recommended": a code glyph, muted as the not-recommended
              // route.
              ListTile(
                leading: Icon(
                  Icons.code,
                  color: colorScheme.onSurfaceVariant,
                  semanticLabel: 'Advanced sync (GitHub)',
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
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // textgate: the explanation paragraph under the heading is gone.
        const _SectionHeader(Icons.sd_storage, 'OFFLINE BACKUP'),
        const SizedBox(height: 12),
        if (storageGranted)
          // Was "Storage permission granted": storage glyph + green tick.
          Row(
            children: [
              const Icon(Icons.sd_storage, size: 20),
              const SizedBox(width: 4),
              Icon(
                Icons.check_circle,
                size: 20,
                color: Theme.of(context).extension<AppStatusColors>()!.success,
                semanticLabel: 'Storage permission granted',
              ),
            ],
          )
        else
          Align(
            alignment: Alignment.centerLeft,
            child: ElevatedButton(
              onPressed: onGrantStorage,
              child: const Icon(
                Icons.sd_storage,
                semanticLabel: 'Grant storage permission',
              ),
            ),
          ),
        DataTransferButtons(
          onImported: () => unawaited(
            context.findAncestorStateOfType<_SettingsScreenState>()!._load(),
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
      title: const Icon(Icons.settings, size: 20, semanticLabel: 'Settings'),
      iconTheme: IconThemeData(color: colorScheme.onSurface),
      actions: [
        const RunnerUpImportBadge(),
        IconButton(
          onPressed: loading ? null : onReset,
          color: colorScheme.error,
          icon: const Icon(Icons.restart_alt, semanticLabel: 'Reset defaults'),
        ),
      ],
    );
  }
}
