/// One run on one screen: the whole route on a full-bleed map with its
/// numbers (distance, moving time, average pace, date) in a panel over the
/// bottom edge. Nothing scrolls (R7); no words (textgate), icons name each
/// value.
library;

import 'package:flutter/material.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/map_tile_cache.dart';
import 'package:workout_app/services/run_format.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/run_map.dart';

/// Height reserved under the route for the stats panel, so the fitted route
/// is not hidden behind it.
const _panelClearance = 190.0;

/// Detail of the finished [track] (it must carry its points).
class RunDetailScreen extends StatelessWidget {
  /// Creates the screen; [tileProviderOpener] is swapped by tests.
  const RunDetailScreen({
    required this.track,
    super.key,
    this.tileProviderOpener = openOsmTileProvider,
  });

  /// The run, with points (see `StorageServiceRuns.getRun`).
  final RunTrack track;

  /// Where the map's tiles come from.
  final TileProviderOpener tileProviderOpener;

  @override
  Widget build(BuildContext context) {
    final top = MediaQuery.paddingOf(context).top;
    return Scaffold(
      body: Stack(
        fit: StackFit.expand,
        children: [
          RunMap.route(
            points: track.points,
            fitPadding: EdgeInsets.fromLTRB(
              AppSpacing.xl,
              top + 64,
              AppSpacing.xl,
              _panelClearance,
            ),
            tileProviderOpener: tileProviderOpener,
          ),
          Positioned(
            left: AppSpacing.sm,
            top: top + AppSpacing.sm,
            child: IconButton.filledTonal(
              onPressed: () => Navigator.maybePop(context),
              icon: const Icon(Icons.arrow_back, semanticLabel: 'Back'),
            ),
          ),
          Positioned(
            left: AppSpacing.md,
            right: AppSpacing.md,
            bottom: MediaQuery.paddingOf(context).bottom + AppSpacing.md,
            child: _StatsPanel(track: track),
          ),
        ],
      ),
    );
  }
}

class _StatsPanel extends StatelessWidget {
  const _StatsPanel({required this.track});

  final RunTrack track;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final isRun = track.sport == RunSport.running;
    return Container(
      key: const Key('run_stats_panel'),
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerHigh,
        borderRadius: BorderRadius.circular(AppRadius.lg),
        border: Border.all(color: scheme.outline),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Icon(
                isRun ? Icons.directions_run : Icons.directions_walk,
                color: scheme.primary,
                semanticLabel: isRun ? 'Run' : 'Walk',
              ),
              const SizedBox(width: AppSpacing.sm),
              Text(
                formatFullDate(track.startedAt),
                style: TextStyle(color: scheme.onSurfaceVariant),
              ),
              const Spacer(),
              if (track.source == RunSource.runnerupImport)
                Icon(
                  Icons.history,
                  color: scheme.onSurfaceVariant,
                  semanticLabel: 'Imported',
                ),
            ],
          ),
          const SizedBox(height: AppSpacing.md),
          Row(
            children: [
              _Stat(Icons.straighten, formatDistanceKm(track.distanceM)),
              _Stat(Icons.timer_outlined, formatDuration(track.totalSeconds)),
              _Stat(
                Icons.speed,
                formatPace(
                  seconds: track.totalSeconds,
                  distanceM: track.distanceM,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _Stat extends StatelessWidget {
  const _Stat(this.icon, this.value);

  final IconData icon;
  final String value;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Expanded(
      child: Column(
        children: [
          Icon(icon, size: 20, color: scheme.onSurfaceVariant),
          const SizedBox(height: AppSpacing.xs),
          FittedBox(
            fit: BoxFit.scaleDown,
            child: Text(
              value,
              style: TextStyle(
                color: scheme.onSurface,
                fontSize: AppTextSize.title,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
